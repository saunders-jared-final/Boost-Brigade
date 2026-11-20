#!/usr/bin/env bash
# Copy the reports and datasheets the site links to into public/, so GitHub Pages serves them
# same-origin as application/pdf: they open in the browser's PDF viewer (at #page=N) instead of
# downloading from github.com/raw. Large files are recompressed with Ghostscript (/ebook, 150 dpi);
# the smaller of original and recompressed is kept. Safe to re-run; skips outputs newer than sources.
#
# The public names are the contract with src/lib/site.ts (REPORTS / DOCS / datasheetUrl).
set -euo pipefail
cd "$(dirname "$0")/../.."          # repo root
OUT=site/public

copy() {  # copy <src> <dest>
  local src=$1 dst=$OUT/$2
  [[ -f "$src" ]] || { echo "missing: $src" >&2; return 1; }
  [[ -f "$dst" && "$dst" -nt "$src" ]] && return 0
  mkdir -p "$(dirname "$dst")"
  local size; size=$(stat -c %s "$src")
  if (( size > 1500000 )) && command -v gs >/dev/null; then
    gs -q -dNOPAUSE -dBATCH -dSAFER -sDEVICE=pdfwrite -dPDFSETTINGS=/ebook -dCompatibilityLevel=1.6 \
       -dDetectDuplicateImages=true -sOutputFile="$dst.tmp" "$src"
    if (( $(stat -c %s "$dst.tmp") < size )); then mv "$dst.tmp" "$dst"; else rm "$dst.tmp"; cp "$src" "$dst"; fi
  else
    cp "$src" "$dst"
  fi
  printf '%-40s %6d KB\n' "$2" $(( $(stat -c %s "$dst") / 1024 ))
}

# Reports (keep in step with REPORTS / DOCS in src/lib/site.ts)
copy 0_Documentation/n11034459_ProjectDeliveryReport_V2.pdf   reports/delivery-report.pdf
copy 0_Documentation/son_report.pdf                           reports/hardware-report.pdf
copy 0_Documentation/jared-assessment/CapstoneProjectProposal.pdf reports/control-proposal.pdf
copy "0_Documentation/Son's Project Proposal.pdf"             reports/hardware-proposal.pdf
copy "0_Documentation/Son's Project Progress Report.pdf"      reports/hardware-progress-report.pdf
copy 0_Documentation/schematic_ordered_vo.pdf                 reports/schematic-v0.pdf

# Datasheets kept in the repository
for f in 1_Datasheets/*.pdf; do [[ $f == *EcoFlow* ]] && continue; copy "$f" "datasheets/$(basename "$f")"; done
