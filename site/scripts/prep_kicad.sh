#!/usr/bin/env bash
# Export the KiCad schematic sheets and PCB layers as SVG for the interactive viewers
# on the PCB page (site/public/kicad/{sch,pcb}). Uses the Windows kicad-cli from WSL.
# Idempotent; outputs are committed because CI has no KiCad.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SITE="$(cd "$HERE/.." && pwd)"
REPO="$(cd "$SITE/.." && pwd)"
KICAD_CLI="${KICAD_CLI:-/mnt/c/Program Files/KiCad/10.0/bin/kicad-cli.exe}"
PROJ="$REPO/5_Kicad/Version 0 project"
OUT="$SITE/public/kicad"
mkdir -p "$OUT/sch" "$OUT/pcb"
winpath() { wslpath -w "$1"; }

echo "== schematic sheets"
TMP="$(mktemp -d)"
"$KICAD_CLI" sch export svg --exclude-drawing-sheet --no-background-color \
  --output "$(winpath "$TMP")" "$(winpath "$PROJ/Version 0 project.kicad_sch")" | grep -c Plotted || true
# normalise names: "Version 0 project-Shuffle Converter 1-Gate Drivers.svg" -> "shuffle-converter-1-gate-drivers.svg"
for f in "$TMP"/*.svg; do
  b="$(basename "$f" .svg)"; b="${b#Version 0 project}"; b="${b#-}"; [ -z "$b" ] && b="root"
  b="$(echo "$b" | tr 'A-Z' 'a-z' | sed 's/[^a-z0-9]\+/-/g; s/-$//')"
  cp "$f" "$OUT/sch/$b.svg"; echo "   $b.svg ($(du -k "$f" | cut -f1) kB)"
done
rm -rf "$TMP"

echo "== pcb layers"
# the patched copy made by prep_models.sh (absolute 3D model paths) is fine for 2D plots too
PCB="$HERE/work/kicad/Version 0 project/Version 0 project.kicad_pcb"
[ -f "$PCB" ] || PCB="$PROJ/Version 0 project.kicad_pcb"
for L in F.Cu In1.Cu In2.Cu In3.Cu In4.Cu B.Cu F.SilkS B.SilkS F.Mask B.Mask Edge.Cuts; do
  "$KICAD_CLI" pcb export svg --mode-single --page-size-mode 2 --exclude-drawing-sheet --black-and-white \
    --layers "$L" --output "$(winpath "$OUT/pcb/$L.svg")" "$(winpath "$PCB")" >/dev/null
  echo "   $L.svg ($(du -k "$OUT/pcb/$L.svg" | cut -f1) kB)"
done
ls -la "$OUT/sch" "$OUT/pcb" | wc -l

echo "== recolour pcb layers (fill/stroke -> currentColor, white -> var(--hole))"
for f in "$OUT"/pcb/*.svg; do
  sed -i -e 's/fill:#FFFFFF/fill:var(--hole,#fff)/g' -e 's/stroke:#FFFFFF/stroke:var(--hole,#fff)/g' \
         -e 's/fill:#[0-9A-Fa-f]\{6\}/fill:currentColor/g' -e 's/stroke:#[0-9A-Fa-f]\{6\}/stroke:currentColor/g' "$f"
done
python3 "$HERE/kicad_index.py"
