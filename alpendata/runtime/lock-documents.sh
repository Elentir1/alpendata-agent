#!/bin/sh
# Run from the repository root with uv and Python 3.13 available.
set -eu
constraints=$(mktemp)
trap 'rm -f "$constraints"' EXIT HUP INT TERM
uv export --frozen --no-dev --no-default-groups --no-emit-project \
  --format requirements-txt --output-file "$constraints" --quiet
uv pip compile alpendata/runtime/documents.in --constraint "$constraints" \
  --python-version 3.13 --python-platform linux --generate-hashes \
  --output-file alpendata/runtime/documents.lock --quiet
