#!/usr/bin/env python3
"""Build curated figure assets -> site/src/assets/figures/<group>/ and src/data/figures.json.

Edit FIGURES to add or remove figures. Each group is a list of specs:
  ("dir", "<repo-relative dir>", "<glob>")              - every match
  ("dir", "<repo-relative dir>", "<glob>", N)           - capped at N (sorted)
  ("regex", "<repo-relative dir>", "<glob>", [patterns], N) - round-robin over patterns, capped at N
  ("file", "<repo-relative path>")                      - single file (PNG preferred; .pdf rendered via pdftocairo)
  ("svg", "<repo-relative dir>", "<glob>")              - copy SVGs as-is
Any spec may end with an options dict, e.g. {"prefix": "mil_"} to prefix output names (avoids clashes).
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ASSETS, DATA, REPO, cache_dir, is_stale, pdf_to_png, rel, to_webp, write_json  # noqa: E402
from PIL import Image  # noqa: E402

LATEX_FIGS = "0_Documentation/jared-assessment/CapstoneDelivery_latex/figures"
ANALYSIS = "8_Results/analysis/out/figures"
MIL = "4_Simulink/1_MIL_Model_In_The_Loop"
QSPICE = "2_Qspice/Claude's outputs/PCB_Baseline/results"

FIGURES: dict[str, list[tuple]] = {
    "results": [
        ("dir", f"{LATEX_FIGS}/results", "*.png"),
    ],
    "misc": [
        ("file", f"{LATEX_FIGS}/misc/{n}.png") for n in
        ["pv_mismatch_1000_200", "pv_shading", "scope_200k", "scope_300k", "scope_400k",
         "scr01", "scr02", "scr03", "scr04", "thermal_100k", "thermal_lab_16oct", "thermal_solar_20oct"]
    ],
    "slides": [
        ("file", f"{LATEX_FIGS}/slides/page-01.png"),
        ("file", f"{LATEX_FIGS}/slides/page-07.png"),
        ("dir", f"{LATEX_FIGS}/slides", "img-*.png"),
    ],
    "analysis": [
        ("dir", f"{ANALYSIS}/energy", "*.png"),
        ("regex", f"{ANALYSIS}/compare", "*.png", [r"ripple", r"G_compare", r"S5_duty", r"S1_", r"S4_"], 20),
        ("regex", f"{ANALYSIS}/events", "*.png", [r"S02", r"B06", r"B01s"], 12),
        ("dir", f"{ANALYSIS}/hardware", "*.png", 21),
        ("dir", f"{ANALYSIS}/carpark_validate", "*.png", {"prefix": "carpark_"}),
        ("dir", f"{ANALYSIS}/mil_validate", "*.png", {"prefix": "mil_"}),
    ],
    "simulink": [
        ("dir", f"{MIL}/figs", "00_summary*.pdf"),
        ("dir", f"{MIL}/figs", "*_string.pdf", 11),
        ("dir", f"{MIL}/PV_figures", "*.png"),
    ],
    "qspice": [
        ("svg", QSPICE, "*.svg"),
        ("svg", f"{QSPICE}/fig", "*.svg"),
        ("svg", "8_Results/QSPICE_200kHz", "*.svg"),
    ],
}
MAX_EDGE, QUALITY = 1800, 85

missing: list[str] = []


def resolve(spec: tuple) -> list[Path]:
    if spec and isinstance(spec[-1], dict):
        spec = spec[:-1]
    kind = spec[0]
    if kind == "file":
        p = REPO / spec[1]
        if p.exists():
            return [p]
        alt = p.with_suffix(".pdf")
        if alt.exists():
            return [alt]
        missing.append(spec[1])
        return []
    d = REPO / spec[1]
    if not d.is_dir():
        missing.append(spec[1] + "/")
        return []
    files = sorted(d.glob(spec[2]))
    if kind == "regex":
        pats, cap = spec[3], spec[4]
        buckets = [[f for f in files if re.search(p, f.name)] for p in pats]
        picked: list[Path] = []
        while len(picked) < cap and any(buckets):
            for b in buckets:
                if b and len(picked) < cap:
                    f = b.pop(0)
                    if f not in picked:
                        picked.append(f)
        return picked
    if not files:
        missing.append(f"{spec[1]}/{spec[2]}")
    if len(spec) > 3 and isinstance(spec[3], int):
        files = files[: spec[3]]
    return files


def unique_name(stem: str, taken: set[str]) -> str:
    name, i = stem, 2
    while name in taken:
        name, i = f"{stem}_{i}", i + 1
    taken.add(name)
    return name


def main() -> int:
    records = []
    for group, specs in FIGURES.items():
        out = ASSETS / "figures" / group
        out.mkdir(parents=True, exist_ok=True)
        taken: set[str] = set()
        for spec in specs:
            opts = spec[-1] if isinstance(spec[-1], dict) else {}
            for src in resolve(spec):
                stem = unique_name(opts.get("prefix", "") + re.sub(r"[^A-Za-z0-9_.-]+", "_", src.stem), taken)
                if src.suffix.lower() == ".svg":
                    dst = out / f"{stem}.svg"
                    if is_stale(dst, src):
                        shutil.copy2(src, dst)
                    w = h = None
                    m = re.search(r'viewBox="[\d.\-]+\s+[\d.\-]+\s+([\d.]+)\s+([\d.]+)"', dst.read_text(errors="ignore")[:4000])
                    if m:
                        w, h = round(float(m.group(1))), round(float(m.group(2)))
                else:
                    raster = src
                    if src.suffix.lower() == ".pdf":
                        raster = pdf_to_png(src, cache_dir() / group / f"{stem}.png")
                    dst = out / f"{stem}.webp"
                    w, h = to_webp(raster, dst, MAX_EDGE, QUALITY)
                records.append({"group": group, "file": dst.name, "source": rel(src), "width": w, "height": h})
                print(f"  [{group}] {dst.name}  <-  {rel(src)}")
    write_json(DATA / "figures.json", records)
    counts = {g: sum(r["group"] == g for r in records) for g in FIGURES}
    print(f"figures: {len(records)} total {counts}")
    if missing:
        print("missing sources:\n  " + "\n  ".join(missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
