# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **video background replacement pipeline** that combines two deep learning models:

- **SAM3.1** (Meta) — open-vocabulary segmentation model that generates first-frame masks from text prompts, points, or boxes
- **MatAnyone2** (NTU S-Lab, CVPR 2026) — video matting model that propagates a first-frame mask to the entire video, producing per-frame alpha mattes

The integration layer (`app/`) orchestrates both models via `conda run` subprocess calls, serves a FastAPI backend, and provides a React frontend for the three-stage workflow: upload → mask selection (with green screen preview) → background replacement.

## Critical Architecture: Process Isolation

**Do not attempt to unify the Python environments.** The three components run in separate conda environments for a reason — dependency conflicts (SAM3 requires `numpy<2`, MatAnyone2 requires `numpy>=1.21`):

| Environment | Python | Purpose |
|---|---|---|
| `sam3` | 3.12 | First-frame mask generation via SAM3.1 |
| `matanyone2` | 3.10 | Video matting + background composition |
| `matting_api` | 3.11 | FastAPI server (never imports SAM3 or MatAnyone2) |

The API server calls models exclusively through subprocess:
```bash
conda run -n sam3 python -m services.mask_service_cli ...
conda run -n matanyone2 python -m services.matting_project_cli ...
```

## Repository Layout

```
matting/
├── app/                    # Integration layer (the application)
│   ├── api_server/         # FastAPI: main.py, config.py, runner.py, jobs.py, schemas.py, project_files.py
│   ├── frontend/           # Vite + React + TypeScript (src/App.tsx, src/api.ts, src/types.ts)
│   ├── docs/               # API_HANDOFF.md (API contract), DEPLOYMENT.md, PROJECT_MEMORY.md, FRONTEND_ENGINEERING.md
│   ├── scripts/            # run_api.sh, smoke_test_*.sh, sync_services.sh
│   ├── sam3/               # Source-of-truth for SAM3 service wrappers (sync to ~/matting/sam3/services/)
│   └── MatAnyone2/         # Source-of-truth for MatAnyone2 service wrappers (sync to ~/matting/MatAnyone2/services/)
├── sam3/                   # Full SAM3 upstream repo (Meta's sam3 + our service wrappers)
│   ├── sam3/model/         # ViT backbone, DETR detector, transformer encoder/decoder, segmentation head
│   ├── sam3/agent/         # SAM3 Agent for complex text prompts
│   ├── services/           # mask_service/ (SAM3MaskService, MaskProjectStore), mask_service_cli.py
│   └── tools/mask_ops.py   # load_gray_mask, merge_or, save_mask, save_overlay
├── MatAnyone2/             # Full MatAnyone2 upstream repo + our service wrappers
│   ├── matanyone2/model/   # MatAnyone2 nn.Module (PixelEncoder, MaskDecoder, QueryTransformer, etc.)
│   ├── matanyone2/inference/ # InferenceCore (memory propagation loop), MemoryManager, ObjectManager
│   ├── services/           # matting_project_cli.py, matting_service/compose_bg.py
│   └── pretrained_models/  # matanyone2.pth checkpoint
└── projects/               # Per-user-task project directories with state.json
```

## The Three-Stage Pipeline

### Stage 1: Video Upload
`POST /api/projects` → FFmpeg extracts first frame → SAM3 `init` command

### Stage 2: Mask Selection → Green Screen
Frontend shows `first_frame.png`. User adds "retained masks" via text prompts or canvas point clicks. Each mask addition calls SAM3.1 through `conda run`. All retained masks are merged (OR) into `final.png`, then MatAnyone2 propagates it to the full video. Multiple rounds can be stacked — alpha mattes are merged via per-frame `max()`.

### Stage 3: Background Replacement
User uploads background image → OpenCV composes `alpha × foreground + (1-alpha) × background` frame-by-frame → FFmpeg muxes original audio.

## Project Directory Structure (per task)

```
projects/{project_id}/
├── inputs/          # input.mp4, background.png, first_frame.png
├── masks/           # retained_000.png, retained_001.png, final.png
├── overlays/        # retained_000_overlay.png, final_overlay.png (colored preview)
├── rounds/          # round_000/alpha.mp4, round_001/alpha.mp4
├── results/         # alpha.mp4, green.mp4, replaced.mp4
└── state.json       # All relative paths, history log, mask snapshots for undo
```

## Key Service Files (our additions to upstream models)

### `sam3/services/mask_service/sam3_mask_service.py`
`SAM3MaskService` — wraps SAM3.1 for text/box/point mask prediction. Key methods:
- `predict_text_mask(image_path, prompt)` — uses `Sam3Processor.set_text_prompt`
- `predict_point_mask(image_path, point)` — has fallback if `add_point_prompt` doesn't exist (calls `append_points` + `_forward_grounding` directly)
- `save_subject()`, `add_foreground()`, `add_retained_mask()` — save mask + overlay, push mask snapshot for undo, call `merge_final()`
- `merge_final()` — OR-merges all retained masks into `final.png`
- `undo_mask()` — pops from `mask_snapshots` stack to restore previous state

### `sam3/services/mask_service/project_store.py`
`MaskProjectStore` — manages project directory, `state.json`, path resolution. `init_from_video()` copies video, runs FFmpeg for first frame.

### `MatAnyone2/services/matting_project_cli.py`
CLI that orchestrates: MatAnyone2 inference → alpha merging → green screen composition → background composition. Handles `run_project`, `compose_background`, `undo_round`, `rebuild_from_rounds`.

### `MatAnyone2/services/matting_service/compose_bg.py`
OpenCV-based video compositing:
- `compose_video(video, alpha, background, output)` — alpha blending with arbitrary background image
- `compose_solid_video()` — green screen (solid color) preview
- `max_alpha_videos(alpha_paths, output)` — per-frame max merge of multiple alpha videos for multi-round accumulation

### `sam3/tools/mask_ops.py`
Low-level mask utilities: `load_gray_mask`, `binarize`, `merge_or` (np.maximum across masks), `save_mask`, `save_overlay` (colorized preview on original frame).

## API Server Architecture

- **`main.py`**: All HTTP endpoints. Each SAM3 endpoint calls `run_sam3_json()` which runs `conda run -n sam3 python -m services.mask_service_cli <command>` and parses the last JSON object from stdout. Matting/background endpoints submit async jobs.
- **`config.py`**: Frozen dataclass reading from env vars (`MATTING_ROOT`, `SAM3_ENV`, `MATANYONE2_ENV`, `SAM3_CHECKPOINT`, etc.)
- **`runner.py`**: `run_command()` for synchronous subprocess with `CommandError`; `run_streaming_command()` for long tasks (reads stdout char-by-char, feeds to progress parser); `run_json_command()` extracts JSON from command output.
- **`jobs.py`**: `JobStore` — in-memory async job queue with single-worker ThreadPoolExecutor. Jobs have status `queued → running → succeeded/failed`, with stage and progress fields.
- **`project_files.py`**: `load_state()`, `project_response()` (builds API response with file URLs), `resolve_file()` (path traversal protection), `state_status()` (derives workflow stage from state.json).
- **`schemas.py`**: Pydantic models for `TextPrompt`, `BoxPrompt`, `PointPrompt`, `MattingRequest`.

### Progress Parsing During Matting
`MattingProgressParser` in `main.py` reads stdout character-by-character from `conda run`, matches regex `(\d+)\s*/\s*(\d+)` to extract frame progress from MatAnyone2's tqdm output, and updates job progress (5% warmup + 80% for inference frames). Stage detection via keyword matching: "running matanyone2", "composing green screen preview", "composing uploaded background", "muxing source audio".

## Frontend Architecture

React + TypeScript, built with Vite. Single-page app with a 5-step workflow stepper:
- **`App.tsx`**: Main state machine managing `WorkflowStage` (upload → mask → matting → review → background → done). Uses `pollJob()` with 1.8s polling interval for async task progress.
- **`api.ts`**: Uses XMLHttpRequest for uploads (progress tracking), fetch for JSON endpoints. All file URLs get cache-busting `?t=` parameter.
- **`types.ts`**: TypeScript interfaces for `ProjectResponse`, `JobResponse`, `MattingSettings`, `Point`.

### Coordinate System
When user clicks on the displayed first frame, the frontend converts canvas coordinates back to original image pixel coordinates using `naturalWidth/naturalHeight` vs displayed dimensions. The backend receives pixel coordinates relative to the original `first_frame.png`.

## MatAnyone2 Model (upstream)

- **`MatAnyone2`** (nn.Module): PixelEncoder (feature extraction) → KeyProjection → MaskEncoder → QueryTransformer (object attention) → MaskDecoder → AuxComputer. Includes `UncertPred` for temporal sparsity/uncertainty prediction. Supports HuggingFace Hub via `PyTorchModelHubMixin`.
- **`InferenceCore`**: Frame-by-frame inference loop with memory propagation (Cutie-style). Manages `MemoryManager` (sensory + working + long-term memory), `ObjectManager`, `ImageFeatureStore`. Processing: first frame encodes given mask → warmup frames re-predict first frame → subsequent frames propagate memory.

## SAM3 Model (upstream)

- **Detector**: DETR-based, conditioned on text (via CLIP-style text encoder), geometry (boxes/points via `SequenceGeometryEncoder`), and image exemplars. Uses `presence_token` for text discrimination. ~848M params.
- **Tracker**: SAM2-style transformer encoder-decoder with memory bank, supporting interactive refinement with points.
- **SAM3.1 Multiplex**: Shared-memory approach for joint multi-object tracking — processes up to 16 objects per "multiplex bucket" for faster inference.
- **`model_builder.py`**: Factory functions for building various model configurations (`build_sam3_image_model`, `build_sam3_video_predictor`, `build_sam3_multiplex_video_predictor`).

## Development Commands

**Sync service wrappers to full model repos:**
```bash
bash ~/matting/app/scripts/sync_services.sh
```

**Start API server:**
```bash
conda activate matting_api
bash ~/matting/app/scripts/run_api.sh
# Serves at http://127.0.0.1:8000, frontend at /app, Swagger at /docs
```

**API smoke test (three-stage flow):**
```bash
bash ~/matting/app/scripts/smoke_test_wsl_api_three_stage.sh
```

**Frontend dev build:**
```bash
cd ~/matting/app/frontend
npm install
npm run build    # outputs to dist/
```

**CLI mask operations (in sam3 env):**
```bash
conda activate sam3
cd ~/matting/sam3
python -m services.mask_service_cli init --project ~/matting/projects/<id> --video <path>
python -m services.mask_service_cli add-mask-text --project ~/matting/projects/<id> --checkpoint <ckpt> --text "person"
python -m services.mask_service_cli add-mask-point --project ~/matting/projects/<id> --checkpoint <ckpt> --point 640 780
python -m services.mask_service_cli undo-mask --project ~/matting/projects/<id>
```

**CLI matting (in matanyone2 env):**
```bash
conda activate matanyone2
cd ~/matting/MatAnyone2
python -m services.matting_project_cli --project ~/matting/projects/<id> --max-size 720
python -m services.matting_project_cli --project ~/matting/projects/<id> --compose-background --background <bg.png>
python -m services.matting_project_cli --project ~/matting/projects/<id> --undo-round
```

## Model Checkpoints

```
~/matting/sam3/models/sam3.1/sam3.1_multiplex.pt
~/matting/MatAnyone2/pretrained_models/matanyone2.pth
```

SAM3.1 checkpoint from ModelScope may produce `missing_keys` warnings — this is expected and acceptable if mask quality is normal.

## Important Constraints

- Single RTX 4090 — only one MatAnyone2 task at a time (enforced by single-threaded job executor)
- Demo videos: 5-15 seconds, `max_size=720` or `1080`, `save_image=false`
- MatAnyone2 requires a first-frame mask — without it, inference fails with dimension mismatch
- In WSL, view images with `explorer.exe "$(wslpath -w path/to/image.png)"`
- The `replaced.mp4` must be re-muxed with H.264 `libx264`, `yuv420p`, `+faststart` for browser compatibility
- `state.json` stores project-relative paths only — API converts to `/files/{project_id}/{path}` URLs
- Multi-round alpha accumulation uses simple per-frame `max()` — if a round has a bad mask, that area is permanently affected unless the round is undone

## Legacy / Deprecated

- The old `subject`/`foreground` distinction is deprecated in favor of the unified `retained_masks` model. Backend still supports subject/foreground endpoints for compatibility but the frontend no longer uses them.
- The `targets` API endpoints exist in the backend but are not exposed in the current frontend flow.
