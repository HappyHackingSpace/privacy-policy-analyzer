import sys
from pathlib import Path

# Allow running the tests without installing the package (e.g. plain `pytest`
# from a checkout): put `src/` on sys.path so `privacy_policy_analyzer` imports.
SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
