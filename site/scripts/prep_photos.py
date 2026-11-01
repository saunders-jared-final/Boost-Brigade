#!/usr/bin/env python3
"""Build photo assets: 0_Documentation/Photos/*.jpg -> site/src/assets/photos/*.webp (+ thumbs) and src/data/photos.json."""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ASSETS, DATA, REPO, to_webp, write_json  # noqa: E402
from PIL import Image  # noqa: E402

SRC = REPO / "0_Documentation" / "Photos"
JOURNEY = REPO / "0_Documentation/jared-assessment/CapstoneDelivery_latex/appendices/M_journey.tex"
OUT = ASSETS / "photos"
HERO = {"20261004_162523", "20261020_132132", "20261020_131809", "20261016_153331"}
EXIF_DT_ORIGINAL = 36867


def tex_clean(s: str) -> str:
    s = s.replace("\\,", "\u2009").replace("~", "\u00a0")
    s = re.sub(r"\\cref\{[^}]*\}", "", s)
    s = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?\{([^{}]*)\}", r"\2", s)  # \emph{x} -> x
    s = re.sub(r"\\([&%$#_])", r"\1", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_captions(tex: Path) -> dict[str, str]:
    caps: dict[str, str] = {}
    if not tex.exists():
        print(f"warning: {tex} missing, no captions", file=sys.stderr)
        return caps
    t = tex.read_text(encoding="utf-8")
    # \includegraphics[...]{stem}\caption{text}
    for m in re.finditer(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}\s*\\caption\{((?:[^{}]|\{[^{}]*\})*)\}", t):
        if not m.group(1).startswith("#"):
            caps.setdefault(m.group(1), tex_clean(m.group(2)))
    # \ph{stem}{caption}  (defined via \newcommand in the same file; takes precedence)
    for m in re.finditer(r"\\ph\{([^}]+)\}\{((?:[^{}]|\{[^{}]*\})*)\}", t):
        caps[m.group(1)] = tex_clean(m.group(2))
    return caps


def caption_for(stem: str, caps: dict[str, str]) -> str:
    if stem in caps:
        return caps[stem]
    for k, v in caps.items():  # e.g. tex uses IMG-20261014 for IMG-20261014-WA0000
        if stem.startswith(k):
            return v
    return ""


def photo_date(path: Path, im: Image.Image) -> str | None:
    try:
        raw = im.getexif().get_ifd(0x8769).get(EXIF_DT_ORIGINAL)
        if raw:
            return datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S").isoformat()
    except Exception:
        pass
    for pat, fmt in ((r"(?<!\d)(20\d{6}_\d{6})(?!\d)", "%Y%m%d_%H%M%S"), (r"(?<![\dA-F])(20\d{6})(?![\dA-F])", "%Y%m%d")):
        m = re.search(pat, path.stem)
        if m:
            try:
                return datetime.strptime(m.group(1), fmt).isoformat()
            except ValueError:
                pass
    return None


def tags_for(stem: str, date: str | None) -> list[str]:
    if stem.startswith(("Messenger_", "IMG-")):
        return ["misc"]
    if not date:
        return ["misc"]
    d = date[:10]
    if d <= "2026-09-30":
        return ["proto/pcb-arrival"]
    if "2026-10-01" <= d <= "2026-10-11":
        return ["assembly"]
    if "2026-10-12" <= d <= "2026-10-15":
        return ["bring-up"]
    if d == "2026-10-16":
        return ["bench-day"]
    if d == "2026-10-20":
        return ["carpark-day"]
    return ["misc"]


def main() -> int:
    if not SRC.is_dir():
        print(f"error: source dir missing: {SRC}", file=sys.stderr)
        return 1
    caps = parse_captions(JOURNEY)
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    files = sorted(p for p in SRC.iterdir() if p.suffix.lower() in (".jpg", ".jpeg"))
    for p in files:
        stem = p.stem
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", stem)  # e.g. "x(1)" -> "x_1_" (import-safe)
        with Image.open(p) as im:
            date = photo_date(p, im)
        w, h = to_webp(p, OUT / f"{safe}.webp", 1600, 82, transpose=True)
        to_webp(p, OUT / f"{safe}.thumb.webp", 480, 78, transpose=True)
        rec = {
            "file": f"{safe}.webp",
            "thumb": f"{safe}.thumb.webp",
            "width": w,
            "height": h,
            "date": date,
            "caption": caption_for(stem, caps),
            "tags": tags_for(stem, date),
        }
        if stem in HERO:
            rec["hero"] = True
        records.append(rec)
    records.sort(key=lambda r: (r["date"] is None, r["date"] or "", r["file"]))
    write_json(DATA / "photos.json", records)
    used = {s for s in caps if any(r["file"].startswith(s) for r in records)}
    print(f"photos: {len(records)} written to {OUT}; captions matched {len(used)}/{len(caps)}; "
          f"missing captions for: {sorted(set(caps) - used) or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
