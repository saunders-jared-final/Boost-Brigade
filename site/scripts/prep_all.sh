#!/usr/bin/env bash
# Run every asset-prep step. Safe to re-run; each step skips outputs newer than their sources.
set -euo pipefail
cd "$(dirname "$0")"
python3 prep_photos.py
python3 prep_figures.py
python3 prep_notebooks.py
bash prep_embeds.sh
