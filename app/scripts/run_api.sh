#!/usr/bin/env bash
set -euo pipefail

export MATTING_ROOT="${MATTING_ROOT:-$HOME/matting}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

# ---- Start SAM2 point server if not already running ----
SAM2_PORT="${SAM2_PORT:-8765}"
if curl -s "http://127.0.0.1:$SAM2_PORT/health" > /dev/null 2>&1; then
  echo "[INFO] SAM2 point server already running on port $SAM2_PORT"
else
  echo "[INFO] Starting SAM2 point server..."
  (
    cd "$MATTING_ROOT/sam2"
    conda run -n matanyone2 python -m services.sam2_service.sam2_point_cli start \
      --checkpoint "$MATTING_ROOT/sam2/checkpoints/sam2.1_hiera_base_plus.pt" \
      --port "$SAM2_PORT"
  ) &
  # Wait for it to be ready
  for i in $(seq 1 30); do
    sleep 1
    if curl -s "http://127.0.0.1:$SAM2_PORT/health" > /dev/null 2>&1; then
      echo "[INFO] SAM2 point server ready after ${i}s"
      break
    fi
  done
fi

# ---- Start FastAPI ----
cd "$MATTING_ROOT/app"
if [[ ! -f "$MATTING_ROOT/app/frontend/dist/index.html" ]]; then
  echo "[WARN] frontend dist not found. Run: bash $MATTING_ROOT/app/scripts/smoke/smoke_test_wsl_frontend_build.sh"
fi
exec uvicorn api_server.main:app --host "$HOST" --port "$PORT"
