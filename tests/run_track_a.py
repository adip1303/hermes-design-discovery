"""Stdlib fallback runner for Track A tests when pytest is unavailable."""
import importlib.util
import sys
from pathlib import Path

path = Path(__file__).resolve().with_name("test_track_a.py")
spec = importlib.util.spec_from_file_location("test_design_discovery_track_a", path)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
globals().update({name: value for name, value in vars(module).items() if name.startswith("test_")})

tests = sorted((name, value) for name, value in globals().items() if name.startswith("test_") and callable(value))
for _, test in tests:
    test()
print("track_a: passed " + ", ".join(name for name, _ in tests))
