#!/usr/bin/env python3
"""Extract image/png outputs from 3_Analytical/shuffler_notebooks/*.ipynb -> site/src/assets/notebooks/<nb>/<nn>.webp
and src/data/notebooks.json with the nearest preceding markdown heading as caption."""
from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ASSETS, DATA, REPO, cache_dir, is_stale, to_webp, write_json  # noqa: E402
import nbformat  # noqa: E402

SRC = REPO / "3_Analytical" / "shuffler_notebooks"
OUT = ASSETS / "notebooks"
MAX_EDGE, QUALITY = 1600, 85


def main() -> int:
    nbs = sorted(SRC.glob("*.ipynb"))
    if not nbs:
        print(f"error: no notebooks in {SRC}", file=sys.stderr)
        return 1
    records = []
    for nbp in nbs:
        name = nbp.stem
        nb = nbformat.read(nbp, as_version=4)
        heading = ""
        idx = 0
        outdir = OUT / name
        for cell in nb.cells:
            if cell.cell_type == "markdown":
                for line in cell.source.splitlines():
                    m = re.match(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$", line)
                    if m:
                        heading = re.sub(r"[*_`]", "", m.group(1)).strip()
                continue
            if cell.cell_type != "code":
                continue
            for out in cell.get("outputs", []):
                png = out.get("data", {}).get("image/png")
                if not png:
                    continue
                idx += 1
                outdir.mkdir(parents=True, exist_ok=True)
                dst = outdir / f"{idx:02d}.webp"
                if is_stale(dst, nbp):
                    tmp = cache_dir() / "notebooks" / name / f"{idx:02d}.png"
                    tmp.parent.mkdir(parents=True, exist_ok=True)
                    tmp.write_bytes(base64.b64decode(png))
                    w, h = to_webp(tmp, dst, MAX_EDGE, QUALITY)
                else:
                    from PIL import Image
                    with Image.open(dst) as im:
                        w, h = im.size
                records.append({"notebook": name, "index": idx, "file": f"{name}/{dst.name}",
                                "heading": heading, "width": w, "height": h})
        print(f"  {name}: {idx} images")
    write_json(DATA / "notebooks.json", records)
    print(f"notebooks: {len(records)} images from {len(nbs)} notebooks -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
