#!/usr/bin/env python3
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "research"
VERIFY = ROOT / "bin" / "verify-research"

for name, key, expected in [
    ("clean", None, 0),
    ("valid-derived", None, 0),
    ("uncited-literal", "source-a", 1),
    ("explicit-correct-decimal", None, 0),
    ("explicit-wrong-decimal", "source-a", 1),
    ("explicit-correct-parenthesized", None, 0),
    ("explicit-wrong-parenthesized", "source-a", 1),
    ("explicit-correct-multiplicative", None, 0),
    ("explicit-wrong-multiplicative", "source-a", 1),
    ("realistic-derivation-good-valid", "5", 1),
    ("realistic-derivation-wrong-valid", "6", 1),
    ("realistic-derivation-uncited-valid", "3", 1),
    ("realistic-derivation-unusual-wrong", "10", 1),
    ("realistic-prose-wrong-decimal", "7.0", 1),
    ("realistic-prose-correct-decimal", None, 0),
    ("realistic-prose-wrong-parenthesized", "25", 1),
    ("realistic-prose-correct-parenthesized", None, 0),
    ("realistic-prose-wrong-multiplicative", "25", 1),
    ("realistic-prose-correct-multiplicative", None, 0),
    ("unresolved", "missing", 1),
    ("excerpt-absent", "source-a", 1),
    ("vacuous-excerpt", "source-a", 1),
    ("punctuation-only-excerpt", "source-a", 1),
    ("vacuous-render-required-excerpt", "source-a", 1),
    ("stale-sha", "source-a", 1),
    ("bad-derived", "source-a", 1),
    ("duplicate", "source-a", 1),
    ("orphan", "orphan", 1),
    ("derived-no-figure", "derived", 1),
    ("footnote-pass", None, 0),
    ("footnote-with-number", "9", 1),
    ("footnote-plus-number", "99", 1),
    ("bracket-number", "99", 1),
    ("missing-field", "source-a", 1),
    ("missing-snapshot", "source-a", 1),
    ("render-required", None, 0),
]:
    result = subprocess.run([str(VERIFY), "--workspace", str(FIXTURES / name)], text=True, capture_output=True)
    assert (result.returncode == 0) == (expected == 0), (name, result.stdout, result.stderr)
    if key:
        assert key in result.stderr, (name, result.stderr)
    if name in {"footnote-with-number", "footnote-plus-number", "bracket-number", "realistic-prose-wrong-decimal"}:
        assert "line " in result.stderr and "cited by source-" in result.stderr, (name, result.stderr)

print("test-verify-research: PASS")
