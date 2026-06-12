from pathlib import Path
import numpy as np
from PIL import Image


def load_gray_mask(path):
    mask = Image.open(path).convert("L")
    return np.array(mask)


def binarize(mask, threshold=127):
    return (mask > threshold).astype(np.uint8) * 255


def merge_or(masks):
    if not masks:
        raise ValueError("No masks to merge")
    merged = np.zeros_like(masks[0], dtype=np.uint8)
    for mask in masks:
        merged = np.maximum(merged, binarize(mask))
    return merged


def save_mask(mask, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(binarize(mask)).save(path)


def save_overlay(image_path, mask, output_path, color=(0, 255, 0), alpha=0.45):
    image = np.array(Image.open(image_path).convert("RGB"))
    mask_bin = binarize(mask) > 0

    overlay = image.copy()
    color_arr = np.array(color, dtype=np.uint8)

    overlay[mask_bin] = (
        image[mask_bin].astype(np.float32) * (1 - alpha)
        + color_arr.astype(np.float32) * alpha
    ).astype(np.uint8)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(overlay).save(output_path)


def resize_mask_to_image(mask, image_path):
    image = Image.open(image_path)
    w, h = image.size
    if mask.shape[:2] == (h, w):
        return mask

    mask_img = Image.fromarray(mask).convert("L")
    mask_img = mask_img.resize((w, h), Image.Resampling.NEAREST)
    return np.array(mask_img)
