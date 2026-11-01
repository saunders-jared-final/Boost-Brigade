#!/usr/bin/env bash
# Build the web-ready glTF models for the Astro showcase site.
#
#   site/public/models/board.glb        KiCad board: components + pads + silkscreen + soldermask
#   site/public/models/board_full.glb   same + tracks + zones (kept only if < 12 MB)
#   site/public/models/enclosure.glb    mechanical assembly (stage 2, see README_models.md)
#
# Idempotent; runnable from anywhere (WSL).  Never touches the original KiCad/CAD files:
# a PATCHED COPY of the .kicad_pcb is made in site/scripts/work/ (gitignored).
#
# Requirements: WSL with node >= 22 + npm, python3, KiCad 10 for Windows (kicad-cli.exe).
# Optional (stage 2): cadquery in python3 (pip install --user cadquery)  OR  work/enclosure.obj
# exported from Fusion 360 by hand (see README_models.md).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
WORK="$SCRIPT_DIR/work"
OUT="$REPO/site/public/models"
KICAD_CLI="${KICAD_CLI:-/mnt/c/Program Files/KiCad/10.0/bin/kicad-cli.exe}"
KICAD_3D_WIN="${KICAD_3D_WIN:-C:/Program Files/KiCad/10.0/share/kicad/3dmodels}"   # kicad-cli does not expand KICAD10_3DMODEL_DIR itself
SRC_PCB="$REPO/5_Kicad/Version 0 project/Version 0 project.kicad_pcb"
LIBS="$REPO/5_Kicad/libs"
STEP="$REPO/9_Mechanical_Enclosure_CAD/shuffler_assembly.step"
BOARD_RATIO="${BOARD_RATIO:-0.5}"        # meshopt simplify target (vertex ratio) for the board
ENCL_RATIO="${ENCL_RATIO:-0.3}"          # ... for the enclosure
FORCE="${FORCE:-0}"                      # FORCE=1 re-runs kicad-cli even if the raw export is up to date

mkdir -p "$WORK" "$OUT"
log() { printf '\n== %s\n' "$*"; }
mb() { awk -v b="$(stat -c %s "$1")" 'BEGIN{printf "%.2f MB", b/1e6}'; }
winpath() { wslpath -w "$1"; }                       # WSL -> Windows path for kicad-cli
winpath_fwd() { wslpath -w "$1" | sed 's#\\#/#g'; }  # same, with forward slashes (as KiCad stores them)

# ----------------------------------------------------------------------------- node deps
# @gltf-transform API + meshoptimizer for glb_pipeline.mjs (installed under site/scripts/node_modules, gitignored)
if [ ! -d "$SCRIPT_DIR/node_modules/@gltf-transform/functions" ]; then
  log "installing node deps for glb_pipeline.mjs"
  (cd "$SCRIPT_DIR" && npm install --no-audit --no-fund)
fi
GLTF="npx --yes @gltf-transform/cli@4"

# =============================================================================
# Stage 1: KiCad board -> board.glb (+ board_full.glb)
# =============================================================================
log "stage 1: KiCad board"
if [ ! -x "$KICAD_CLI" ] && [ ! -f "$KICAD_CLI" ]; then
  echo "kicad-cli not found at $KICAD_CLI (set KICAD_CLI=...)" >&2; exit 1
fi

# 1a. patched copy of the PCB.  Six footprints point at another author's absolute path
#     (C:/Users/benha/dev/solar-shuffler-kicad/...) and two Wurth modules use a relative
#     path that only resolves from the original footprint library; rewrite both to the
#     absolute Windows path of 5_Kicad/libs.  Everything else (KICAD10_3DMODEL_DIR,
#     kicad-embed://) is untouched.  The project's own fp-lib-table is not needed for a
#     .kicad_pcb export (footprints are embedded), so a bare copy in work/ is enough.
PATCHED_DIR="$WORK/kicad/Version 0 project"
PATCHED="$PATCHED_DIR/Version 0 project.kicad_pcb"
mkdir -p "$PATCHED_DIR"
LIBS_WIN="$(winpath_fwd "$LIBS")"
sed -e "s#C:/Users/benha/dev/solar-shuffler-kicad/#${LIBS_WIN}/#g" \
    -e "s#\"\.\./\.\./KiCad_WPME-FDSM (rev26d)/#\"${LIBS_WIN}/KiCad_WPME-FDSM (rev26d)/#g" \
    "$SRC_PCB" > "$PATCHED.tmp"
if [ ! -f "$PATCHED" ] || ! cmp -s "$PATCHED.tmp" "$PATCHED"; then mv "$PATCHED.tmp" "$PATCHED"; else rm "$PATCHED.tmp"; fi
cp -n "$REPO/5_Kicad/Version 0 project/Version 0 project.kicad_pro" "$PATCHED_DIR/" 2>/dev/null || true
echo "patched copy: $PATCHED"
echo "remaining non-standard model refs:"; grep -o '(model "[^"]*"' "$PATCHED" | grep -v KICAD10_3DMODEL_DIR | sort | uniq -c | sed 's/^/   /'

# 1b. kicad-cli exports (Windows binary -> Windows paths).  The same KiCad options as the
#     3D viewer "export GLB": substitute STEP for VRML, skip DNP, fuse, 0.05 mm merge.
COMMON=(--subst-models --no-dnp --fuse-shapes --min-distance 0.05mm
        --include-pads --include-silkscreen --include-soldermask
        -D "KICAD10_3DMODEL_DIR=$KICAD_3D_WIN"
        -D "KIPRJMOD=$(winpath_fwd "$REPO/5_Kicad/Version 0 project")")
export_glb() {  # export_glb <out.glb> [extra kicad-cli flags...]
  local out="$1"; shift
  if [ "$FORCE" != 1 ] && [ -f "$out" ] && [ "$out" -nt "$PATCHED" ] && [ "$out" -nt "$SRC_PCB" ]; then
    echo "up to date: $out"; return
  fi
  "$KICAD_CLI" pcb export glb -f "${COMMON[@]}" "$@" -o "$(winpath "$out")" "$(winpath "$PATCHED")" \
      2>&1 | tee "${out%.glb}.log" | grep -E "File not found|Could not|Export time|created" | sort | uniq -c | sed 's/^/   /'
  [ -f "$out" ] || { echo "kicad-cli produced no output" >&2; exit 1; }
}

export_glb "$WORK/board.raw.glb"
export_glb "$WORK/board_full.raw.glb" --include-tracks --include-zones

# 1c. optimise WITHOUT flattening the scene graph (gltf-transform optimize would merge all
#     175 refdes nodes into ~10 anonymous ones).  glb_pipeline.mjs keeps one node per refdes,
#     names the board layers, joins primitives per part, welds, simplifies and meshopt-compresses.
node "$SCRIPT_DIR/glb_pipeline.mjs" "$WORK/board.raw.glb" "$OUT/board.glb" --board --ratio "$BOARD_RATIO"
echo "board.glb: $(mb "$OUT/board.glb")"

node "$SCRIPT_DIR/glb_pipeline.mjs" "$WORK/board_full.raw.glb" "$WORK/board_full.glb" --board --ratio "$BOARD_RATIO"
if [ "$(stat -c %s "$WORK/board_full.glb")" -lt $((12 * 1000 * 1000)) ]; then
  mv "$WORK/board_full.glb" "$OUT/board_full.glb"; echo "board_full.glb: $(mb "$OUT/board_full.glb") (kept)"
else
  echo "board_full.glb too large ($(mb "$WORK/board_full.glb")) - not kept"; rm -f "$OUT/board_full.glb"
fi

# =============================================================================
# Stage 2: enclosure assembly -> enclosure.glb
#   preferred: STEP -> cadquery (step_to_glb.py), one named node per solid
#   fallback : work/enclosure.obj exported from Fusion 360 by hand (README_models.md)
# =============================================================================
log "stage 2: enclosure"
ENCL_RAW="$WORK/enclosure.raw.glb"
if python3 -c "import cadquery" 2>/dev/null && [ -f "$STEP" ]; then
  if [ "$FORCE" = 1 ] || [ ! -f "$ENCL_RAW" ] || [ "$STEP" -nt "$ENCL_RAW" ]; then
    python3 "$SCRIPT_DIR/step_to_glb.py" "$STEP" "$ENCL_RAW"
  else
    echo "up to date: $ENCL_RAW"
  fi
elif [ -f "$WORK/enclosure.obj" ]; then
  echo "cadquery not available - using hand-exported $WORK/enclosure.obj"
  if [ "$FORCE" = 1 ] || [ ! -f "$ENCL_RAW" ] || [ "$WORK/enclosure.obj" -nt "$ENCL_RAW" ]; then
    (cd "$WORK" && npx --yes obj2gltf -i enclosure.obj -o "$ENCL_RAW")
  fi
else
  echo "SKIPPED: neither cadquery (pip install --user cadquery) nor $WORK/enclosure.obj available."
  echo "         See $SCRIPT_DIR/README_models.md for the manual Fusion 360 export."
fi
if [ -f "$ENCL_RAW" ]; then
  node "$SCRIPT_DIR/glb_pipeline.mjs" "$ENCL_RAW" "$OUT/enclosure.glb" --ratio "$ENCL_RATIO"
  echo "enclosure.glb: $(mb "$OUT/enclosure.glb")"
fi

# =============================================================================
log "summary"
ls -la "$OUT"/*.glb
for f in "$OUT"/*.glb; do python3 "$SCRIPT_DIR/glb_nodes.py" "$f" 0 | head -3; done
