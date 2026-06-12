"""
Mask registration helpers for the API server.

When SAM2 produces a mask, these functions save it to the project
directory, update state.json, and re-merge final.png — all within
the matting_api process (no conda subprocess needed).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image


def load_gray_mask(path: str | Path) -> np.ndarray:
    mask = Image.open(path).convert("L")
    return np.array(mask)


def binarize(mask: np.ndarray, threshold: int = 127) -> np.ndarray:
    return (mask > threshold).astype(np.uint8) * 255


def merge_or(masks: list[np.ndarray]) -> np.ndarray:
    if not masks:
        raise ValueError("No masks to merge")
    merged = np.zeros_like(masks[0], dtype=np.uint8)
    for m in masks:
        merged = np.maximum(merged, binarize(m))
    return merged


def save_mask(mask: np.ndarray, path: str | Path):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(binarize(mask)).save(p)


def save_overlay(
    image_path: str | Path,
    mask: np.ndarray,
    output_path: str | Path,
    color: tuple[int, int, int] = (0, 180, 255),
    alpha: float = 0.45,
):
    image = np.array(Image.open(image_path).convert("RGB"))
    mask_bin = binarize(mask) > 0
    overlay = image.copy()
    color_arr = np.array(color, dtype=np.uint8)
    overlay[mask_bin] = (
        image[mask_bin].astype(np.float32) * (1 - alpha)
        + color_arr.astype(np.float32) * alpha
    ).astype(np.uint8)
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(overlay).save(p)


def register_retained_mask(
    project_dir: str | Path,
    mask: np.ndarray,
    source: dict,
    mask_name: str | None = None,
) -> dict:
    """Add a retained mask to the project, update state.json, and re-merge final.png.

    Args:
        project_dir: Path to the project root (e.g. ~/matting/projects/avatar_demo)
        mask: Binary mask as numpy array (0/255, HxW)
        source: Dict describing how the mask was created, e.g.
                {"mode": "point", "point": [449, 1011]}
        mask_name: Human-readable label (auto-derived from source if None)

    Returns:
        The updated state dict.
    """
    project_dir = Path(project_dir)
    state_path = project_dir / "state.json"
    masks_dir = project_dir / "masks"
    overlays_dir = project_dir / "overlays"
    masks_dir.mkdir(parents=True, exist_ok=True)
    overlays_dir.mkdir(parents=True, exist_ok=True)

    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    first_frame_path = project_dir / "inputs" / "first_frame.png"

    # Push mask snapshot for undo
    state.setdefault("mask_snapshots", []).append({
        "subject_mask": state.get("subject_mask"),
        "foreground_masks": list(state.get("foreground_masks", [])),
        "retained_masks": list(state.get("retained_masks", [])),
        "final_mask": state.get("final_mask"),
    })

    # Save mask + overlay
    idx = len(state.get("retained_masks", []))
    mask_path = masks_dir / f"retained_{idx:03d}.png"
    overlay_path = overlays_dir / f"retained_{idx:03d}_overlay.png"

    save_mask(mask, mask_path)
    save_overlay(str(first_frame_path), mask, str(overlay_path), color=(0, 180, 255))

    # Determine name
    name = mask_name or _derive_name(source, idx)

    item = {
        "id": f"MASK_{idx + 1}",
        "name": name,
        "source": source,
        "mask": _to_project_path(project_dir, mask_path),
        "overlay": _to_project_path(project_dir, overlay_path),
    }
    state.setdefault("retained_masks", []).append(item)

    # History
    state.setdefault("history", []).append({
        "time": _now_iso(),
        "action": "add_retained_mask",
        "payload": item,
    })

    # Merge final
    _merge_final(project_dir, state)

    # Save state
    state["updated_at"] = _now_iso()
    state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))

    return state


def _merge_final(project_dir: Path, state: dict):
    retained = state.get("retained_masks", [])
    if not retained:
        state["final_mask"] = None
        return

    mask_paths = [
        project_dir / item["mask"]
        for item in retained
        if item.get("mask")
    ]
    masks = [load_gray_mask(p) for p in mask_paths if p.exists()]
    if not masks:
        state["final_mask"] = None
        return

    final = merge_or(masks)
    final_path = project_dir / "masks" / "final.png"
    overlay_path = project_dir / "overlays" / "final_overlay.png"
    first_frame = project_dir / "inputs" / "first_frame.png"

    save_mask(final, final_path)
    if first_frame.exists():
        save_overlay(str(first_frame), final, str(overlay_path), color=(0, 180, 255))

    state["final_mask"] = _to_project_path(project_dir, final_path)
    state.setdefault("history", []).append({
        "time": _now_iso(),
        "action": "merge_final",
        "payload": {"mask_count": len(masks)},
    })


def _to_project_path(project_dir: Path, path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(project_dir.resolve()))
    except ValueError:
        return str(path)


def _derive_name(source: dict, index: int) -> str:
    if source.get("mode") == "text" and source.get("text"):
        return source["text"]
    return f"MASK_{index + 1}"


def _now_iso() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")
