#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-$HOME/matting}"
PROJECT="${PROJECT:-$ROOT/projects/avatar_smoke}"
VIDEO="${VIDEO:-$ROOT/MatAnyone2/inputs/video/avatar.mp4}"
BACKGROUND="${BACKGROUND:-$ROOT/MatAnyone2/inputs/bg.png}"
SAM_CKPT="${SAM_CKPT:-$ROOT/sam3/models/sam3.1/sam3.1_multiplex.pt}"

echo "[INFO] root: $ROOT"
echo "[INFO] project: $PROJECT"

echo "[INFO] init project"
cd "$ROOT/sam3"
conda run -n sam3 python -m services.mask_service_cli init \
  --project "$PROJECT" \
  --video "$VIDEO" \
  --background "$BACKGROUND"

echo "[INFO] add retained object: person"
conda run -n sam3 python -m services.mask_service_cli add-mask-text \
  --project "$PROJECT" \
  --checkpoint "$SAM_CKPT" \
  --text "person"

echo "[INFO] add retained object: desk"
conda run -n sam3 python -m services.mask_service_cli add-mask-text \
  --project "$PROJECT" \
  --checkpoint "$SAM_CKPT" \
  --text "desk"

echo "[INFO] run MatAnyone2"
cd "$ROOT/MatAnyone2"
conda run -n matanyone2 python -m services.matting_project_cli \
  --project "$PROJECT"

echo "[DONE] results:"
find "$PROJECT/results" -maxdepth 2 -type f | sort
