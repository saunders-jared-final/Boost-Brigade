#!/usr/bin/env python3
"""Extract curated figures from the two final reports (PDF) into src/assets/figures/{hw,ctrl}/.

Figures are located by their "Figure N:" caption on each page: the crop is the union of the
images and vector drawings between the previous body-text block and the caption. Rendered at
3x (216 dpi) and saved as WebP. Also renders the first page of every datasheet in 1_Datasheets
to src/assets/datasheets/<stem>.webp and the title-page render to figures/misc/hero_render.webp.

Needs: pip install --user pymupdf pillow
"""
from __future__ import annotations
import io, re, sys
from pathlib import Path
import pymupdf  # PyMuPDF
from PIL import Image

HERE = Path(__file__).resolve().parent
SITE = HERE.parent
REPO = SITE.parent
OUT = SITE / "src" / "assets" / "figures"

# (figure number -> output key); captions are kept in src/data/reportfigs.ts
SON = {
    1: "assembly_stencil", 2: "topology_ripple", 3: "topology_selected", 4: "recovery_ideal",
    5: "recovery_semireal", 6: "arch_initial", 7: "board_annotated", 8: "bench_waveforms",
    9: "bench_power", 10: "bench_leg_currents", 11: "ringing_400k", 12: "outdoor_setup",
    13: "pv_run2", 14: "pv_runs", 15: "pv_run3", 16: "gantt", 17: "qspice_halfbridge",
    18: "qspice_cuk", 19: "qspice_ideal_string", 20: "qspice_semireal", 21: "qspice_parasitic",
}
JARED = {
    1: "pv_curves", 2: "vmodel", 7: "dataflow", 9: "gain_pipeline", 10: "architecture",
    11: "state_machine", 12: "built_20oct", 14: "qspice_k03", 15: "duty_steps", 16: "bench_B06",
    17: "solar_S02", 18: "ref_step", 22: "derivation_n3", 23: "phase_portraits", 24: "root_locus",
    26: "sampling", 27: "mil_tests", 28: "mil_plant", 29: "mil_blocks", 30: "carpark_twin",
    31: "qspice_top", 32: "twin_variants", 33: "qspice_controller", 36: "scope_captures",
}
SOURCES = [
    (REPO / "0_Documentation/son_report.pdf", OUT / "hw", SON),
    (REPO / "0_Documentation/n11034459_ProjectDeliveryReport_V1.pdf", OUT / "ctrl", JARED),
]


def save_webp(pix: pymupdf.Pixmap, out: Path, max_edge=2200, quality=88):
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    img.thumbnail((max_edge, max_edge))
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "WEBP", quality=quality, method=6)


def extract(pdf: Path, outdir: Path, wanted: dict[int, str]) -> int:
    doc = pymupdf.open(pdf)
    n = 0
    for pno in range(len(doc)):
        page = doc[pno]
        blocks = page.get_text("dict")["blocks"]
        caps, body = [], []
        for b in blocks:
            if b["type"] != 0:
                continue
            txt = "".join(s["text"] for l in b["lines"] for s in l["spans"]).strip()
            sizes = [s["size"] for l in b["lines"] for s in l["spans"]]
            r = pymupdf.Rect(b["bbox"])
            m = re.match(r"^(Figure|Fig\.)\s*(\d+)[:.]", txt)
            if m:
                caps.append((int(m.group(2)), r))
            elif len(txt) > 60 and max(sizes) >= 9.5:
                body.append(r)
        if not caps:
            continue
        rects = [pymupdf.Rect(i["bbox"]) for i in page.get_image_info()]
        rects += [pymupdf.Rect(d["rect"]) for d in page.get_drawings()]
        for num, cr in caps:
            if num not in wanted:
                continue
            top = 0.0
            for r in body:
                if r.y1 <= cr.y0 and r.y1 > top:
                    top = r.y1
            for num2, cr2 in caps:
                if cr2.y1 <= cr.y0 and cr2.y1 > top:
                    top = cr2.y1
            region = None
            for r in rects:
                if r.y1 <= cr.y0 + 3 and r.y0 >= top - 3 and r.width > 30 and r.height > 15:
                    region = r if region is None else region | r
            if region is None:
                print(f"  !! no region for figure {num} on page {pno+1}", file=sys.stderr)
                continue
            region = (region + (-4, -4, 4, 4)) & page.rect
            pix = page.get_pixmap(matrix=pymupdf.Matrix(3, 3), clip=region, alpha=False)
            save_webp(pix, outdir / f"{wanted[num]}.webp")
            n += 1
    return n


def datasheets():
    out = SITE / "src" / "assets" / "datasheets"
    out.mkdir(parents=True, exist_ok=True)
    for pdf in sorted((REPO / "1_Datasheets").glob("*.pdf")):
        doc = pymupdf.open(pdf)
        pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(1.4, 1.4), alpha=False)
        save_webp(pix, out / f"{pdf.stem}.webp", max_edge=900, quality=80)
        print(f"  datasheet {pdf.stem}: {len(doc)} pages")


def hero():
    """Title-page CAD render of the delivery report at its native 1200 px."""
    doc = pymupdf.open(REPO / "0_Documentation/n11034459_ProjectDeliveryReport_V1.pdf")
    for info in doc[0].get_images(full=True):
        xref = info[0]
        base = doc.extract_image(xref)
        if base["width"] >= 900 and abs(base["width"] - base["height"]) > 50:  # the render, not the square logo
            img = Image.open(io.BytesIO(base["image"])).convert("RGB")
            img.save(OUT / "misc" / "hero_render.webp", "WEBP", quality=92, method=6)
            print(f"  hero render {img.size}")
            return


if __name__ == "__main__":
    for pdf, outdir, wanted in SOURCES:
        n = extract(pdf, outdir, wanted)
        print(f"{pdf.name}: {n}/{len(wanted)} figures -> {outdir.relative_to(SITE)}")
    datasheets()
    hero()
