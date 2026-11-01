#!/usr/bin/env bash
# Fail the build if anything that must never be published leaks into the site tree.
set -euo pipefail
cd "$(dirname "$0")/.."
PATTERN='shuffler123|shuffler-pod-token|GF_SECURITY_ADMIN_PASSWORD|DOCKER_INFLUXDB_INIT_PASSWORD|benha'
if grep -rIEn "$PATTERN" src public --exclude-dir=node_modules 2>/dev/null; then
  echo "check_secrets: forbidden string found in site tree" >&2
  exit 1
fi
echo "check_secrets: clean"
