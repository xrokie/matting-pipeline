#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-$HOME/matting}"
FRONTEND_DIR="$ROOT/app/frontend"

command -v node >/dev/null || { echo "[ERROR] node not found"; exit 1; }
command -v npm >/dev/null || { echo "[ERROR] npm not found"; exit 1; }

echo "[INFO] node: $(node --version)"
echo "[INFO] npm: $(npm --version)"
echo "[INFO] frontend: $FRONTEND_DIR"

cd "$FRONTEND_DIR"
npm install
npm run build

test -f "$FRONTEND_DIR/dist/index.html"
test -d "$FRONTEND_DIR/dist/assets"

echo "[DONE] frontend build output:"
find "$FRONTEND_DIR/dist" -maxdepth 2 -type f | sort
