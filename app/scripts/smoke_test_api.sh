#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-$HOME/matting}"
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
PROJECT_ID="${PROJECT_ID:-avatar_demo}"
VIDEO="${VIDEO:-$ROOT/MatAnyone2/inputs/video/avatar.mp4}"
BACKGROUND="${BACKGROUND:-$ROOT/MatAnyone2/inputs/bg.png}"

echo "[INFO] health"
curl -sS "$BASE_URL/health"
echo

echo "[INFO] create project"
curl -sS -X POST "$BASE_URL/api/projects" \
  -F "project_id=$PROJECT_ID" \
  -F "video=@$VIDEO" \
  -F "background=@$BACKGROUND"
echo

echo "[INFO] add retained object: person"
curl -sS -X POST "$BASE_URL/api/projects/$PROJECT_ID/masks/text" \
  -H "Content-Type: application/json" \
  -d '{"text":"person"}'
echo

echo "[INFO] add retained object: desk"
curl -sS -X POST "$BASE_URL/api/projects/$PROJECT_ID/masks/text" \
  -H "Content-Type: application/json" \
  -d '{"text":"desk"}'
echo

echo "[INFO] start matting job"
curl -sS -X POST "$BASE_URL/api/projects/$PROJECT_ID/matting" \
  -H "Content-Type: application/json" \
  -d '{"warmup":10,"erode":10,"dilate":10,"max_size":-1,"save_image":false}'
echo

echo "[INFO] poll the returned job id manually with:"
echo "curl $BASE_URL/api/jobs/{job_id}"
