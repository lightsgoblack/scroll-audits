"""Make `tools.switchbench` importable under plain `pytest`."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE.parents[2], HERE):          # repo root, tests folder
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
