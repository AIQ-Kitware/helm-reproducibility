#!/usr/bin/env bash
# Regenerate the EEE-only demo fixture from scratch.
#
# The fixture is checked into the repo at
# tests/fixtures/eee_only_demo/eee_artifacts/, so this script is **only**
# necessary if you have edited tests/fixtures/eee_only_demo/build_fixture.py
# and want to refresh the artifacts. The generator is uuid5-deterministic,
# so re-running with no source changes produces bit-identical files.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

python3 tests/fixtures/eee_only_demo/build_fixture.py
echo "Fixture refreshed under tests/fixtures/eee_only_demo/eee_artifacts/"
