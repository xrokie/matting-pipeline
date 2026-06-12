import argparse
import cv2
import numpy as np

def cover_resize(img, w, h):
    ih, iw = img.shape[:2]
    scale = max(w / iw, h / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    x = (nw - w) // 2
    y = (nh - h) // 2
    return img[y:y+h, x:x+w]

ap = argparse.ArgumentParser()
ap.add_argument("--video", required=True)
ap.add_argument("--alpha", required=True)
ap.add_argument("--background", required=True)
ap.add_argument("--output", required=True)
args = ap.parse_args()

vc = cv2.VideoCapture(args.video)
ac = cv2.VideoCapture(args.alpha)

fps = vc.get(cv2.CAP_PROP_FPS) or 25
w = int(vc.get(cv2.CAP_PROP_FRAME_WIDTH))
h = int(vc.get(cv2.CAP_PROP_FRAME_HEIGHT))

bg = cv2.imread(args.background, cv2.IMREAD_COLOR)
if bg is None:
    raise FileNotFoundError(args.background)
bg = cover_resize(bg, w, h)

writer = cv2.VideoWriter(
    args.output,
    cv2.VideoWriter_fourcc(*"mp4v"),
    fps,
    (w, h),
)

while True:
    ok_v, frame = vc.read()
    ok_a, alpha_frame = ac.read()
    if not ok_v or not ok_a:
        break

    alpha = cv2.cvtColor(alpha_frame, cv2.COLOR_BGR2GRAY)
    alpha = cv2.resize(alpha, (w, h), interpolation=cv2.INTER_LINEAR)
    alpha = cv2.GaussianBlur(alpha, (0, 0), 0.5).astype(np.float32) / 255.0
    alpha = alpha[..., None]

    comp = frame.astype(np.float32) * alpha + bg.astype(np.float32) * (1.0 - alpha)
    writer.write(np.clip(comp, 0, 255).astype(np.uint8))

vc.release()
ac.release()
writer.release()
