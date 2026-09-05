#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
runtime_image=$(/usr/bin/podman --cgroup-manager=cgroupfs image inspect localhost/alpendata-runtime:dev --format '{{.Id}}')
exec bash scripts/run_tests.sh alpendata/backend/tests/test_runtime.py -- \
    -c alpendata/backend/pyproject.toml -p no:cacheprovider --runtime-image "sha256:$runtime_image"
