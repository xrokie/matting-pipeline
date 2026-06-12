from dataclasses import dataclass
import os
from pathlib import Path


def _path_from_env(name, default):
    return Path(os.environ.get(name, default)).expanduser().resolve()


@dataclass(frozen=True)
class Settings:
    matting_root: Path = _path_from_env("MATTING_ROOT", "~/matting")
    sam3_env: str = os.environ.get("SAM3_ENV", "sam3")
    matanyone2_env: str = os.environ.get("MATANYONE2_ENV", "matanyone2")
    sam3_device: str = os.environ.get("SAM3_DEVICE", "cuda")
    sam3_checkpoint: Path = _path_from_env(
        "SAM3_CHECKPOINT",
        "~/matting/sam3/models/sam3.1/sam3.1_multiplex.pt",
    )
    matanyone2_checkpoint: Path = _path_from_env(
        "MATANYONE2_CHECKPOINT",
        "~/matting/MatAnyone2/pretrained_models/matanyone2.pth",
    )
    sam2_server_url: str = os.environ.get("SAM2_SERVER_URL", "http://127.0.0.1:8765")
    sam2_checkpoint: Path = _path_from_env(
        "SAM2_CHECKPOINT",
        "~/matting/sam2/checkpoints/sam2.1_hiera_base_plus.pt",
    )
    max_upload_mb: int = int(os.environ.get("MAX_UPLOAD_MB", "2048"))

    @property
    def sam3_dir(self):
        return self.matting_root / "sam3"

    @property
    def matanyone2_dir(self):
        return self.matting_root / "MatAnyone2"

    @property
    def projects_dir(self):
        return self.matting_root / "projects"


settings = Settings()
