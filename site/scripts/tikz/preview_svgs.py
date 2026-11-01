#!/usr/bin/env python3
"""Write an HTML page that inlines every diagram SVG twice (light and dark
background) so font embedding, currentColor and name collisions can be checked
in a real browser.  usage: preview_svgs.py OUT.html [SVG...]  (default: all in
site/src/assets/diagrams).  Screenshot e.g. with
  msedge --headless=new --screenshot=out.png --window-size=1600,5200 file:///.../OUT.html
"""
import glob
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DIR = os.path.normpath(os.path.join(HERE, "..", "..", "src", "assets", "diagrams"))

out = sys.argv[1]
files = sys.argv[2:] or sorted(glob.glob(os.path.join(DEFAULT_DIR, "*.svg")))
rows = []
for f in files:
    svg = re.sub(r"<\?xml[^>]*\?>\s*", "", open(f, encoding="utf-8").read())
    name = os.path.basename(f)
    rows.append(f'<h3>{name}</h3><div class="row"><div class="cell light">{svg}</div><div class="cell dark">{svg}</div></div>')
html = (
    "<!doctype html><html><head><meta charset='utf-8'><style>"
    "body{margin:0;font-family:sans-serif;background:#888}h3{margin:6px 10px;font-size:14px;color:#000}"
    ".row{display:flex}.cell{width:50%;padding:10px;box-sizing:border-box}"
    ".light{background:#fff;color:#111}.dark{background:#1b1f27;color:#e8e8e8}"
    "svg{width:100%;height:auto;display:block}</style></head><body>" + "".join(rows) + "</body></html>"
)
open(out, "w", encoding="utf-8").write(html)
print(f"wrote {out} ({len(files)} figures, {len(html)//1024} KB)")
