from pathlib import Path

import numpy as np
import torch
from PIL import Image

from sam3.model_builder import build_sam3_image_model
from sam3.model.sam3_image_processor import Sam3Processor
from tools.mask_ops import load_gray_mask, merge_or, save_mask, save_overlay


class SAM3MaskService:
    def __init__(self, checkpoint, device="cuda"):
        self.checkpoint = checkpoint
        self.device = device
        self.model = None
        self.processor = None

    def load(self):
        if self.model is not None:
            return

        print("[INFO] loading SAM3.1 model...")
        self.model = build_sam3_image_model(
            checkpoint_path=self.checkpoint,
            load_from_HF=False,
            device=self.device,
            eval_mode=True,
        )
        self.processor = Sam3Processor(model=self.model, device=self.device)

    def predict_text_mask(self, image_path, prompt):
        self.load()
        image = Image.open(image_path).convert("RGB")

        def _run():
            state = self.processor.set_image(image)
            return self.processor.set_text_prompt(prompt=prompt, state=state)

        with torch.inference_mode():
            if self.device == "cuda":
                with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                    state = _run()
            else:
                state = _run()

        return self._select_mask(state)

    def predict_box_mask(self, image_path, box):
        self.load()
        image = Image.open(image_path).convert("RGB")
        norm_box = self._pixel_box_to_norm_box(image, box)

        def _run():
            state = self.processor.set_image(image)
            return self.processor.add_geometric_prompt(
                box=norm_box,
                label=True,
                state=state,
            )

        with torch.inference_mode():
            if self.device == "cuda":
                with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                    state = _run()
            else:
                state = _run()

        return self._select_mask(state)

    def predict_point_mask(self, image_path, point):
        self.load()
        image = Image.open(image_path).convert("RGB")
        norm_point = self._pixel_point_to_norm_point(image, point)

        def _run():
            state = self.processor.set_image(image)
            return self._add_point_prompt(norm_point, True, state)

        with torch.inference_mode():
            if self.device == "cuda":
                with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                    state = _run()
            else:
                state = _run()

        return self._select_mask(state)

    def save_subject(self, project_store, mask, source):
        state = project_store.load_state()
        self._push_mask_snapshot(state)
        first_frame = project_store.resolve_path(state["first_frame"], "inputs/first_frame.png")

        subject_path = project_store.masks_dir / "subject.png"
        overlay_path = project_store.overlays_dir / "subject_overlay.png"

        save_mask(mask, subject_path)
        save_overlay(first_frame, mask, overlay_path, color=(0, 255, 0))

        state["subject_mask"] = project_store.to_project_path(subject_path)
        project_store.add_history(state, "set_subject", source)
        project_store.save_state(state)

        self.merge_final(project_store)
        return project_store.load_state()

    def add_foreground(self, project_store, mask, source):
        state = project_store.load_state()
        self._push_mask_snapshot(state)
        first_frame = project_store.resolve_path(state["first_frame"], "inputs/first_frame.png")

        idx = len(state.get("foreground_masks", []))
        mask_path = project_store.masks_dir / f"foreground_{idx:03d}.png"
        overlay_path = project_store.overlays_dir / f"foreground_{idx:03d}_overlay.png"

        save_mask(mask, mask_path)
        save_overlay(first_frame, mask, overlay_path, color=(255, 180, 0))

        state.setdefault("foreground_masks", []).append(project_store.to_project_path(mask_path))
        project_store.add_history(state, "add_foreground", source)
        project_store.save_state(state)

        self.merge_final(project_store)
        return project_store.load_state()

    def add_retained_mask(self, project_store, mask, source):
        state = project_store.load_state()
        self._push_mask_snapshot(state)
        first_frame = project_store.resolve_path(state["first_frame"], "inputs/first_frame.png")

        idx = len(state.get("retained_masks", []))
        mask_path = project_store.masks_dir / f"retained_{idx:03d}.png"
        overlay_path = project_store.overlays_dir / f"retained_{idx:03d}_overlay.png"

        save_mask(mask, mask_path)
        save_overlay(first_frame, mask, overlay_path, color=(0, 180, 255))

        item = {
            "id": f"MASK_{idx + 1}",
            "name": self._retained_name(source, idx),
            "source": source,
            "mask": project_store.to_project_path(mask_path),
            "overlay": project_store.to_project_path(overlay_path),
        }
        state.setdefault("retained_masks", []).append(item)
        project_store.add_history(state, "add_retained_mask", item)
        project_store.save_state(state)

        self.merge_final(project_store)
        return project_store.load_state()

    def add_target(self, project_store, mask, source):
        state = project_store.load_state()
        first_frame = project_store.resolve_path(state["first_frame"], "inputs/first_frame.png")

        idx = len(state.get("targets", []))
        target_id = f"target_{idx:03d}"
        target_dir = project_store.project_dir / "targets" / target_id
        target_dir.mkdir(parents=True, exist_ok=True)

        mask_path = target_dir / "mask.png"
        overlay_path = target_dir / "overlay.png"

        save_mask(mask, mask_path)
        save_overlay(first_frame, mask, overlay_path, color=(255, 80, 160))

        target = {
            "id": target_id,
            "name": self._target_name(source, target_id),
            "source": source,
            "mask": project_store.to_project_path(mask_path),
            "overlay": project_store.to_project_path(overlay_path),
            "results": {},
        }
        state.setdefault("targets", []).append(target)
        state["active_target_id"] = target_id
        project_store.add_history(state, "add_target", target)
        project_store.save_state(state)
        return project_store.load_state()

    def undo_foreground(self, project_store):
        state = project_store.load_state()
        self._push_mask_snapshot(state)
        masks = state.get("foreground_masks", [])

        if not masks:
            print("[WARN] no foreground mask to undo")
            return state

        removed = masks.pop()
        state["foreground_masks"] = masks
        project_store.add_history(state, "undo_foreground", {"removed": removed})
        project_store.save_state(state)

        self.merge_final(project_store)
        return project_store.load_state()

    def undo_mask(self, project_store):
        state = project_store.load_state()
        snapshots = state.get("mask_snapshots", [])

        if not snapshots:
            print("[WARN] no mask snapshot to undo")
            return state

        snapshot = snapshots.pop()
        state["mask_snapshots"] = snapshots
        state["subject_mask"] = snapshot.get("subject_mask")
        state["foreground_masks"] = snapshot.get("foreground_masks", [])
        state["retained_masks"] = snapshot.get("retained_masks", [])
        state["final_mask"] = snapshot.get("final_mask")
        project_store.add_history(state, "undo_mask", {"restored": snapshot})
        project_store.save_state(state)

        # Regenerate final overlay so the frontend reflects the undone state.
        retained = state.get("retained_masks", [])
        if retained or state.get("subject_mask"):
            self.merge_final(project_store)
        else:
            # Clear final mask artifacts when no masks remain
            state["final_mask"] = None
            project_store.save_state(state)
        return project_store.load_state()

    def merge_final(self, project_store):
        state = project_store.load_state()

        retained_masks = state.get("retained_masks", [])
        if retained_masks:
            mask_values = [item["mask"] for item in retained_masks if item.get("mask")]
        elif state.get("subject_mask"):
            mask_values = [state["subject_mask"]] + state.get("foreground_masks", [])
        else:
            raise RuntimeError("At least one retained mask is required before merging final mask")

        mask_paths = [
            project_store.resolve_path(mask_path)
            for mask_path in mask_values
        ]
        masks = [load_gray_mask(p) for p in mask_paths]
        final = merge_or(masks)

        final_path = project_store.masks_dir / "final.png"
        overlay_path = project_store.overlays_dir / "final_overlay.png"

        save_mask(final, final_path)
        first_frame = project_store.resolve_path(state["first_frame"], "inputs/first_frame.png")
        save_overlay(first_frame, final, overlay_path, color=(0, 180, 255))

        state["final_mask"] = project_store.to_project_path(final_path)
        project_store.add_history(state, "merge_final", {"mask_count": len(mask_paths)})
        project_store.save_state(state)
        return state

    def _select_mask(self, state):
        masks = state.get("masks")
        scores = state.get("scores")

        if masks is None or len(masks) == 0:
            return None

        masks = masks.detach().float().cpu().numpy()

        if masks.ndim == 4:
            masks = masks[:, 0]

        if scores is not None:
            scores_np = scores.detach().float().cpu().numpy()
            idx = int(np.argmax(scores_np))
        else:
            areas = masks.reshape(masks.shape[0], -1).sum(axis=1)
            idx = int(np.argmax(areas))

        return (masks[idx] > 0.5).astype(np.uint8) * 255

    def _pixel_box_to_norm_box(self, image, box):
        w, h = image.size
        x1, y1, x2, y2 = [float(v) for v in box]

        cx = ((x1 + x2) / 2.0) / w
        cy = ((y1 + y2) / 2.0) / h
        bw = (x2 - x1) / w
        bh = (y2 - y1) / h

        return [cx, cy, bw, bh]

    def _pixel_point_to_norm_point(self, image, point):
        w, h = image.size
        x, y = [float(v) for v in point]
        return [x / w, y / h]

    def _add_point_prompt(self, point, label, state):
        if hasattr(self.processor, "add_point_prompt"):
            return self.processor.add_point_prompt(
                point=point,
                label=label,
                state=state,
            )

        if "backbone_out" not in state:
            raise ValueError("You must call set_image before add point prompt")

        if "language_features" not in state["backbone_out"]:
            dummy_text_outputs = self.model.backbone.forward_text(
                ["visual"], device=self.device
            )
            state["backbone_out"].update(dummy_text_outputs)

        if "geometric_prompt" not in state:
            state["geometric_prompt"] = self.model._get_dummy_prompt()

        points = torch.tensor(point, device=self.device, dtype=torch.float32).view(1, 1, 2)
        labels = torch.tensor([int(label)], device=self.device, dtype=torch.long).view(1, 1)
        mask = torch.zeros(1, 1, device=self.device, dtype=torch.bool)
        state["geometric_prompt"].append_points(points, labels, mask)

        return self.processor._forward_grounding(state)

    def _target_name(self, source, fallback):
        if source.get("mode") == "text" and source.get("text"):
            return source["text"]
        return fallback

    def _push_mask_snapshot(self, state):
        state.setdefault("mask_snapshots", []).append({
            "subject_mask": state.get("subject_mask"),
            "foreground_masks": list(state.get("foreground_masks", [])),
            "retained_masks": list(state.get("retained_masks", [])),
            "final_mask": state.get("final_mask"),
        })

    def _retained_name(self, source, index):
        if source.get("mode") == "text" and source.get("text"):
            return source["text"]
        return f"MASK_{index + 1}"
