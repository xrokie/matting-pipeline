"""
SAM2.1 persistent point-prompt server.

Runs as a long-lived HTTP service on 127.0.0.1:8765.
Loads the SAM2.1 model once at startup and keeps it resident in GPU memory.

Endpoints:
  POST /set_image   - precompute image features for a project
  POST /predict     - run point-prompt prediction, save mask + overlay
  GET  /health      - health check
  POST /shutdown    - graceful shutdown (optional)

All responses are JSON.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Lock

import numpy as np
import torch
from PIL import Image

from sam2.build_sam import build_sam2
from sam2.sam2_image_predictor import SAM2ImagePredictor


class SAM2PointPredictor:
    """Manages SAM2.1 model lifecycle and inference."""

    def __init__(self, checkpoint_path: str, device: str = "cuda"):
        self.checkpoint_path = checkpoint_path
        self.device = device
        self.model = None
        self.predictor = None
        self._image_cache: dict[str, dict] = {}  # project_id -> {image, features}
        self._lock = Lock()

    def load(self):
        if self.model is not None:
            return
        log("Loading SAM2.1 model...")
        t0 = time.time()
        self.model = build_sam2(
            "configs/sam2.1/sam2.1_hiera_b+.yaml",
            self.checkpoint_path,
            device=self.device,
        )
        self.predictor = SAM2ImagePredictor(self.model)
        # CUDA warmup: run a dummy predict to trigger JIT compilation
        log("Warming up CUDA kernels...")
        dummy = np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8)
        dummy_img = Image.fromarray(dummy)
        with torch.inference_mode(), torch.autocast(self.device, dtype=torch.bfloat16):
            self.predictor.set_image(dummy_img)
            self.predictor.predict(
                point_coords=np.array([[128, 128]]),
                point_labels=np.array([1]),
                multimask_output=False,
            )
        log(f"Model ready in {time.time() - t0:.1f}s, GPU memory: {torch.cuda.max_memory_allocated() / 1024 ** 3:.1f} GB")

    def set_image(self, project_id: str, image_path: str):
        self.load()
        image_path = Path(image_path).expanduser().resolve()
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        image = Image.open(image_path).convert("RGB")
        with self._lock:
            with torch.inference_mode(), torch.autocast(self.device, dtype=torch.bfloat16):
                self.predictor.set_image(image)
            self._image_cache[project_id] = {
                "image": image,
                "image_path": str(image_path),
                "width": image.size[0],
                "height": image.size[1],
            }
        log(f"set_image: {project_id} <- {image_path}  ({image.size[0]}x{image.size[1]})")

    def predict(self, project_id: str, point: list[int, int], label: int = 1) -> dict:
        self.load()
        cache = self._image_cache.get(project_id)
        if cache is None:
            raise RuntimeError(f"No image set for project '{project_id}'. Call /set_image first.")

        x, y = point
        if not (0 <= x <= cache["width"] and 0 <= y <= cache["height"]):
            raise ValueError(f"Point ({x}, {y}) out of bounds ({cache['width']}x{cache['height']})")

        with self._lock:
            with torch.inference_mode(), torch.autocast(self.device, dtype=torch.bfloat16):
                masks, scores, _ = self.predictor.predict(
                    point_coords=np.array([[x, y]]),
                    point_labels=np.array([label]),
                    multimask_output=True,
                )

        best_idx = int(np.argmax(scores))
        mask = (masks[best_idx] > 0).astype(np.uint8) * 255
        foreground_pixels = int(mask.sum() // 255)

        return {
            "mask": mask,
            "mask_array": mask.tobytes(),
            "shape": list(mask.shape),
            "score": float(scores[best_idx]),
            "all_scores": [float(s) for s in scores],
            "foreground_pixels": foreground_pixels,
        }

    def clear_image(self, project_id: str):
        self._image_cache.pop(project_id, None)

    def health(self) -> dict:
        return {
            "status": "ok" if self.model is not None else "not_loaded",
            "device": self.device,
            "cached_projects": list(self._image_cache.keys()),
            "gpu_memory_gb": round(torch.cuda.max_memory_allocated() / 1024**3, 2) if torch.cuda.is_available() else 0,
        }


# ----- HTTP handler -----

_predictor: SAM2PointPredictor | None = None


def get_predictor() -> SAM2PointPredictor:
    global _predictor
    if _predictor is None:
        raise RuntimeError("Server not initialized")
    return _predictor


class RequestHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        log(fmt % args)

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw)

    def do_GET(self):
        if self.path == "/health":
            try:
                pred = get_predictor()
                self._send_json(pred.health())
            except Exception as exc:
                self._send_json({"status": "error", "message": str(exc)}, 500)
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        try:
            body = self._read_json()
            pred = get_predictor()

            if self.path == "/set_image":
                project_id = body["project_id"]
                image_path = body["image_path"]
                pred.set_image(project_id, image_path)
                self._send_json({"status": "ok", "project_id": project_id})

            elif self.path == "/predict":
                project_id = body["project_id"]
                point = body["point"]
                label = body.get("label", 1)
                result = pred.predict(project_id, point, label)
                # Don't send the raw mask array in JSON — save to file instead
                mask_path = body.get("save_mask")
                overlay_path = body.get("save_overlay")
                image_path = body.get("image_path_for_overlay")
                if mask_path:
                    _save_mask_file(result["mask"], mask_path, body.get("binarize_threshold", 127))
                    result["mask_path"] = mask_path
                if overlay_path and image_path:
                    _save_overlay_file(image_path, result["mask"], overlay_path)
                    result["overlay_path"] = overlay_path
                # Remove heavy binary data from response
                result.pop("mask", None)
                result.pop("mask_array", None)
                self._send_json(result)

            elif self.path == "/clear_image":
                project_id = body.get("project_id", "")
                pred.clear_image(project_id)
                self._send_json({"status": "ok"})

            elif self.path == "/shutdown":
                self._send_json({"status": "shutting_down"})
                sys.exit(0)

            else:
                self._send_json({"error": f"unknown endpoint: {self.path}"}, 404)

        except Exception as exc:
            traceback.print_exc()
            self._send_json({"error": str(exc), "traceback": traceback.format_exc()}, 500)


# ----- helpers (minimal, no dependency on sam3/tools) -----

def _save_mask_file(mask: np.ndarray, path: str, threshold: int = 127):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    binary = (mask > threshold).astype(np.uint8) * 255
    Image.fromarray(binary).save(p)


def _save_overlay_file(image_path: str, mask: np.ndarray, output_path: str, alpha: float = 0.45):
    image = np.array(Image.open(image_path).convert("RGB"))
    mask_bin = (mask > 127) if mask.dtype == np.uint8 else mask

    # Resize mask to match image dimensions if needed.
    # SAM2 returns masks at the resolution passed to set_image(), but the
    # overlay source image may have been regenerated at a different size.
    if mask_bin.shape[:2] != image.shape[:2]:
        h_img, w_img = image.shape[:2]
        h_mask, w_mask = mask_bin.shape[:2]
        # Check for width/height swap (common with portrait video)
        if (h_mask, w_mask) == (w_img, h_img):
            mask_bin = mask_bin.T
        else:
            mask_img = Image.fromarray(mask_bin.astype(np.uint8))
            mask_img = mask_img.resize((w_img, h_img), Image.Resampling.NEAREST)
            mask_bin = np.array(mask_img) > 0

    overlay = image.copy()
    color = np.array([0, 180, 255], dtype=np.uint8)  # blue tint for SAM2 masks
    overlay[mask_bin] = (
        image[mask_bin].astype(np.float32) * (1 - alpha)
        + color.astype(np.float32) * alpha
    ).astype(np.uint8)
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(overlay).save(p)


def log(msg: str):
    print(f"[sam2-server] {msg}", file=sys.stderr, flush=True)


# ----- main -----

def main():
    parser = argparse.ArgumentParser(description="SAM2.1 persistent point-prompt server")
    parser.add_argument("--checkpoint", required=True, help="Path to SAM2.1 checkpoint")
    parser.add_argument("--port", type=int, default=8765, help="Listen port (default: 8765)")
    parser.add_argument("--device", default="cuda", help="Device (default: cuda)")
    args = parser.parse_args()

    global _predictor
    _predictor = SAM2PointPredictor(checkpoint_path=args.checkpoint, device=args.device)
    _predictor.load()

    server = HTTPServer(("127.0.0.1", args.port), RequestHandler)
    log(f"SAM2 point server listening on http://127.0.0.1:{args.port}")
    log(f"Endpoints: /health /set_image /predict /clear_image /shutdown")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        log("Shutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
