"""Export the current database into seed/finn_seed.db (commit it). Run from backend/: python scripts/make_snapshot.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from finn.snapshot import make  # noqa: E402

p = make()
print(f"snapshot written: {p} ({p.stat().st_size / 1e6:.1f} MB)")
