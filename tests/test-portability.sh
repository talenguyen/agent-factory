#!/usr/bin/env bash
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"

home_prefix="/""Users/"
if git -C "$root" grep -nE "${home_prefix}[^[:space:]]+"; then
  echo 'tracked file contains a home-directory path' >&2
  exit 1
fi
old_ledger_prefix=".superpowers/""dtp-crew"
if git -C "$root" grep -nF "$old_ledger_prefix"; then
  echo 'tracked file references the old crew-ledger path' >&2
  exit 1
fi
rg -Fxq '.factory/' "$root/.gitignore" || { echo '.factory/ is not gitignored' >&2; exit 1; }
rg -Fxq '.claude/settings.local.json' "$root/.gitignore" || { echo '.claude/settings.local.json is not gitignored' >&2; exit 1; }
if rg -q 'enabledPlugins|skillOverrides' "$root/.claude/settings.json"; then
  echo 'tracked settings retain local preferences' >&2
  exit 1
fi

printf '%s\n' 'test-portability: PASS'
