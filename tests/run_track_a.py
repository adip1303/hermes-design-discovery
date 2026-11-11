"""Stdlib fallback runner for Track A tests when pytest is unavailable."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from test_track_a import *

tests = sorted((name, value) for name, value in globals().items() if name.startswith("test_") and callable(value))
for _, test in tests:
    test()
print("track_a: passed " + ", ".join(name for name, _ in tests))
