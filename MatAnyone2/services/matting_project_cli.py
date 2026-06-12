import argparse
import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image

from inference_matanyone2 import main as run_matanyone2
from services.matting_service.compose_bg import compose_solid_video, compose_video, max_alpha_videos


def load_state(project_dir):
    state_path = Path(project_dir) / "state.json"
    if not state_path.exists():
        raise FileNotFoundError(f"Missing state.json: {state_path}")
    return json.loads(state_path.read_text())


def save_state(project_dir, state):
    state_path = Path(project_dir) / "state.json"
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def to_project_path(project_dir, path):
    path = Path(path).resolve()
    try:
        return str(path.relative_to(project_dir))
    except ValueError:
        return str(path)


def find_one(pattern, directory):
    matches = sorted(Path(directory).glob(pattern))
    if not matches:
        raise FileNotFoundError(f"No file matched {pattern} in {directory}")
    return matches[-1]


def find_target(state, target_id):
    for target in state.get("targets", []):
        if target.get("id") == target_id:
            return target
    raise KeyError(f"Missing target: {target_id}")


def resolve_project_path(project_dir, value, fallback_inside_project=None):
    if value is None:
        return None

    path = Path(value)

    if path.is_absolute() and path.exists():
        return path

    if fallback_inside_project:
        candidate = project_dir / fallback_inside_project
        if candidate.exists():
            return candidate

    candidate = project_dir / path
    if candidate.exists():
        return candidate

    candidate = Path.cwd() / path
    if candidate.exists():
        return candidate

    return candidate


def mux_audio(video_with_no_audio, source_video, output_video):
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_with_no_audio),
        "-i",
        str(source_video),
        "-map",
        "0:v:0",
        "-map",
        "1:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        "-shortest",
        str(output_video),
    ]
    subprocess.run(cmd, check=True)


def build_preview_outputs(project_dir, state, alpha_paths, input_video):
    results_dir = project_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    alpha_out = results_dir / "alpha.mp4"
    green_no_audio = results_dir / "green_no_audio.mp4"
    green_out = results_dir / "green.mp4"

    print("[INFO] merging alpha rounds...")
    if len(alpha_paths) == 1:
        shutil.copy2(alpha_paths[0], alpha_out)
    else:
        max_alpha_videos(alpha_paths, alpha_out)

    print("[INFO] composing green screen preview...")
    compose_solid_video(input_video, alpha_out, green_no_audio)

    print("[INFO] muxing source audio...")
    try:
        mux_audio(green_no_audio, input_video, green_out)
    except Exception as exc:
        print(f"[WARN] green audio mux failed, keeping no-audio video: {exc}")
        shutil.copy2(green_no_audio, green_out)

    state["results"] = {
        "alpha": to_project_path(project_dir, alpha_out),
        "green": to_project_path(project_dir, green_out),
        "green_no_audio": to_project_path(project_dir, green_no_audio),
    }

    print(f"[DONE] cumulative alpha: {alpha_out}")
    print(f"[DONE] green: {green_out}")
    return state


def rebuild_from_rounds(project_dir, state):
    input_video = resolve_project_path(project_dir, state["video"], "inputs/input.mp4")

    if not input_video.exists():
        raise FileNotFoundError(f"Missing input video: {input_video}")

    alpha_paths = [
        resolve_project_path(project_dir, item["round_alpha"])
        for item in state.get("matting_rounds", [])
    ]
    alpha_paths = [path for path in alpha_paths if path.exists()]

    if not alpha_paths:
        state.pop("results", None)
        save_state(project_dir, state)
        print("[DONE] no matting rounds remain")
        return state

    state = build_preview_outputs(project_dir, state, alpha_paths, input_video)
    save_state(project_dir, state)
    return state


def compose_background(args):
    project_dir = Path(args.project).resolve()
    state = load_state(project_dir)

    input_video = resolve_project_path(project_dir, state["video"], "inputs/input.mp4")
    results = state.get("results") or {}
    alpha = resolve_project_path(project_dir, results.get("alpha"), "results/alpha.mp4")

    if args.background:
        uploaded_background = Path(args.background).expanduser().resolve()
        if not uploaded_background.exists():
            raise FileNotFoundError(f"Missing background: {uploaded_background}")
        background = project_dir / "inputs" / "background.png"
        background.parent.mkdir(parents=True, exist_ok=True)
        Image.open(uploaded_background).convert("RGB").save(background)
        state["background"] = to_project_path(project_dir, background)
    else:
        background = resolve_project_path(project_dir, state.get("background"), "inputs/background.png")

    if not input_video.exists():
        raise FileNotFoundError(f"Missing input video: {input_video}")
    if not alpha.exists():
        raise FileNotFoundError(f"Missing alpha: {alpha}")
    if not background or not background.exists():
        raise FileNotFoundError(f"Missing background: {background}")

    results_dir = project_dir / "results"
    replaced_no_audio = results_dir / "replaced_no_audio.mp4"
    replaced_out = results_dir / "replaced.mp4"
    results_dir.mkdir(parents=True, exist_ok=True)

    print("[INFO] composing uploaded background...")
    compose_video(input_video, alpha, background, replaced_no_audio)

    print("[INFO] muxing source audio...")
    try:
        mux_audio(replaced_no_audio, input_video, replaced_out)
    except Exception as exc:
        print(f"[WARN] replaced audio mux failed, keeping no-audio video: {exc}")
        shutil.copy2(replaced_no_audio, replaced_out)

    state.setdefault("results", {}).update({
        "replaced": to_project_path(project_dir, replaced_out),
        "replaced_no_audio": to_project_path(project_dir, replaced_no_audio),
    })
    save_state(project_dir, state)

    print(f"[DONE] replaced: {replaced_out}")
    print(json.dumps(state, indent=2, ensure_ascii=False))
    return state


def undo_round(args):
    project_dir = Path(args.project).resolve()
    state = load_state(project_dir)
    rounds = state.get("matting_rounds", [])

    if not rounds:
        print("[WARN] no matting round to undo")
        print(json.dumps(state, indent=2, ensure_ascii=False))
        return

    removed = rounds.pop()
    state["matting_rounds"] = rounds
    state.setdefault("matting_history", []).append({
        "action": "undo_round",
        "removed": removed.get("id"),
    })
    state = rebuild_from_rounds(project_dir, state)
    print(json.dumps(state, indent=2, ensure_ascii=False))


def run_project(args):
    project_dir = Path(args.project).resolve()
    state = load_state(project_dir)

    input_video = resolve_project_path(project_dir, state["video"], "inputs/input.mp4")

    target = None
    if args.target_id:
        target = find_target(state, args.target_id)
        mask_value = target["mask"]
        mask_fallback = f"targets/{args.target_id}/mask.png"
        suffix = args.target_id
    else:
        mask_value = state["final_mask"]
        mask_fallback = "masks/final.png"
        suffix = args.suffix

    final_mask = resolve_project_path(project_dir, mask_value, mask_fallback)

    if not input_video.exists():
        raise FileNotFoundError(f"Missing input video: {input_video}")
    if not final_mask.exists():
        raise FileNotFoundError(f"Missing final mask: {final_mask}")

    if args.target_id:
        results_dir = project_dir / "targets" / args.target_id / "results"
    else:
        results_dir = project_dir / "results"
    matanyone_dir = results_dir / "matanyone2_raw"
    results_dir.mkdir(parents=True, exist_ok=True)
    matanyone_dir.mkdir(parents=True, exist_ok=True)

    print("[INFO] running MatAnyone2...")
    run_matanyone2(
        input_path=str(input_video),
        mask_path=str(final_mask),
        output_path=str(matanyone_dir),
        ckpt_path=args.ckpt,
        n_warmup=args.warmup,
        r_erode=args.erode,
        r_dilate=args.dilate,
        suffix=suffix,
        save_image=args.save_image,
        max_size=args.max_size,
    )

    raw_alpha = find_one("*_pha.mp4", matanyone_dir)
    raw_foreground = find_one("*_fgr.mp4", matanyone_dir)

    if target is not None:
        background = resolve_project_path(project_dir, state.get("background"), "inputs/background.png")
        if not background or not background.exists():
            raise FileNotFoundError(f"Missing background: {background}")

        alpha_out = results_dir / "alpha.mp4"
        foreground_out = results_dir / "foreground.mp4"
        replaced_no_audio = results_dir / "replaced_no_audio.mp4"
        replaced_out = results_dir / "replaced.mp4"

        shutil.copy2(raw_alpha, alpha_out)
        shutil.copy2(raw_foreground, foreground_out)

        print("[INFO] composing uploaded background...")
        compose_video(input_video, alpha_out, background, replaced_no_audio)

        print("[INFO] muxing source audio...")
        try:
            mux_audio(replaced_no_audio, input_video, replaced_out)
        except Exception as exc:
            print(f"[WARN] audio mux failed, keeping no-audio video: {exc}")
            shutil.copy2(replaced_no_audio, replaced_out)

        target["results"] = {
            "alpha": to_project_path(project_dir, alpha_out),
            "foreground": to_project_path(project_dir, foreground_out),
            "replaced": to_project_path(project_dir, replaced_out),
            "replaced_no_audio": to_project_path(project_dir, replaced_no_audio),
            "matanyone2_raw_dir": to_project_path(project_dir, matanyone_dir),
        }
        save_state(project_dir, state)
        print(f"[DONE] alpha: {alpha_out}")
        print(f"[DONE] foreground: {foreground_out}")
        print(f"[DONE] replaced: {replaced_out}")
        return

    rounds = state.setdefault("matting_rounds", [])
    round_id = f"round_{len(rounds):03d}"
    round_dir = project_dir / "rounds" / round_id
    round_dir.mkdir(parents=True, exist_ok=True)

    round_alpha = round_dir / "alpha.mp4"
    round_foreground = round_dir / "foreground.mp4"

    shutil.copy2(raw_alpha, round_alpha)
    shutil.copy2(raw_foreground, round_foreground)

    round_results = {
        "id": round_id,
        "source_mask": to_project_path(project_dir, final_mask),
        "round_alpha": to_project_path(project_dir, round_alpha),
        "foreground": to_project_path(project_dir, round_foreground),
        "matanyone2_raw_dir": to_project_path(project_dir, matanyone_dir),
    }
    rounds.append(round_results)
    alpha_paths = [
        resolve_project_path(project_dir, item["round_alpha"])
        for item in rounds
    ]
    state = build_preview_outputs(project_dir, state, alpha_paths, input_video)
    state["results"]["foreground"] = to_project_path(project_dir, round_foreground)

    save_state(project_dir, state)

    print(f"[DONE] round: {round_id}")
    print(f"[DONE] round alpha: {round_alpha}")
    print(f"[DONE] foreground: {round_foreground}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--ckpt", default="pretrained_models/matanyone2.pth")
    parser.add_argument("--warmup", default="10")
    parser.add_argument("--erode", default="10")
    parser.add_argument("--dilate", default="10")
    parser.add_argument("--suffix", default="final")
    parser.add_argument("--max-size", default="-1")
    parser.add_argument("--save-image", action="store_true")
    parser.add_argument("--target-id", default=None)
    parser.add_argument("--undo-round", action="store_true")
    parser.add_argument("--compose-background", action="store_true")
    parser.add_argument("--background", default=None)

    args = parser.parse_args()
    if args.undo_round:
        undo_round(args)
        return
    if args.compose_background:
        compose_background(args)
        return

    run_project(args)


if __name__ == "__main__":
    main()
