"""Compatibility entry point for the relocated SAM2.1 point server.

The implementation now lives in ``<MATTING_ROOT>/sam2/services/sam2_service``.
This shim keeps older ``python -m services.sam2_service.sam2_point_server`` calls
working when launched from the MatAnyone2 directory.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


def main():
    repo_root = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(repo_root / "sam2"))
    target = repo_root / "sam2" / "services" / "sam2_service" / "sam2_point_server.py"
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
