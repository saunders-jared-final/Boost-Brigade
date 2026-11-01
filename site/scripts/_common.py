"""Shared helpers for the site asset-prep scripts (prep_photos, prep_figures, prep_notebooks)."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageOps

SCRIPTS = Path(__file__).resolve().parent
SITE = SCRIPTS.parent
REPO = SITE.parent
ASSETS = SITE / "src" / "assets"
DATA = SITE / "src" / "data"


def rel(p: Path) -> str:
    """Repo-relative POSIX path for provenance fields."""
    return Path(p).resolve().relative_to(REPO).as_posix()


def is_stale(dst: Path, *srcs: Path) -> bool:
    """True if dst is missing or older than any of its sources (idempotency check)."""
    if not dst.exists():
        return True
    m = dst.stat().st_mtime
    return any(Path(s).stat().st_mtime > m for s in srcs)


def to_webp(src: Path, dst: Path, max_edge: int, quality: int, *, transpose: bool = False) -> tuple[int, int]:
    """Convert src raster to webp at dst, fitting the long edge to max_edge. Returns (w, h) of the output.

    Skips the conversion when dst is newer than src, but always returns the output size.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not is_stale(dst, src):
        with Image.open(dst) as im:
            return im.size
    with Image.open(src) as im:
        if transpose:
            im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA" if "A" in im.getbands() or im.mode == "P" else "RGB")
        im.thumbnail((max_edge, max_edge), Image.LANCZOS)
        im.save(dst, "WEBP", quality=quality, method=6)
        return im.size


def pdf_to_png(pdf: Path, out_png: Path, dpi: int = 150) -> Path:
    """Render page 1 of a PDF to PNG via pdftocairo (idempotent)."""
    out_png.parent.mkdir(parents=True, exist_ok=True)
    if not is_stale(out_png, pdf):
        return out_png
    stem = out_png.with_suffix("")  # pdftocairo appends .png
    subprocess.run(["pdftocairo", "-png", "-r", str(dpi), "-singlefile", str(pdf), str(stem)], check=True)
    return out_png


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def cache_dir() -> Path:
    """Scratch dir for intermediate PDF->PNG renders (kept out of the site tree)."""
    d = Path(tempfile.gettempdir()) / "boost-brigade-site-prep"
    d.mkdir(parents=True, exist_ok=True)
    return d
