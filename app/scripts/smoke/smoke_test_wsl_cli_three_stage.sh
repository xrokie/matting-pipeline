#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-$HOME/matting}"
PROJECT="${PROJECT:-$ROOT/projects/avatar_cli_three_stage_$(date +%Y%m%d_%H%M%S)}"
VIDEO="${VIDEO:-$ROOT/MatAnyone2/inputs/video/avatar.mp4}"
BACKGROUND="${BACKGROUND:-$ROOT/MatAnyone2/inputs/bg.png}"
SAM_CKPT="${SAM_CKPT:-$ROOT/sam3/models/sam3.1/sam3.1_multiplex.pt}"
MATANYONE_CKPT="${MATANYONE_CKPT:-$ROOT/MatAnyone2/pretrained_models/matanyone2.pth}"
SUBJECT_POINT_X="${SUBJECT_POINT_X:-}"
SUBJECT_POINT_Y="${SUBJECT_POINT_Y:-}"
MAX_SIZE="${MAX_SIZE:-720}"

png_center() {
  python3 - "$1" <<'PY'
import struct
import sys

with open(sys.argv[1], "rb") as f:
    sig = f.read(8)
    if sig != b"\x89PNG\r\n\x1a\n":
        raise SystemExit("first frame is not a PNG")
    length = struct.unpack(">I", f.read(4))[0]
    chunk = f.read(4)
    if chunk != b"IHDR" or length < 8:
        raise SystemExit("PNG IHDR not found")
    width, height = struct.unpack(">II", f.read(8))
print(f"{width // 2} {height // 2}")
PY
}

echo "[INFO] root: $ROOT"
echo "[INFO] project: $PROJECT"
command -v python3 >/dev/null || { echo "[ERROR] python3 not found"; exit 1; }

echo "[INFO] sync service wrappers"
bash "$ROOT/app/scripts/sync_services.sh"

echo "[INFO] init project with video only"
cd "$ROOT/sam3"
conda run --no-capture-output -n sam3 python -m services.mask_service_cli init \
  --project "$PROJECT" \
  --video "$VIDEO"

if [[ -z "$SUBJECT_POINT_X" || -z "$SUBJECT_POINT_Y" ]]; then
  read -r SUBJECT_POINT_X SUBJECT_POINT_Y < <(png_center "$PROJECT/inputs/first_frame.png")
fi
echo "[INFO] retained object point: $SUBJECT_POINT_X,$SUBJECT_POINT_Y"

echo "[INFO] add retained object by point"
conda run --no-capture-output -n sam3 python -m services.mask_service_cli add-mask-point \
  --project "$PROJECT" \
  --checkpoint "$SAM_CKPT" \
  --point "$SUBJECT_POINT_X" "$SUBJECT_POINT_Y"

echo "[INFO] undo mask"
conda run --no-capture-output -n sam3 python -m services.mask_service_cli undo-mask \
  --project "$PROJECT"

echo "[INFO] add retained object by point again"
conda run --no-capture-output -n sam3 python -m services.mask_service_cli add-mask-point \
  --project "$PROJECT" \
  --checkpoint "$SAM_CKPT" \
  --point "$SUBJECT_POINT_X" "$SUBJECT_POINT_Y"

echo "[INFO] run MatAnyone2 green-screen matting"
cd "$ROOT/MatAnyone2"
conda run --no-capture-output -n matanyone2 python -m services.matting_project_cli \
  --project "$PROJECT" \
  --ckpt "$MATANYONE_CKPT" \
  --max-size "$MAX_SIZE"

echo "[INFO] compose uploaded background without rerunning matting"
conda run --no-capture-output -n matanyone2 python -m services.matting_project_cli \
  --project "$PROJECT" \
  --compose-background \
  --background "$BACKGROUND"

echo "[DONE] results:"
find "$PROJECT" -maxdepth 3 -type f \
  \( -path "*/inputs/*" -o -path "*/masks/*" -o -path "*/overlays/*" -o -path "*/results/*" -o -path "*/rounds/*" \) \
  | sort
