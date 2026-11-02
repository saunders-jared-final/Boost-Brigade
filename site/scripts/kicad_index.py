#!/usr/bin/env python3
"""Index reference designators in the exported KiCad SVGs -> src/data/kicad_index.json

kicad-cli writes every label as an invisible <text x y> element (plus stroked paths), so the
schematic sheet and the board position of each refdes can be read straight from the SVGs.
Positions are in SVG user units (mm of the sheet / board) of the file's viewBox.
"""
from __future__ import annotations
import json, re
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent
SCH = SITE / "public/kicad/sch"
PCB = SITE / "public/kicad/pcb"
REF = re.compile(r"^(?:[A-Z]{1,3}\d+[A-Z]?(?:_[A-Z0-9]+)?|XT60_\d|TP\d+|SW\d|S\d)$")
TEXT = re.compile(r'<text x="([\d.]+)" y="([\d.]+)"[^>]*>([^<]*)</text>')
VB = re.compile(r'viewBox="([\d. ]+)"')

def scan(svg: Path):
    s = svg.read_text(encoding="utf-8", errors="replace")
    vb = [float(v) for v in VB.search(s).group(1).split()]
    out = {}
    for x, y, t in TEXT.findall(s):
        t = t.strip()
        if REF.match(t) and t not in out:
            out[t] = (round(float(x), 2), round(float(y), 2))
    return vb, out

index = {"sheets": {}, "board": {}}
for svg in sorted(SCH.glob("*.svg")):
    vb, refs = scan(svg)
    index["sheets"][svg.stem] = {"viewBox": vb, "refs": refs}
    print(f"{svg.stem}: {len(refs)} refdes")
vb, refs = scan(PCB / "F.SilkS.svg")
index["board"] = {"viewBox": vb, "refs": refs}
print(f"board silkscreen: {len(refs)} refdes")
(SITE / "src/data/kicad_index.json").write_text(json.dumps(index, indent=1))
