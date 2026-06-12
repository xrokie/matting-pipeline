# CLAUDE.md

This file provides guidance to Claude Code when working in this repository. For human-oriented documentation, see [README.md](README.md).

## Critical Constraints

- **Never unify the three conda environments.** SAM3 needs `numpy<2`, MatAnyone2 needs `numpy>=1.21`.
- **API server (`matting_api`) never imports SAM3 or MatAnyone2 directly.** All model calls go through `conda run` subprocesses. See `api_server/runner.py`.
- **Single GPU queue.** Only one MatAnyone2 task at a time. Enforced by single-threaded `JobStore` in `api_server/jobs.py`.
- **Video matting is slow at full resolution.** Default `max_size=720`. At `max_size=-1` MatAnyone2 uses 40+ GB RAM.
- **`.mov` files (iPhone) need explicit sRGB FFmpeg conversion.** Fixed in `sam3/services/mask_service/project_store.py`. Do not revert the `-pix_fmt rgb24 -colorspace bt709` flags.

## Service Wrapper Architecture

`app/sam3/services/` and `app/MatAnyone2/services/` are the **source of truth**. Run `sync_services.sh` to deploy to `sam3/` and `MatAnyone2/`. Never edit the deployment copies directly.

The `app/api_server/mask_registry.py` module runs in-process in the API server (not via conda subprocess) to manipulate `state.json` and merge masks. It requires `numpy` and `Pillow` in the `matting_api` environment.

## SAM2.1 Point Server

Persistent process on port 8765 in the `matanyone2` conda env. Started automatically by `run_api.sh`. Model stays in GPU (~0.8 GB), inference 5-11ms. Falls back to SAM3.1 if unreachable. The `/masks/point` endpoint prefers SAM2; `/masks/box` and `/masks/text` always use SAM3.1.

## State.json & Multi-Round Matting

`state.json` stores project-relative paths only. API converts to `/files/{project_id}/...` URLs. Mask snapshots are pushed before each mask operation to enable undo. `matting_rounds` accumulates per-round alphas; `results.alpha` is the max-merge of all rounds.

`clear_masks` (`POST /masks/clear`) preserves `matting_rounds` and `results` while resetting `retained_masks` — used for the "preserve green screen, re-select objects" workflow.

## Frontend Coordinate System

Canvas clicks must be converted from display coordinates to original image pixel coordinates. The frontend does this in `eventToImagePoint()` using `naturalWidth`/`naturalHeight` vs displayed dimensions. The backend receives pixel coordinates relative to `first_frame.png`.

## Key Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MATTING_ROOT` | `~/matting` | Deployment root |
| `SAM3_ENV` | `sam3` | Conda env for SAM3 |
| `MATANYONE2_ENV` | `matanyone2` | Conda env for MatAnyone2 + SAM2 |
| `SAM2_SERVER_URL` | `http://127.0.0.1:8765` | SAM2 persistent server |
| `SAM3_CHECKPOINT` | `~/matting/sam3/models/sam3.1/sam3.1_multiplex.pt` | SAM3.1 weights |
| `SAM2_CHECKPOINT` | `~/matting/sam2/checkpoints/sam2.1_hiera_base_plus.pt` | SAM2.1 weights |

## Build & Test Commands

```bash
# Frontend
cd ~/matting/app/frontend && npm install && npm run build

# API smoke test (three-stage flow)
bash ~/matting/app/scripts/smoke_test_wsl_api_three_stage.sh

# Sync service wrappers
bash ~/matting/app/scripts/sync_services.sh

# Start all services
conda activate matting_api && bash ~/matting/app/scripts/run_api.sh
```
