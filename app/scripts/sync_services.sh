#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-$HOME/matting}"

echo "[INFO] service wrappers are kept in place in this repository:"
echo "       $ROOT/sam3/services"
echo "       $ROOT/sam3/tools"
echo "       $ROOT/MatAnyone2/services"
echo "       $ROOT/sam2/services"

for path in \
  "$ROOT/sam3/services/mask_service_cli.py" \
  "$ROOT/sam3/services/mask_service/sam3_mask_service.py" \
  "$ROOT/sam3/tools/mask_ops.py" \
  "$ROOT/MatAnyone2/services/matting_project_cli.py" \
  "$ROOT/sam2/services/sam2_service/sam2_point_server.py" \
  "$ROOT/sam2/services/sam2_service/sam2_point_cli.py" \
  "$ROOT/MatAnyone2/services/sam2_service/sam2_point_server.py" \
  "$ROOT/MatAnyone2/services/sam2_service/sam2_point_cli.py"
do
  if [[ ! -f "$path" ]]; then
    echo "[ERROR] missing service wrapper: $path"
    exit 1
  fi
done

echo "[DONE] service wrapper layout looks valid; no sync step is required."
