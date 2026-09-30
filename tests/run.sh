#!/usr/bin/env bash
# The validator's and summariser's tests, offline, against the fixtures in
# tests/fixtures (see tests/README.md). Needs the pinned jsonschema:
#   python3 -m pip install --no-deps -r scripts/requirements.txt
set -euo pipefail
cd "$(dirname "$0")/.."
exec "${PYTHON:-python3}" -m unittest discover -s tests -p 'test_*.py' -v
