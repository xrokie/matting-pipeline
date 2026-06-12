# Video Background Replacement Pipeline

SAM3.1 + SAM2.1 + MatAnyone2 视频背景替换工程管线。

## What It Does

Upload a video → select objects to keep (click / text / box) → generate green-screen preview → replace background.

```
input.mp4  →  [SAM2.1 / SAM3.1]  →  first-frame masks  →  [MatAnyone2]  →  alpha matte  →  [OpenCV+FFmpeg]  →  replaced.mp4
```

## Architecture

```
matting/
├── app/                          # Application (source of truth)
│   ├── api_server/               # FastAPI backend
│   │   ├── main.py               #   HTTP endpoints
│   │   ├── config.py             #   Environment-based settings
│   │   ├── jobs.py               #   Async job queue (GPU tasks)
│   │   ├── runner.py             #   Subprocess / streaming command runner
│   │   ├── project_files.py      #   Project state & file resolution
│   │   ├── mask_registry.py      #   Mask merge & state.json management
│   │   └── schemas.py            #   Pydantic request/response models
│   ├── frontend/                 # React + TypeScript (Vite)
│   │   └── src/
│   │       ├── App.tsx           #   Main state machine (5 workflow stages)
│   │       ├── api.ts            #   API client (XHR uploads + fetch)
│   │       └── types.ts          #   TypeScript interfaces
│   ├── docs/                     # API contract & deployment guides
│   └── scripts/                  # Startup, smoke tests, service sync
│
├── sam3/                         # SAM3.1 upstream + our service wrappers
│   ├── sam3/model/               #   ViT, DETR, transformer, segmentation
│   ├── sam3/model_builder.py     #   Model factory (848M params)
│   ├── services/                 #   ★ Our additions:
│   │   ├── mask_service_cli.py   #      CLI: init, text/point/box prompts
│   │   └── mask_service/         #      SAM3MaskService + MaskProjectStore
│   └── tools/mask_ops.py         #      Mask load/save/merge utilities
│
├── MatAnyone2/                   # MatAnyone2 upstream + our service wrappers
│   ├── matanyone2/model/         #   PixelEncoder, MaskDecoder, Transformer
│   ├── matanyone2/inference/     #   InferenceCore (memory propagation)
│   ├── inference_matanyone2.py   #   Main entry point
│   └── services/                 #   ★ Our additions:
│       ├── matting_project_cli.py     #  CLI: matting + background compose
│       ├── matting_service/           #  compose_bg (OpenCV compositing)
│       └── sam2_service/              #  SAM2.1 persistent point server
│
└── projects/                     # Per-task project directories (runtime data)
    └── {project_id}/
        ├── inputs/               #   input.mp4, first_frame.png, background.png
        ├── masks/                #   retained_000.png … final.png
        ├── overlays/             #   Preview images with colored mask overlays
        ├── rounds/               #   round_000/alpha.mp4 … per-round alphas
        ├── results/              #   alpha.mp4, green.mp4, replaced.mp4
        └── state.json            #   All paths (project-relative), history, snapshots
```

## Three Conda Environments (Process Isolation)

| Environment | Python | Purpose |
|---|---|---|
| `sam3` | 3.12 | SAM3.1 first-frame mask generation |
| `matanyone2` | 3.10 | MatAnyone2 video matting + SAM2.1 point server |
| `matting_api` | 3.11 | FastAPI server (never imports models directly) |

**Do not unify these environments.** SAM3 requires `numpy<2`, MatAnyone2 requires `numpy>=1.21`. The API server calls models exclusively through `conda run` subprocesses.

## Model Checkpoints

Place these before running (not included in this repo):

```
~/matting/sam3/models/sam3.1/sam3.1_multiplex.pt
~/matting/MatAnyone2/pretrained_models/matanyone2.pth
~/matting/sam2/checkpoints/sam2.1_hiera_base_plus.pt
```

## Quick Start

```bash
# 1. Sync service wrappers from app/ to model repos
bash ~/matting/app/scripts/sync_services.sh

# 2. Build frontend (optional — dist/ already included)
cd ~/matting/app/frontend && npm install && npm run build

# 3. Start (auto-launches SAM2 server + API)
conda activate matting_api
bash ~/matting/app/scripts/run_api.sh
# → http://127.0.0.1:8000/app
# → http://127.0.0.1:8000/docs  (Swagger)
```

## API Overview

Full contract: [`app/docs/API_HANDOFF.md`](app/docs/API_HANDOFF.md)

### Three-Stage Workflow

| Stage | Endpoint | Description |
|---|---|---|
| **1. Upload** | `POST /api/projects` | Upload video, extract first frame |
| **2. Mask** | `POST /api/projects/{id}/masks/text` | Add retained mask via text prompt |
| | `POST /api/projects/{id}/masks/point` | Add retained mask via point click (SAM2.1, ~1s) |
| | `POST /api/projects/{id}/masks/box` | Add retained mask via box selection |
| | `POST /api/projects/{id}/mask/undo` | Undo last mask operation |
| | `POST /api/projects/{id}/masks/clear` | Clear all masks (keep rounds) |
| **Green Screen** | `POST /api/projects/{id}/matting` | Run MatAnyone2 → green.mp4 (async job) |
| | `GET /api/jobs/{job_id}` | Poll job status + frame progress |
| **3. Background** | `POST /api/projects/{id}/background` | Upload background → replaced.mp4 (async job) |
| | `POST /api/projects/{id}/matting/undo` | Undo last matting round |
| **Files** | `GET /files/{project_id}/{path}` | Serve project files |

### Project State Machine

```
created → ready_for_mask → ready_for_matting → ready_for_background → background_succeeded
```

### Async Job Model

```json
{
  "job_id": "job_abc123",
  "status": "queued | running | succeeded | failed",
  "stage": "matanyone2 | green_preview | compose | mux_audio",
  "progress": 0.42,
  "message": "MatAnyone2 推理中：42/100 帧",
  "result": { /* ProjectResponse on success */ },
  "error": { "code": "...", "message": "..." }
}
```

Frontend should poll `GET /api/jobs/{job_id}` every 1-2 seconds during async tasks.

## Key Design Decisions

### Process Isolation
API server never imports SAM3 or MatAnyone2. All model calls use `conda run` subprocesses. Benefits: independent upgrades, no dependency conflicts, Docker-friendly.

### Multi-Round Matting
Each mask selection → MatAnyone2 run produces a round. All round alphas are max-merged. Users can return from green-screen review, re-select objects, and run additional rounds.

### SAM2.1 Persistent Server
Point-click mask generation uses a persistent SAM2.1 process on port 8765. Model stays in GPU (~0.8 GB), inference latency 5-11ms. Falls back to SAM3.1 if unavailable.

### Service Sync
`app/` is the source of truth for service wrappers. Run `sync_services.sh` to propagate changes to `sam3/services/` and `MatAnyone2/services/`.

## For Frontend Developers

See [`app/docs/API_HANDOFF.md`](app/docs/API_HANDOFF.md) for the complete API contract.

Key points:
- All file URLs are served as `/files/{project_id}/{relative_path}`
- The frontend must convert canvas display coordinates back to original image pixel coordinates before sending to the API
- Async tasks (matting, background compose) return `job_id` immediately — poll for completion
- Point click now triggers mask immediately (no separate confirm step)
- `POST /api/projects/{id}/masks/clear` clears masks while preserving green-screen rounds, enabling multi-round refinement
