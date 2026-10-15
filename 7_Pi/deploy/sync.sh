#!/usr/bin/env bash
# DEV MACHINE: copy only the Pi code (7_Pi, incl. staged firmware) to the Pi, no git needed on the Pi.
#   bash 7_Pi/deploy/sync.sh <user>@<pi-address> [remote dir, default ~/Boost-Brigade/7_Pi]
set -euo pipefail
[ $# -ge 1 ] || { echo "usage: $0 user@host [remote_dir]"; exit 1; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEST="${2:-Boost-Brigade/7_Pi}"
rsync -avz --delete --exclude data/ --exclude .venv/ --exclude __pycache__/ --exclude ".lgd-nfy*" \
  --exclude pod/params.yaml "$ROOT/7_Pi/" "$1:$DEST/"
# params.yaml is edited / saved on the Pi (params_web "Save"): only copy it when the Pi has none
rsync -avz --ignore-existing "$ROOT/7_Pi/pod/params.yaml" "$1:$DEST/pod/params.yaml"
echo "next, on the Pi:  bash $DEST/deploy/setup.sh"
