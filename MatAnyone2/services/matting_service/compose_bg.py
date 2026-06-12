from pathlib import Path

import cv2
import numpy as np


def cover_resize(image, target_w, target_h):
    h, w = image.shape[:2]
    scale = max(target_w / w, target_h / h)
    new_w = int(round(w * scale))
    new_h = int(round(h * scale))

    resized = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    x0 = max(0, (new_w - target_w) // 2)
    y0 = max(0, (new_h - target_h) // 2)

    return resized[y0:y0 + target_h, x0:x0 + target_w]


def compose_video(video_path, alpha_path, background_path, output_path):
    video_path = str(video_path)
    alpha_path = str(alpha_path)
    background_path = str(background_path)
    output_path = str(output_path)

    video_cap = cv2.VideoCapture(video_path)
    alpha_cap = cv2.VideoCapture(alpha_path)

    if not video_cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    if not alpha_cap.isOpened():
        raise RuntimeError(f"Cannot open alpha: {alpha_path}")

    fps = video_cap.get(cv2.CAP_PROP_FPS)
    width = int(video_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(video_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    bg = cv2.imread(background_path, cv2.IMREAD_COLOR)
    if bg is None:
        raise RuntimeError(f"Cannot read background: {background_path}")
    bg = cover_resize(bg, width, height)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    frame_idx = 0

    while True:
        ok_v, frame = video_cap.read()
        ok_a, alpha_frame = alpha_cap.read()

        if not ok_v or not ok_a:
            break

        if alpha_frame.shape[:2] != (height, width):
            alpha_frame = cv2.resize(alpha_frame, (width, height), interpolation=cv2.INTER_LINEAR)

        alpha_gray = cv2.cvtColor(alpha_frame, cv2.COLOR_BGR2GRAY)
        alpha = alpha_gray.astype(np.float32) / 255.0
        alpha = alpha[..., None]

        comp = frame.astype(np.float32) * alpha + bg.astype(np.float32) * (1.0 - alpha)
        comp = np.clip(comp, 0, 255).astype(np.uint8)

        writer.write(comp)
        frame_idx += 1

    video_cap.release()
    alpha_cap.release()
    writer.release()

    if frame_idx == 0:
        raise RuntimeError("No frames were composed")

    print(f"[DONE] composed frames: {frame_idx}")
    print(f"[DONE] output: {output_path}")


def compose_solid_video(video_path, alpha_path, output_path, color=(0, 255, 0)):
    video_path = str(video_path)
    alpha_path = str(alpha_path)
    output_path = str(output_path)

    video_cap = cv2.VideoCapture(video_path)
    alpha_cap = cv2.VideoCapture(alpha_path)

    if not video_cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    if not alpha_cap.isOpened():
        raise RuntimeError(f"Cannot open alpha: {alpha_path}")

    fps = video_cap.get(cv2.CAP_PROP_FPS)
    width = int(video_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(video_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    background = np.zeros((height, width, 3), dtype=np.uint8)
    background[:, :] = np.array(color, dtype=np.uint8)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    frame_idx = 0

    while True:
        ok_v, frame = video_cap.read()
        ok_a, alpha_frame = alpha_cap.read()

        if not ok_v or not ok_a:
            break

        if alpha_frame.shape[:2] != (height, width):
            alpha_frame = cv2.resize(alpha_frame, (width, height), interpolation=cv2.INTER_LINEAR)

        alpha_gray = cv2.cvtColor(alpha_frame, cv2.COLOR_BGR2GRAY)
        alpha = alpha_gray.astype(np.float32) / 255.0
        alpha = alpha[..., None]

        comp = frame.astype(np.float32) * alpha + background.astype(np.float32) * (1.0 - alpha)
        comp = np.clip(comp, 0, 255).astype(np.uint8)

        writer.write(comp)
        frame_idx += 1

    video_cap.release()
    alpha_cap.release()
    writer.release()

    if frame_idx == 0:
        raise RuntimeError("No frames were composed")

    print(f"[DONE] composed green frames: {frame_idx}")
    print(f"[DONE] output: {output_path}")


def max_alpha_videos(alpha_paths, output_path):
    alpha_paths = [str(path) for path in alpha_paths]
    output_path = str(output_path)

    if not alpha_paths:
        raise RuntimeError("No alpha videos to merge")

    caps = [cv2.VideoCapture(path) for path in alpha_paths]
    for path, cap in zip(alpha_paths, caps):
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open alpha: {path}")

    fps = caps[0].get(cv2.CAP_PROP_FPS)
    width = int(caps[0].get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(caps[0].get(cv2.CAP_PROP_FRAME_HEIGHT))

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    frame_idx = 0

    while True:
        max_gray = None

        for index, cap in enumerate(caps):
            ok, frame = cap.read()
            if not ok:
                if index == 0:
                    max_gray = None
                    break
                gray = np.zeros((height, width), dtype=np.uint8)
            else:
                if frame.shape[:2] != (height, width):
                    frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_LINEAR)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            max_gray = gray if max_gray is None else np.maximum(max_gray, gray)

        if max_gray is None:
            break

        writer.write(cv2.cvtColor(max_gray, cv2.COLOR_GRAY2BGR))
        frame_idx += 1

    for cap in caps:
        cap.release()
    writer.release()

    if frame_idx == 0:
        raise RuntimeError("No alpha frames were merged")

    print(f"[DONE] merged alpha frames: {frame_idx}")
    print(f"[DONE] output: {output_path}")
