#!/usr/bin/env python3
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "lib" / "crew" / "adapters" / "herdr_mux.py"
spec = importlib.util.spec_from_file_location("herdr_mux", MODULE_PATH)
herdr_mux = importlib.util.module_from_spec(spec)
spec.loader.exec_module(herdr_mux)

provider = "opencode-go"
model = "deepseek-v4-pro"
thinking = "high"

assert herdr_mux.profile_banner_matches(
    provider, model, thinking, "(opencode-go) deepseek-v4-pro • high"
)
assert herdr_mux.profile_banner_matches(
    provider, model, thinking, "deepseek-v4-pro • high"
)
assert not herdr_mux.profile_banner_matches(
    provider, "wrong-model", thinking, "deepseek-v4-pro • high"
)
assert not herdr_mux.profile_banner_matches(
    provider, model, "low", "deepseek-v4-pro • high"
)

print("test-herdr-banner-regex: PASS")
