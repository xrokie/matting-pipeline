import json
import io
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from PIL import Image


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def _strip_icc(image_path):
    """Remove embedded ICC color profile from a PNG.

    PIL ignores ICC profiles and reads raw pixel values.  Browsers
    apply ICC color management.  Stripping the profile ensures both
    see identical pixels, which is critical when the PNG is used as
    both a preview (browser) and model input (PIL).
    """
    try:
        img = Image.open(image_path)
        # If there's no ICC profile, this is a no-op
        if "icc_profile" in img.info:
            # Save without the profile
            data = list(img.getdata())
            mode = img.mode
            size = img.size
            cleaned = Image.new(mode, size)
            cleaned.putdata(data)
            cleaned.save(image_path, "PNG")
    except Exception:
        pass  # non-fatal — worst case the image has a color profile


class MaskProjectStore:
    def __init__(self, project_dir):
        self.project_dir = Path(project_dir).resolve()
        self.masks_dir = self.project_dir / "masks"
        self.overlays_dir = self.project_dir / "overlays"
        self.inputs_dir = self.project_dir / "inputs"
        self.state_path = self.project_dir / "state.json"

    def ensure_dirs(self):
        self.project_dir.mkdir(parents=True, exist_ok=True)
        self.inputs_dir.mkdir(parents=True, exist_ok=True)
        self.masks_dir.mkdir(parents=True, exist_ok=True)
        self.overlays_dir.mkdir(parents=True, exist_ok=True)

    def init_from_video(self, video_path, background_path=None):
        self.ensure_dirs()

        video_dst = self.inputs_dir / "input.mp4"
        shutil.copy2(Path(video_path).expanduser(), video_dst)

        bg_dst = None
        if background_path:
            bg_dst = self.inputs_dir / "background.png"
            Image.open(Path(background_path).expanduser()).convert("RGB").save(bg_dst)

        first_frame = self.inputs_dir / "first_frame.png"

        # Extract first frame with explicit sRGB color space.
        # .mov files (especially iPhone) often use HDR/BT.2020 — without
        # these flags, browsers color-manage the PNG differently from how
        # PIL reads raw pixels, causing SAM masks to misalign with the
        # displayed preview.
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(video_dst),
                "-frames:v",
                "1",
                "-update",
                "1",
                "-pix_fmt",
                "rgb24",
                "-colorspace",
                "bt709",
                "-color_primaries",
                "bt709",
                "-color_trc",
                "iec61966-2-1",
                "-color_range",
                "2",          # full range (0-255), matches PNG convention
                str(first_frame),
            ],
            check=True,
        )
        # Strip any embedded ICC profile so PIL and browsers see identical
        # pixel values.  PIL ignores ICC; browsers apply it.
        _strip_icc(first_frame)

        state = {
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "video": self.to_project_path(video_dst),
            "background": self.to_project_path(bg_dst) if bg_dst else None,
            "first_frame": self.to_project_path(first_frame),
            "subject_mask": None,
            "foreground_masks": [],
            "retained_masks": [],
            "final_mask": None,
            "targets": [],
            "active_target_id": None,
            "history": [],
        }
        self.save_state(state)
        return state

    def load_state(self):
        if not self.state_path.exists():
            raise FileNotFoundError(f"Missing state file: {self.state_path}")
        return json.loads(self.state_path.read_text())

    def save_state(self, state):
        state["updated_at"] = now_iso()
        self.state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False))

    def to_project_path(self, path):
        path = Path(path).resolve()
        try:
            return str(path.relative_to(self.project_dir))
        except ValueError:
            return str(path)

    def resolve_path(self, value, fallback_inside_project=None):
        if value is None:
            return None

        path = Path(value).expanduser()

        if path.is_absolute() and path.exists():
            return path

        if fallback_inside_project:
            candidate = self.project_dir / fallback_inside_project
            if candidate.exists():
                return candidate

        candidate = self.project_dir / path
        if candidate.exists():
            return candidate

        candidate = Path.cwd() / path
        if candidate.exists():
            return candidate

        return self.project_dir / path

    def add_history(self, state, action, payload):
        state.setdefault("history", []).append(
            {
                "time": now_iso(),
                "action": action,
                "payload": payload,
            }
        )
