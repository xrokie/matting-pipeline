#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-$HOME/matting}"
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
PROJECT_ID="${PROJECT_ID:-avatar_three_stage_$(date +%Y%m%d_%H%M%S)}"
VIDEO="${VIDEO:-$ROOT/MatAnyone2/inputs/video/avatar.mp4}"
BACKGROUND="${BACKGROUND:-$ROOT/MatAnyone2/inputs/bg.png}"
SUBJECT_POINT_X="${SUBJECT_POINT_X:-}"
SUBJECT_POINT_Y="${SUBJECT_POINT_Y:-}"
MAX_SIZE="${MAX_SIZE:-720}"
WORK_DIR="${WORK_DIR:-/tmp/matting_api_smoke}"

mkdir -p "$WORK_DIR"
command -v curl >/dev/null || { echo "[ERROR] curl not found"; exit 1; }
command -v python3 >/dev/null || { echo "[ERROR] python3 not found"; exit 1; }

json_get() {
  python3 - "$1" "$2" <<'PY'
import json
import sys

path, expr = sys.argv[1], sys.argv[2]
data = json.load(open(path, encoding="utf-8"))
value = data
for part in expr.split("."):
    if part == "":
        continue
    value = value[part]
if value is None:
    print("")
else:
    print(value)
PY
}

poll_job() {
  local job_id="$1"
  local out_file="$2"

  while true; do
    curl -sS "$BASE_URL/api/jobs/$job_id" > "$out_file"
    local status
    status="$(json_get "$out_file" status)"
    local progress
    progress="$(json_get "$out_file" progress)"
    local message
    message="$(json_get "$out_file" message)"
    echo "[INFO] job=$job_id status=$status progress=$progress message=$message"

    if [[ "$status" == "succeeded" ]]; then
      return 0
    fi
    if [[ "$status" == "failed" ]]; then
      echo "[ERROR] job failed:"
      cat "$out_file"
      exit 1
    fi
    sleep 3
  done
}

check_file_url() {
  local path="$1"
  if [[ -z "$path" ]]; then
    echo "[ERROR] missing file URL"
    exit 1
  fi
  curl -fsSL "$BASE_URL$path" -o /dev/null
  echo "[OK] reachable: $path"
}

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

echo "[INFO] health"
curl -sS "$BASE_URL/health" > "$WORK_DIR/health.json"
cat "$WORK_DIR/health.json"
echo

echo "[INFO] create project with video only: $PROJECT_ID"
curl -sS -X POST "$BASE_URL/api/projects" \
  -F "project_id=$PROJECT_ID" \
  -F "video=@$VIDEO" > "$WORK_DIR/create.json"
PROJECT_ID="$(json_get "$WORK_DIR/create.json" project_id)"
FIRST_FRAME_URL="$(json_get "$WORK_DIR/create.json" files.first_frame)"
check_file_url "$FIRST_FRAME_URL"
curl -fsSL "$BASE_URL$FIRST_FRAME_URL" -o "$WORK_DIR/first_frame.png"
if [[ -z "$SUBJECT_POINT_X" || -z "$SUBJECT_POINT_Y" ]]; then
  read -r SUBJECT_POINT_X SUBJECT_POINT_Y < <(png_center "$WORK_DIR/first_frame.png")
fi
echo "[INFO] retained object point: $SUBJECT_POINT_X,$SUBJECT_POINT_Y"

echo "[INFO] add retained object by point"
curl -sS -X POST "$BASE_URL/api/projects/$PROJECT_ID/masks/point" \
  -H "Content-Type: application/json" \
  -d "{\"point\":[$SUBJECT_POINT_X,$SUBJECT_POINT_Y]}" > "$WORK_DIR/mask_1.json"
check_file_url "$(json_get "$WORK_DIR/mask_1.json" files.final_overlay)"

echo "[INFO] undo mask once"
curl -sS -X POST "$BASE_URL/api/projects/$PROJECT_ID/mask/undo" > "$WORK_DIR/undo.json"
cat "$WORK_DIR/undo.json"
echo

echo "[INFO] add retained object by point again"
curl -sS -X POST "$BASE_URL/api/projects/$PROJECT_ID/masks/point" \
  -H "Content-Type: application/json" \
  -d "{\"point\":[$SUBJECT_POINT_X,$SUBJECT_POINT_Y]}" > "$WORK_DIR/mask_2.json"
check_file_url "$(json_get "$WORK_DIR/mask_2.json" files.final_overlay)"

echo "[INFO] start matting"
curl -sS -X POST "$BASE_URL/api/projects/$PROJECT_ID/matting" \
  -H "Content-Type: application/json" \
  -d "{\"warmup\":10,\"erode\":10,\"dilate\":10,\"max_size\":$MAX_SIZE,\"save_image\":false}" > "$WORK_DIR/matting_start.json"
MATTING_JOB="$(json_get "$WORK_DIR/matting_start.json" job_id)"
poll_job "$MATTING_JOB" "$WORK_DIR/matting_job.json"

curl -sS "$BASE_URL/api/projects/$PROJECT_ID" > "$WORK_DIR/after_matting.json"
check_file_url "$(json_get "$WORK_DIR/after_matting.json" files.alpha)"
check_file_url "$(json_get "$WORK_DIR/after_matting.json" files.green)"

echo "[INFO] upload background and compose"
curl -sS -X POST "$BASE_URL/api/projects/$PROJECT_ID/background" \
  -F "background=@$BACKGROUND" > "$WORK_DIR/background_start.json"
BACKGROUND_JOB="$(json_get "$WORK_DIR/background_start.json" job_id)"
poll_job "$BACKGROUND_JOB" "$WORK_DIR/background_job.json"

curl -sS "$BASE_URL/api/projects/$PROJECT_ID" > "$WORK_DIR/final.json"
check_file_url "$(json_get "$WORK_DIR/final.json" files.replaced)"

echo "[DONE] API three-stage smoke succeeded for project: $PROJECT_ID"
