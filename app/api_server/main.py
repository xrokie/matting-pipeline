from pathlib import Path
import re
import shutil
import urllib.request
import urllib.error

import numpy as np
from PIL import Image as PILImage
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .jobs import jobs
from .mask_registry import register_retained_mask as _register_retained_mask
from .project_files import (
    load_state,
    normalize_project_id,
    project_dir,
    project_response,
    resolve_file,
    save_upload,
)
from .runner import CommandError, run_json_command, run_streaming_command
from .schemas import BoxPrompt, MattingRequest, PointPrompt, TextPrompt


app = FastAPI(title="SAM3.1 + MatAnyone2 视频换背景 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_root = Path(__file__).resolve().parents[1] / "frontend"
frontend_dist = frontend_root / "dist"
frontend_dir = frontend_dist if frontend_dist.exists() else frontend_root
if frontend_dir.exists():
    app.mount("/app", StaticFiles(directory=str(frontend_dir), html=True), name="app")


@app.get("/")
def root():
    return RedirectResponse(url="/app")


def conda_command(env_name, *parts):
    return ["conda", "run", "--no-capture-output", "-n", env_name, "python", "-m", *parts]


def sam3_command(*parts):
    return conda_command(settings.sam3_env, "services.mask_service_cli", *parts)


def matanyone2_command(*parts):
    return conda_command(settings.matanyone2_env, "services.matting_project_cli", *parts)


def _sam2_post(endpoint: str, data: dict, timeout: int = 60) -> dict:
    """Make a JSON POST request to the SAM2 point server."""
    import json as _json
    url = f"{settings.sam2_server_url}{endpoint}"
    body = _json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return _json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8") if exc.fp else str(exc)
        raise RuntimeError(f"SAM2 server HTTP {exc.code}: {err_body}")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"SAM2 server unreachable: {exc}")


def _sam2_available() -> bool:
    """Check if the SAM2 point server is reachable."""
    try:
        import json as _json
        url = f"{settings.sam2_server_url}/health"
        with urllib.request.urlopen(url, timeout=2) as resp:
            result = _json.loads(resp.read().decode("utf-8"))
            return result.get("status") == "ok"
    except Exception:
        return False


def run_sam2_point(project_id: str, point: list[int, int]) -> dict:
    """Run point-prompt via SAM2 persistent server.

    Saves mask + overlay to the project directory, registers the retained
    mask in state.json, and re-merges final.png.  Returns the updated project
    response dict.
    """
    target_project = project_dir(project_id)
    state = load_state(project_id)
    first_frame_rel = state.get("first_frame")
    if not first_frame_rel:
        raise RuntimeError("Project has no first_frame — run init first")
    first_frame_path = target_project / first_frame_rel

    # Ensure SAM2 has the image encoded (cheap check, skips re-encoding if cached)
    _precache_sam2_image(project_id, str(first_frame_path))

    # Determine output paths
    retained_count = len(state.get("retained_masks", []))
    mask_dest = target_project / "masks" / f"retained_{retained_count:03d}.png"
    overlay_dest = target_project / "overlays" / f"retained_{retained_count:03d}_overlay.png"

    # Call SAM2 predict
    result = _sam2_post("/predict", {
        "project_id": project_id,
        "point": point,
        "label": 1,
        "save_mask": str(mask_dest),
        "save_overlay": str(overlay_dest),
        "image_path_for_overlay": str(first_frame_path),
    })

    # Load the saved mask and register it
    mask_arr = np.array(PILImage.open(mask_dest).convert("L"))

    source = {"mode": "point", "point": list(point)}
    new_state = _register_retained_mask(
        project_dir=target_project,
        mask=mask_arr,
        source=source,
    )

    return project_response(project_id, new_state)


def handle_command_error(exc):
    raise HTTPException(
        status_code=500,
        detail={
            "code": "COMMAND_FAILED",
            "message": str(exc),
            "stdout": exc.stdout,
            "stderr": exc.stderr,
        },
    ) from exc


def run_sam3_json(project_id, *parts):
    try:
        state = run_json_command(sam3_command(*parts), cwd=settings.sam3_dir)
    except CommandError as exc:
        handle_command_error(exc)
    return project_response(project_id, state)


def _precache_sam2_image(project_id: str, image_path: str):
    """Pre-encode image in SAM2 server if not already cached.

    Safe to call multiple times — skips re-encoding if project is cached.
    """
    if not _sam2_available():
        return
    try:
        import json as _json
        url = f"{settings.sam2_server_url}/health"
        with urllib.request.urlopen(url, timeout=2) as resp:
            health = _json.loads(resp.read().decode("utf-8"))
        if project_id in health.get("cached_projects", []):
            return
        _sam2_post("/set_image", {
            "project_id": project_id,
            "image_path": image_path,
        })
    except Exception as exc:
        print(f"[WARN] SAM2 pre-cache failed (non-fatal): {exc}")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "matting_root": str(settings.matting_root),
        "sam3_dir_exists": settings.sam3_dir.exists(),
        "matanyone2_dir_exists": settings.matanyone2_dir.exists(),
        "sam3_checkpoint_exists": settings.sam3_checkpoint.exists(),
        "matanyone2_checkpoint_exists": settings.matanyone2_checkpoint.exists(),
    }


@app.post("/api/projects")
def create_project(
    video: UploadFile = File(...),
    background: UploadFile | None = File(default=None),
    project_id: str | None = Form(default=None),
):
    project_id = normalize_project_id(project_id)
    target_project = project_dir(project_id)
    upload_dir = target_project / "_uploads"

    video_path = save_upload(video, upload_dir / "source_video")
    background_path = save_upload(background, upload_dir / "source_background") if background else None

    try:
        state = run_json_command(
            sam3_command(
                "init",
                "--project",
                str(target_project),
                "--video",
                str(video_path),
                *(
                    ["--background", str(background_path)]
                    if background_path
                    else []
                ),
            ),
            cwd=settings.sam3_dir,
        )
    except CommandError as exc:
        handle_command_error(exc)

    shutil.rmtree(upload_dir, ignore_errors=True)

    # Clear stale SAM2 cache (project may have been re-created with a
    # different video → different first-frame dimensions) then pre-cache.
    if _sam2_available():
        try:
            _sam2_post("/clear_image", {"project_id": project_id})
        except Exception:
            pass
    first_frame = state.get("first_frame")
    if first_frame:
        _precache_sam2_image(project_id, str(target_project / first_frame))

    return project_response(project_id, state)


@app.get("/api/projects/{project_id}")
def get_project(project_id: str):
    state = load_state(project_id)
    return project_response(project_id, state)


@app.post("/api/projects/{project_id}/subject/text")
def set_subject_text(project_id: str, payload: TextPrompt):
    target_project = project_dir(project_id)
    return run_sam3_json(
        project_id,
        "set-subject-text",
        "--project",
        str(target_project),
        "--checkpoint",
        str(settings.sam3_checkpoint),
        "--text",
        payload.text,
        "--device",
        settings.sam3_device,
    )


@app.post("/api/projects/{project_id}/subject/box")
def set_subject_box(project_id: str, payload: BoxPrompt):
    target_project = project_dir(project_id)
    return run_sam3_json(
        project_id,
        "set-subject-box",
        "--project",
        str(target_project),
        "--checkpoint",
        str(settings.sam3_checkpoint),
        "--box",
        *[str(value) for value in payload.box],
        "--device",
        settings.sam3_device,
    )


@app.post("/api/projects/{project_id}/subject/point")
def set_subject_point(project_id: str, payload: PointPrompt):
    target_project = project_dir(project_id)
    return run_sam3_json(
        project_id,
        "set-subject-point",
        "--project",
        str(target_project),
        "--checkpoint",
        str(settings.sam3_checkpoint),
        "--point",
        *[str(value) for value in payload.point],
        "--device",
        settings.sam3_device,
    )


@app.post("/api/projects/{project_id}/foreground/text")
def add_foreground_text(project_id: str, payload: TextPrompt):
    target_project = project_dir(project_id)
    return run_sam3_json(
        project_id,
        "add-foreground-text",
        "--project",
        str(target_project),
        "--checkpoint",
        str(settings.sam3_checkpoint),
        "--text",
        payload.text,
        "--device",
        settings.sam3_device,
    )


@app.post("/api/projects/{project_id}/foreground/box")
def add_foreground_box(project_id: str, payload: BoxPrompt):
    target_project = project_dir(project_id)
    return run_sam3_json(
        project_id,
        "add-foreground-box",
        "--project",
        str(target_project),
        "--checkpoint",
        str(settings.sam3_checkpoint),
        "--box",
        *[str(value) for value in payload.box],
        "--device",
        settings.sam3_device,
    )


@app.post("/api/projects/{project_id}/foreground/point")
def add_foreground_point(project_id: str, payload: PointPrompt):
    target_project = project_dir(project_id)
    return run_sam3_json(
        project_id,
        "add-foreground-point",
        "--project",
        str(target_project),
        "--checkpoint",
        str(settings.sam3_checkpoint),
        "--point",
        *[str(value) for value in payload.point],
        "--device",
        settings.sam3_device,
    )


@app.post("/api/projects/{project_id}/masks/text")
def add_mask_text(project_id: str, payload: TextPrompt):
    target_project = project_dir(project_id)
    return run_sam3_json(
        project_id,
        "add-mask-text",
        "--project",
        str(target_project),
        "--checkpoint",
        str(settings.sam3_checkpoint),
        "--text",
        payload.text,
        "--device",
        settings.sam3_device,
    )


@app.post("/api/projects/{project_id}/masks/point")
def add_mask_point(project_id: str, payload: PointPrompt):
    # Prefer SAM2 persistent server for fast point prompts
    if _sam2_available():
        try:
            return run_sam2_point(project_id, payload.point)
        except Exception as exc:
            # SAM2 failed — log and fall back to SAM3
            print(f"[WARN] SAM2 point failed, falling back to SAM3: {exc}")

    # Fallback: SAM3.1 point prompt
    target_project = project_dir(project_id)
    return run_sam3_json(
        project_id,
        "add-mask-point",
        "--project",
        str(target_project),
        "--checkpoint",
        str(settings.sam3_checkpoint),
        "--point",
        *[str(value) for value in payload.point],
        "--device",
        settings.sam3_device,
    )


@app.post("/api/projects/{project_id}/masks/box")
def add_mask_box(project_id: str, payload: BoxPrompt):
    """Add retained mask via box/rectangle prompt (SAM3.1 only, no SAM2 fallback)."""
    target_project = project_dir(project_id)
    return run_sam3_json(
        project_id,
        "add-mask-box",
        "--project",
        str(target_project),
        "--checkpoint",
        str(settings.sam3_checkpoint),
        "--box",
        *[str(value) for value in payload.box],
        "--device",
        settings.sam3_device,
    )


@app.post("/api/projects/{project_id}/foreground/undo")
def undo_foreground(project_id: str):
    target_project = project_dir(project_id)
    return run_sam3_json(
        project_id,
        "undo-foreground",
        "--project",
        str(target_project),
    )


@app.post("/api/projects/{project_id}/mask/undo")
def undo_mask(project_id: str):
    target_project = project_dir(project_id)
    return run_sam3_json(
        project_id,
        "undo-mask",
        "--project",
        str(target_project),
    )


@app.post("/api/projects/{project_id}/masks/clear")
def clear_masks(project_id: str):
    """Clear all retained masks (keep matting rounds and results).

    Used when the user wants to re-select objects for a new matting round
    while preserving previously generated alpha from earlier rounds.
    """
    target_project = project_dir(project_id)
    state = load_state(project_id)
    state["retained_masks"] = []
    state["foreground_masks"] = []
    state["subject_mask"] = None
    state["final_mask"] = None
    state["mask_snapshots"] = []
    state.setdefault("history", []).append({
        "time": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "action": "clear_masks",
        "payload": {},
    })
    state_path = target_project / "state.json"
    state_path.write_text(__import__("json").dumps(state, indent=2, ensure_ascii=False))
    return project_response(project_id, state)


@app.post("/api/projects/{project_id}/targets/text")
def add_target_text(project_id: str, payload: TextPrompt):
    target_project = project_dir(project_id)
    return run_sam3_json(
        project_id,
        "add-target-text",
        "--project",
        str(target_project),
        "--checkpoint",
        str(settings.sam3_checkpoint),
        "--text",
        payload.text,
        "--device",
        settings.sam3_device,
    )


@app.post("/api/projects/{project_id}/targets/box")
def add_target_box(project_id: str, payload: BoxPrompt):
    target_project = project_dir(project_id)
    return run_sam3_json(
        project_id,
        "add-target-box",
        "--project",
        str(target_project),
        "--checkpoint",
        str(settings.sam3_checkpoint),
        "--box",
        *[str(value) for value in payload.box],
        "--device",
        settings.sam3_device,
    )


@app.post("/api/projects/{project_id}/targets/point")
def add_target_point(project_id: str, payload: PointPrompt):
    target_project = project_dir(project_id)
    return run_sam3_json(
        project_id,
        "add-target-point",
        "--project",
        str(target_project),
        "--checkpoint",
        str(settings.sam3_checkpoint),
        "--point",
        *[str(value) for value in payload.point],
        "--device",
        settings.sam3_device,
    )


def run_matting_job(project_id, payload: MattingRequest, job_id, target_id=None):
    target_project = project_dir(project_id)
    command = matanyone2_command(
        "--project",
        str(target_project),
        "--ckpt",
        str(settings.matanyone2_checkpoint),
        "--warmup",
        str(payload.warmup),
        "--erode",
        str(payload.erode),
        "--dilate",
        str(payload.dilate),
        "--max-size",
        str(payload.max_size),
    )
    if payload.save_image:
        command.append("--save-image")
    if target_id:
        command.extend(["--target-id", target_id])

    progress_parser = MattingProgressParser(job_id)
    run_streaming_command(
        command,
        cwd=settings.matanyone2_dir,
        on_output=progress_parser.feed,
    )

    state = load_state(project_id)
    if target_id:
        target = next((item for item in state.get("targets", []) if item.get("id") == target_id), None)
        results = (target or {}).get("results") or {}
        if not results.get("replaced"):
            raise RuntimeError(f"MatAnyone2 已结束，但 {target_id} 中没有 results.replaced")
    else:
        results = state.get("results") or {}
        if not results.get("green"):
            raise RuntimeError("MatAnyone2 已结束，但 state.json 中没有 results.green")
    return project_response(project_id, state)


def run_background_job(project_id, background_path, job_id):
    target_project = project_dir(project_id)
    command = matanyone2_command(
        "--project",
        str(target_project),
        "--compose-background",
        "--background",
        str(background_path),
    )

    progress_parser = MattingProgressParser(job_id)
    try:
        run_streaming_command(
            command,
            cwd=settings.matanyone2_dir,
            on_output=progress_parser.feed,
        )
    finally:
        shutil.rmtree(Path(background_path).parent, ignore_errors=True)

    state = load_state(project_id)
    results = state.get("results") or {}
    if not results.get("replaced"):
        raise RuntimeError("背景合成已结束，但 state.json 中没有 results.replaced")
    return project_response(project_id, state)


class MattingProgressParser:
    FRAME_RE = re.compile(r"(?P<current>\d+)\s*/\s*(?P<total>\d+)")

    def __init__(self, job_id):
        self.job_id = job_id
        self.buffer = ""
        self.last_current = -1
        self.last_total = -1

    def feed(self, chunk):
        self.buffer += chunk
        if len(self.buffer) > 240:
            self.buffer = self.buffer[-240:]

        self._update_stage()
        self._update_frame_progress()

    def _update_stage(self):
        lower = self.buffer.lower()
        if "running matanyone2" in lower:
            jobs.update(
                self.job_id,
                stage="matanyone2",
                progress=max(jobs.get(self.job_id)["progress"], 0.05),
                message="MatAnyone2 初始化中",
            )
        elif "composing green screen preview" in lower:
            jobs.update(
                self.job_id,
                stage="green_preview",
                progress=max(jobs.get(self.job_id)["progress"], 0.88),
                message="正在生成绿幕预览",
            )
        elif "composing uploaded background" in lower or "composing background" in lower:
            jobs.update(
                self.job_id,
                stage="compose",
                progress=max(jobs.get(self.job_id)["progress"], 0.90),
                message="正在合成背景",
            )
        elif "muxing source audio" in lower:
            jobs.update(
                self.job_id,
                stage="mux_audio",
                progress=max(jobs.get(self.job_id)["progress"], 0.95),
                message="正在封装音频",
            )

    def _update_frame_progress(self):
        matches = list(self.FRAME_RE.finditer(self.buffer))
        if not matches:
            return

        match = matches[-1]
        current = int(match.group("current"))
        total = int(match.group("total"))
        if total <= 0:
            return
        if current == self.last_current and total == self.last_total:
            return

        self.last_current = current
        self.last_total = total
        ratio = max(0.0, min(1.0, current / total))
        progress = 0.05 + ratio * 0.80
        jobs.update(
            self.job_id,
            stage="matanyone2",
            progress=progress,
            message=f"MatAnyone2 推理中：{current}/{total} 帧",
        )


def undo_matting_round_job(project_id):
    target_project = project_dir(project_id)
    run_streaming_command(
        matanyone2_command("--project", str(target_project), "--undo-round"),
        cwd=settings.matanyone2_dir,
    )
    state = load_state(project_id)
    return project_response(project_id, state)


@app.post("/api/projects/{project_id}/matting")
def start_matting(project_id: str, payload: MattingRequest):
    state = load_state(project_id)
    if not state.get("final_mask"):
        raise HTTPException(status_code=400, detail="需要先生成 final_mask")

    job = jobs.submit(project_id, run_matting_job, project_id, payload)
    return job


@app.post("/api/projects/{project_id}/background")
def upload_background(project_id: str, background: UploadFile = File(...)):
    state = load_state(project_id)
    results = state.get("results") or {}
    if not results.get("alpha"):
        raise HTTPException(status_code=400, detail="需要先完成 MatAnyone2 绿幕生成")

    target_project = project_dir(project_id)
    upload_dir = target_project / "_uploads" / "background"
    background_path = save_upload(background, upload_dir / "source_background")
    job = jobs.submit(
        project_id,
        run_background_job,
        project_id,
        str(background_path),
        initial_stage="background_queued",
        initial_message="背景合成任务已进入队列",
        running_stage="compose",
        running_message="开始合成替换背景",
    )
    return job


@app.post("/api/projects/{project_id}/matting/undo")
def undo_matting_round(project_id: str):
    state = load_state(project_id)
    if not state.get("matting_rounds"):
        raise HTTPException(status_code=400, detail="没有可撤销的绿幕轮次")

    try:
        return undo_matting_round_job(project_id)
    except CommandError as exc:
        handle_command_error(exc)


@app.post("/api/projects/{project_id}/targets/{target_id}/matting")
def start_target_matting(project_id: str, target_id: str, payload: MattingRequest):
    state = load_state(project_id)
    if not any(item.get("id") == target_id for item in state.get("targets", [])):
        raise HTTPException(status_code=404, detail="target 不存在")

    job = jobs.submit(project_id, run_matting_job, project_id, payload, target_id=target_id)
    return job


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job 不存在")
    return job


@app.get("/files/{project_id}/{file_path:path}")
def get_file(project_id: str, file_path: str):
    target = resolve_file(project_id, file_path)
    return FileResponse(str(target))
