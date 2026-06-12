"""
CLI entry point for SAM2.1 point-prompt service.

Usage:
  # Start the persistent server (blocking):
  python -m services.sam2_service.sam2_point_cli start \
      --checkpoint ~/matting/sam2/checkpoints/sam2.1_hiera_base_plus.pt

  # One-shot set_image (requires server running):
  python -m services.sam2_service.sam2_point_cli set-image \
      --project avatar_demo \
      --image ~/matting/projects/avatar_demo/inputs/first_frame.png

  # One-shot predict (requires server running, auto-saves mask + overlay):
  python -m services.sam2_service.sam2_point_cli predict \
      --project avatar_demo \
      --point 640 780 \
      --save-mask ~/matting/projects/avatar_demo/masks/retained_000.png \
      --save-overlay ~/matting/projects/avatar_demo/overlays/retained_000_overlay.png \
      --overlay-source ~/matting/projects/avatar_demo/inputs/first_frame.png
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import urllib.error


DEFAULT_PORT = 8765
BASE_URL = f"http://127.0.0.1:{DEFAULT_PORT}"


def _post(endpoint: str, data: dict) -> dict:
    url = f"{BASE_URL}{endpoint}"
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8") if exc.fp else str(exc)
        raise RuntimeError(f"HTTP {exc.code}: {err_body}")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Connection failed — is the SAM2 server running? ({exc})")


def _print_json(data: dict):
    print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_start(args):
    from services.sam2_service.sam2_point_server import main as server_main
    import sys as _sys
    # Forward args to the server
    _sys.argv = [
        "sam2_point_server",
        "--checkpoint", args.checkpoint,
        "--port", str(getattr(args, "port", DEFAULT_PORT)),
        "--device", getattr(args, "device", "cuda"),
    ]
    server_main()


def cmd_set_image(args):
    result = _post("/set_image", {
        "project_id": args.project,
        "image_path": args.image,
    })
    _print_json(result)


def cmd_predict(args):
    result = _post("/predict", {
        "project_id": args.project,
        "point": args.point,
        "label": getattr(args, "label", 1),
        "save_mask": args.save_mask,
        "save_overlay": args.save_overlay,
        "image_path_for_overlay": args.overlay_source,
    })
    _print_json(result)


def cmd_health(_args):
    result = _post("/health", {})
    _print_json(result)


def cmd_clear_image(args):
    result = _post("/clear_image", {"project_id": args.project})
    _print_json(result)


def cmd_shutdown(_args):
    try:
        result = _post("/shutdown", {})
        _print_json(result)
    except RuntimeError:
        pass  # server might close before sending response


def main():
    parser = argparse.ArgumentParser(description="SAM2.1 point-prompt CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("start", help="Start persistent SAM2 server (blocking)")
    p.add_argument("--checkpoint", required=True, help="Path to SAM2.1 checkpoint (.pt)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--device", default="cuda")

    p = sub.add_parser("set-image", help="Precompute image features for a project")
    p.add_argument("--project", required=True)
    p.add_argument("--image", required=True)

    p = sub.add_parser("predict", help="Run point prediction (saves mask + overlay)")
    p.add_argument("--project", required=True)
    p.add_argument("--point", nargs=2, type=int, required=True, help="x y pixel coordinates")
    p.add_argument("--label", type=int, default=1, help="1=foreground, 0=background")
    p.add_argument("--save-mask", required=True, help="Path to save mask PNG")
    p.add_argument("--save-overlay", required=True, help="Path to save overlay PNG")
    p.add_argument("--overlay-source", required=True, help="Original image for overlay generation")

    p = sub.add_parser("health")
    p = sub.add_parser("clear-image")
    p.add_argument("--project", required=True)
    p = sub.add_parser("shutdown")

    args = parser.parse_args()

    commands = {
        "start": cmd_start,
        "set-image": cmd_set_image,
        "predict": cmd_predict,
        "health": cmd_health,
        "clear-image": cmd_clear_image,
        "shutdown": cmd_shutdown,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
