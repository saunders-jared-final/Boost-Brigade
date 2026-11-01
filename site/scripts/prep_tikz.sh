#!/usr/bin/env bash
# Build the report's TikZ fragments into theme-friendly SVGs for the Astro site.
#
#   figures/tikz/<name>.tex  --wrap-->  latex -> dvisvgm (real text, woff2 fonts)
#                                       | fallback: pdflatex -> dvisvgm --pdf (text as paths)
#                                       | fallback: pdflatex -> pdftocairo -svg
#                            --post-->  site/src/assets/diagrams/<name>.svg
#
# Runnable from anywhere; idempotent (skips fragments whose SVG is newer than all
# of its inputs; pass -f to force).  Compiles in a scratch dir on the Linux
# filesystem because building on /mnt/c is ~10x slower.
#
#   TIKZ_BUILD=<dir>        scratch build dir   (default: ~/tikz_build, else /tmp)
#   TIKZ_ROUTE=dvi|pdf|cairo  force a conversion route instead of the cascade
#   FRAGMENTS="a b"         subset of fragment names to build
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SITE="$(cd "$HERE/.." && pwd)"
REPO="$(cd "$SITE/.." && pwd)"
SRC="$REPO/0_Documentation/jared-assessment/CapstoneDelivery_latex/figures/tikz"
TPL="$HERE/tikz/wrap.tex.in"
STYLES="$HERE/tikz/tikz_styles.tex"
POST="$HERE/tikz/postprocess_svg.py"
OUT="$SITE/src/assets/diagrams"

FORCE=0
[[ "${1:-}" == "-f" || "${1:-}" == "--force" ]] && FORCE=1

if [[ -z "${TIKZ_BUILD:-}" ]]; then
  if [[ -n "${HOME:-}" && -w "$HOME" ]]; then TIKZ_BUILD="$HOME/tikz_build"; else TIKZ_BUILD="/tmp/tikz_build_$(id -u)"; fi
fi
mkdir -p "$TIKZ_BUILD" "$TIKZ_BUILD/out" "$OUT"

for tool in latex pdflatex dvisvgm pdftocairo python3; do
  command -v "$tool" >/dev/null || { echo "prep_tikz: missing tool: $tool" >&2; exit 1; }
done

DEFAULT_FRAGMENTS="adc_timing control_loop coupled_inductor gain_pipeline nodal_n3 pipeline_vmodel shuffler_circuit state_machine system_arch timeline"
FRAGMENTS="${FRAGMENTS:-$DEFAULT_FRAGMENTS}"

cp -f "$STYLES" "$TIKZ_BUILD/tikz_styles.tex"

# newer_than FILE DEP...  -> 0 if FILE exists and is newer than every DEP
newer_than() { local f="$1"; shift; [[ -f "$f" ]] || return 1; for d in "$@"; do [[ "$f" -nt "$d" ]] || return 1; done; }

wrap() { # name classopts > wrapper.tex
  sed -e "s|@FRAGMENT@|$1|" -e "s|@CLASSOPTS@|$2|" "$TPL"
}

latex_run() { # engine wrapper-basename  (runs twice only if asked for a rerun)
  local eng="$1" base="$2"
  "$eng" -interaction=nonstopmode -halt-on-error "$base.tex" >"$base.stdout" 2>&1 || {
    echo "  $eng failed; last log lines:" >&2
    grep -A3 '^!' "$base.log" | head -20 >&2
    return 1
  }
  grep -q 'Rerun to get' "$base.log" && "$eng" -interaction=nonstopmode -halt-on-error "$base.tex" >"$base.stdout" 2>&1
  return 0
}

route_dvi() { # name -> raw svg path on stdout
  local n="$1" b="w_dvi_$1"
  wrap "$n" "tikz,border=6pt,dvisvgm" > "$b.tex"
  latex_run latex "$b" || return 1
  dvisvgm --font-format=woff2 --exact-bbox --optimize -o "raw_dvi_$n.svg" "$b.dvi" >"$b.dvisvgm.log" 2>&1 || { cat "$b.dvisvgm.log" >&2; return 1; }
  # unsupported specials / missing fonts mean the drawing is probably incomplete
  if grep -qiE 'warning|error' "$b.dvisvgm.log"; then
    echo "  dvisvgm (dvi) reported:" >&2; grep -iE 'warning|error' "$b.dvisvgm.log" >&2; return 1
  fi
  echo "raw_dvi_$n.svg"
}

pdf_build() { # name -> ensures w_pdf_<name>.pdf exists
  local n="$1" b="w_pdf_$1"
  [[ -f "$b.pdf" && "$b.pdf" -nt "$n.tex" && "$b.pdf" -nt tikz_styles.tex && "$b.pdf" -nt "$TPL" ]] && return 0
  wrap "$n" "tikz,border=6pt" > "$b.tex"
  latex_run pdflatex "$b"
}

route_pdf() {
  local n="$1" b="w_pdf_$1"
  pdf_build "$n" || return 1
  dvisvgm --pdf --font-format=woff2 --exact-bbox --optimize -o "raw_pdf_$n.svg" "$b.pdf" >"$b.dvisvgm.log" 2>&1 || { cat "$b.dvisvgm.log" >&2; return 1; }
  echo "raw_pdf_$n.svg"
}

route_cairo() {
  local n="$1" b="w_pdf_$1"
  pdf_build "$n" || return 1
  pdftocairo -svg "$b.pdf" "raw_cairo_$n.svg" || return 1
  echo "raw_cairo_$n.svg"
}

status=0
cd "$TIKZ_BUILD"
for n in $FRAGMENTS; do
  frag="$SRC/$n.tex"
  [[ -f "$frag" ]] || { echo "prep_tikz: no such fragment $frag" >&2; status=1; continue; }
  dst="$OUT/$n.svg"
  if (( ! FORCE )) && newer_than "$dst" "$frag" "$STYLES" "$TPL" "$POST" "${BASH_SOURCE[0]}"; then
    echo "$n: up to date"; continue
  fi
  cp -f "$frag" "$n.tex"
  echo "== $n"
  raw=""
  case "${TIKZ_ROUTE:-}" in
    dvi)   raw=$(route_dvi "$n")   || true ;;
    pdf)   raw=$(route_pdf "$n")   || true ;;
    cairo) raw=$(route_cairo "$n") || true ;;
    "")
      raw=$(route_dvi "$n") || { echo "  falling back to pdflatex + dvisvgm --pdf" >&2; raw=$(route_pdf "$n") || true; }
      [[ -n "$raw" ]] || { echo "  falling back to pdftocairo" >&2; raw=$(route_cairo "$n") || true; }
      ;;
    *) echo "prep_tikz: bad TIKZ_ROUTE=$TIKZ_ROUTE" >&2; exit 2 ;;
  esac
  if [[ -z "$raw" || ! -s "$raw" ]]; then echo "$n: FAILED" >&2; status=1; continue; fi
  # the post-processor derives its namespace prefix from the output basename, so keep it = <name>.svg
  python3 "$POST" "$raw" "out/$n.svg"
  cp -f "out/$n.svg" "$dst.tmp" && mv -f "$dst.tmp" "$dst"
  route="${raw#raw_}"; route="${route%%_*}"
  echo "  -> $dst  (route: $route)"
done
exit $status
