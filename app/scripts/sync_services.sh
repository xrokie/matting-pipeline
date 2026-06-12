#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-$HOME/matting}"

RSYNC_EXCLUDES=(
  --exclude ".DS_Store"
  --exclude "._*"
  --exclude "__pycache__/"
  --exclude "*.pyc"
  --exclude "*.pt"
  --exclude "*.pth"
)

echo "[INFO] syncing SAM3 service wrapper"
rsync -av --delete "${RSYNC_EXCLUDES[@]}" \
  "$ROOT/app/sam3/services/" \
  "$ROOT/sam3/services/"

echo "[INFO] syncing SAM3 helper tools"
rsync -av --delete "${RSYNC_EXCLUDES[@]}" \
  "$ROOT/app/sam3/tools/" \
  "$ROOT/sam3/tools/"

echo "[INFO] syncing MatAnyone2 service wrapper"
rsync -av --delete "${RSYNC_EXCLUDES[@]}" \
  "$ROOT/app/MatAnyone2/services/" \
  "$ROOT/MatAnyone2/services/"

echo "[DONE] service wrappers are in sync"
