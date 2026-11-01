#!/usr/bin/env bash
# Copy standalone HTML embeds and the Grafana dashboard JSON into the site tree (idempotent via cp -u).
set -euo pipefail
SITE="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(dirname "$SITE")"
mkdir -p "$SITE/public/embeds" "$SITE/src/data"

cp -u "$REPO/2_Qspice/Claude's outputs/PCB_Baseline/build_book.html" "$SITE/public/embeds/build_book.html"
cp -u "$REPO/0_Documentation/UI Pod Wiring.html"                      "$SITE/public/embeds/ui-pod-wiring.html"
cp -u "$REPO/7_Pi/grafana/dashboards/shuffler.json"                    "$SITE/src/data/grafana_shuffler.json"

echo "== external references in embeds (http/https, excluding xmlns) =="
for f in "$SITE"/public/embeds/*.html; do
  echo "-- $(basename "$f")"
  grep -oE 'https?://[^"'"'"' )<>]+' "$f" | grep -v 'www.w3.org' | sort | uniq -c || true
  echo "   <script> tags: $(grep -oE '<script[^>]*>' "$f" | sort | uniq -c | tr '\n' ';' || true)"
done
echo "== grafana_shuffler.json secret scan (token|password|secret|apikey) =="
if grep -niE 'token|password|secret|apikey|api_key' "$SITE/src/data/grafana_shuffler.json"; then
  echo "WARNING: possible secret in grafana_shuffler.json" >&2; exit 1
fi
echo "clean"
