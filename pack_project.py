r"""Convenience launcher for llm_project_packer.

This lets you run the packer from the repository root:

    python pack_project.py .\sample_input --target chatgpt --mode balanced
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent / "llm_project_packer"
ENTRYPOINT = PROJECT_DIR / "pack_project.py"


if not ENTRYPOINT.exists():
    raise SystemExit(f"Could not find packer entry point: {ENTRYPOINT}")

sys.path.insert(0, str(PROJECT_DIR))
runpy.run_path(str(ENTRYPOINT), run_name="__main__")
