import json
import re
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from .config import settings


PROJECT_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{1,63}$")


def normalize_project_id(project_id=None):
    if project_id is None or project_id.strip() == "":
        return f"project_{uuid4().hex[:12]}"

    project_id = project_id.strip()
    if not PROJECT_ID_RE.match(project_id):
        raise HTTPException(
            status_code=400,
            detail="project_id 只能包含字母、数字、下划线和中划线，长度 2-64",
        )
    return project_id


def project_dir(project_id):
    project_id = normalize_project_id(project_id)
    path = (settings.projects_dir / project_id).resolve()
    if settings.projects_dir not in path.parents and path != settings.projects_dir:
        raise HTTPException(status_code=400, detail="非法 project 路径")
    return path


def load_state(project_id):
    path = project_dir(project_id) / "state.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="project 不存在")
    return json.loads(path.read_text())


def save_upload(upload: UploadFile, target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as out:
        shutil.copyfileobj(upload.file, out)
    return target


def file_url(project_id, relative_path):
    if relative_path is None:
        return None
    return f"/files/{project_id}/{relative_path}"


def state_status(state):
    results = state.get("results") or {}
    if results.get("replaced"):
        return "background_succeeded"
    if results.get("green"):
        return "ready_for_background"
    if state.get("final_mask"):
        return "ready_for_matting"
    if state.get("first_frame"):
        return "ready_for_mask"
    return "created"


def state_files(project_id, state):
    files = {
        "video": file_url(project_id, state.get("video")),
        "background": file_url(project_id, state.get("background")),
        "first_frame": file_url(project_id, state.get("first_frame")),
        "subject_mask": file_url(project_id, state.get("subject_mask")),
        "final_mask": file_url(project_id, state.get("final_mask")),
    }

    foreground_masks = state.get("foreground_masks") or []
    files["foreground_masks"] = [
        file_url(project_id, mask_path)
        for mask_path in foreground_masks
    ]

    retained_masks = state.get("retained_masks") or []
    files["retained_masks"] = [
        {
            "id": item.get("id"),
            "name": item.get("name"),
            "mask": file_url(project_id, item.get("mask")),
            "overlay": file_url(project_id, item.get("overlay")),
            "source": item.get("source"),
        }
        for item in retained_masks
    ]

    overlay_dir = project_dir(project_id) / "overlays"
    if state.get("subject_mask") and (overlay_dir / "subject_overlay.png").exists():
        files["subject_overlay"] = file_url(project_id, "overlays/subject_overlay.png")
    if state.get("final_mask") and (overlay_dir / "final_overlay.png").exists():
        files["final_overlay"] = file_url(project_id, "overlays/final_overlay.png")

    foreground_overlay_urls = []
    for index, _ in enumerate(foreground_masks):
        overlay = overlay_dir / f"foreground_{index:03d}_overlay.png"
        if overlay.exists():
            foreground_overlay_urls.append(file_url(project_id, f"overlays/{overlay.name}"))
    files["foreground_overlays"] = foreground_overlay_urls

    results = state.get("results") or {}
    if results:
        files["alpha"] = file_url(project_id, results.get("alpha"))
        files["foreground"] = file_url(project_id, results.get("foreground"))
        files["green"] = file_url(project_id, results.get("green"))
        files["replaced"] = file_url(project_id, results.get("replaced"))
        files["round_count"] = len(state.get("matting_rounds", []))

    target_files = []
    for target in state.get("targets", []):
        target_results = target.get("results") or {}
        target_files.append({
            "id": target.get("id"),
            "name": target.get("name"),
            "mask": file_url(project_id, target.get("mask")),
            "overlay": file_url(project_id, target.get("overlay")),
            "alpha": file_url(project_id, target_results.get("alpha")),
            "foreground": file_url(project_id, target_results.get("foreground")),
            "replaced": file_url(project_id, target_results.get("replaced")),
        })
    files["targets"] = target_files

    return files


def project_response(project_id, state):
    return {
        "project_id": project_id,
        "status": state_status(state),
        "files": state_files(project_id, state),
        "state": state,
    }


def resolve_file(project_id, relative_path):
    base = project_dir(project_id)
    target = (base / relative_path).resolve()
    if base not in target.parents and target != base:
        raise HTTPException(status_code=403, detail="非法文件路径")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return target
