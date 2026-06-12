# App — CLI Reference & Development Guide

This directory is the application layer. For project overview and architecture, see the [root README](../README.md).

## CLI Commands

All commands assume the deployment structure at `~/matting/`.

### SAM3 Mask Operations (conda env: `sam3`)

```bash
cd ~/matting/sam3
conda activate sam3

# Initialize project from video
python -m services.mask_service_cli init \
  --project ~/matting/projects/{id} \
  --video /path/to/video.mp4

# Add retained mask by text
python -m services.mask_service_cli add-mask-text \
  --project ~/matting/projects/{id} \
  --checkpoint ~/matting/sam3/models/sam3.1/sam3.1_multiplex.pt \
  --text "person"

# Add retained mask by point
python -m services.mask_service_cli add-mask-point \
  --project ~/matting/projects/{id} \
  --checkpoint ~/matting/sam3/models/sam3.1/sam3.1_multiplex.pt \
  --point 640 780

# Add retained mask by box
python -m services.mask_service_cli add-mask-box \
  --project ~/matting/projects/{id} \
  --checkpoint ~/matting/sam3/models/sam3.1/sam3.1_multiplex.pt \
  --box 100 200 500 800

# Undo last mask
python -m services.mask_service_cli undo-mask --project ~/matting/projects/{id}

# View project state
python -m services.mask_service_cli state --project ~/matting/projects/{id}
```

### MatAnyone2 Matting (conda env: `matanyone2`)

```bash
cd ~/matting/MatAnyone2
conda activate matanyone2

# Run matting (generates green.mp4)
python -m services.matting_project_cli \
  --project ~/matting/projects/{id} \
  --max-size 720

# Compose background (generates replaced.mp4)
python -m services.matting_project_cli \
  --project ~/matting/projects/{id} \
  --compose-background \
  --background ~/matting/MatAnyone2/inputs/bg.png

# Undo last matting round
python -m services.matting_project_cli \
  --project ~/matting/projects/{id} \
  --undo-round
```

### SAM2.1 Point Server (conda env: `matanyone2`)

```bash
cd ~/matting/MatAnyone2
conda activate matanyone2

# Start persistent server
python -m services.sam2_service.sam2_point_cli start \
  --checkpoint ~/matting/sam2/checkpoints/sam2.1_hiera_base_plus.pt

# One-shot calls (server must be running)
python -m services.sam2_service.sam2_point_cli set-image \
  --project my_project --image /path/to/first_frame.png

python -m services.sam2_service.sam2_point_cli predict \
  --project my_project --point 640 780 \
  --save-mask /path/to/mask.png \
  --save-overlay /path/to/overlay.png \
  --overlay-source /path/to/first_frame.png
```

### API Server (conda env: `matting_api`)

```bash
conda activate matting_api
bash ~/matting/app/scripts/run_api.sh
# → http://127.0.0.1:8000/app (frontend)
# → http://127.0.0.1:8000/docs (Swagger)

# Smoke test
bash ~/matting/app/scripts/smoke_test_wsl_api_three_stage.sh
```

## Service Sync

`app/sam3/` and `app/MatAnyone2/` are the canonical sources for service wrappers. After editing, sync to deployment:

```bash
bash ~/matting/app/scripts/sync_services.sh
```

## Project Directory Convention

```
projects/{project_id}/
├── inputs/               # input.mp4, first_frame.png, background.png
├── masks/                # retained_000.png … final.png
├── overlays/             # *_overlay.png (colored previews)
├── rounds/               # round_000/alpha.mp4 …
├── results/              # alpha.mp4, green.mp4, replaced.mp4
└── state.json            # All paths, history, mask snapshots
```

`state.json` stores project-relative paths only. The API server converts these to `/files/...` URLs.
