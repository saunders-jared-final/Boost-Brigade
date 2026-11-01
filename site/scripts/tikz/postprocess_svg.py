#!/usr/bin/env python3
"""Make a dvisvgm / pdftocairo SVG theme-friendly for the Astro site.

  * pure black fills/strokes (#000, #000000, black, rgb(0,0,0)) -> currentColor
  * namespace @font-face families, text classes (.fN) and ids with the figure
    name, so several diagrams inlined on one page cannot clobber each other
    (dvisvgm subsets fonts per figure and reuses the names phvr8r, f1, f2 ...)
  * drop a full-size white background rect if one is present
  * add a viewBox if missing (keeps width/height)
  * verify the result parses as XML; print a one-line summary

usage: postprocess_svg.py IN.svg OUT.svg
"""
import os
import re
import sys
import xml.etree.ElementTree as ET

BLACK = re.compile(
    r"(?P<attr>\b(?:fill|stroke|stop-color|color))(?P<eq>\s*=\s*)(?P<q>['\"])"
    r"(?:#000000|#000|black|rgb\(\s*0\s*,\s*0\s*,\s*0\s*\))(?P=q)",
    re.I,
)
BLACK_CSS = re.compile(
    r"(?P<prop>\b(?:fill|stroke|stop-color|color))(?P<colon>\s*:\s*)"
    r"(?:#000000|#000|black|rgb\(\s*0\s*,\s*0\s*,\s*0\s*\))(?=\s*[;'\"}])",
    re.I,
)
WHITE = {"#fff", "#ffffff", "white", "rgb(255,255,255)", "rgb(255, 255, 255)"}
SVG_NS = "http://www.w3.org/2000/svg"


ID_OK = re.compile(r"[^A-Za-z0-9_-]")


def namespace(text, prefix):
    """Prefix font-family names, text.fN classes and element ids with `prefix`."""
    n = 0
    text, k = re.subn(r"font-family\s*:\s*([A-Za-z0-9_-]+)", lambda m: f"font-family:{prefix}-{m.group(1)}", text); n += k
    text, k = re.subn(r"text\.(f\d+)\s*\{", lambda m: f"text.{prefix}-{m.group(1)}{{", text); n += k
    text, k = re.subn(r"class=(['\"])(f\d+)\1", lambda m: f"class={m.group(1)}{prefix}-{m.group(2)}{m.group(1)}", text); n += k
    ids = set(re.findall(r"\bid=['\"]([^'\"]+)['\"]", text))
    for i in sorted(ids, key=len, reverse=True):
        text = re.sub(rf"\bid=(['\"]){re.escape(i)}\1", rf"id=\1{prefix}-{i}\1", text)
        text = re.sub(rf"#{re.escape(i)}(?=[)'\"\s])", f"#{prefix}-{i}", text)
    return text, n


def num(s):
    m = re.match(r"\s*([-+]?\d*\.?\d+(?:e[-+]?\d+)?)", s or "")
    return float(m.group(1)) if m else None


def main(src, dst):
    text = open(src, encoding="utf-8").read()
    prefix = "tikz-" + ID_OK.sub("_", os.path.splitext(os.path.basename(dst))[0])
    text, n_ns = namespace(text, prefix)

    text, n_attr = BLACK.subn(lambda m: f"{m['attr']}{m['eq']}{m['q']}currentColor{m['q']}", text)
    text, n_css = BLACK_CSS.subn(lambda m: f"{m['prop']}{m['colon']}currentColor", text)

    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")
    root = ET.fromstring(text)
    if root.tag != f"{{{SVG_NS}}}svg":
        sys.exit(f"{src}: root is not <svg>")

    width, height = num(root.get("width")), num(root.get("height"))
    if root.get("viewBox") is None and width and height:
        root.set("viewBox", f"0 0 {width:g} {height:g}")
    vb = [float(v) for v in root.get("viewBox").replace(",", " ").split()]
    vw, vh = vb[2], vb[3]

    # remove a background rect that covers (almost) the whole canvas and is white
    removed = 0
    parent_map = {c: p for p in root.iter() for c in p}
    for rect in list(root.iter(f"{{{SVG_NS}}}rect")):
        fill = (rect.get("fill") or "").strip().lower()
        style = rect.get("style") or ""
        m = re.search(r"fill\s*:\s*([^;]+)", style)
        if m:
            fill = m.group(1).strip().lower()
        rw, rh = num(rect.get("width")), num(rect.get("height"))
        if fill in WHITE and rw and rh and rw >= 0.98 * vw and rh >= 0.98 * vh:
            parent_map[rect].remove(rect)
            removed += 1

    out = ET.tostring(root, encoding="unicode")
    if not out.startswith("<?xml"):
        out = "<?xml version='1.0' encoding='UTF-8'?>\n" + out
    # re-parse to be sure what we write is well-formed
    ET.fromstring(out)
    with open(dst, "w", encoding="utf-8") as fh:
        fh.write(out)

    n_text = len(list(root.iter(f"{{{SVG_NS}}}text")))
    n_path = len(list(root.iter(f"{{{SVG_NS}}}path")))
    n_use = len(list(root.iter(f"{{{SVG_NS}}}use")))
    n_font = out.count("@font-face")
    print(
        f"{dst}: ok size={len(out.encode())}B black->currentColor={n_attr + n_css} "
        f"bg_rect_removed={removed} text_elems={n_text} paths={n_path} use={n_use} "
        f"fonts_embedded={n_font} namespaced={n_ns} viewBox='{root.get('viewBox')}'"
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
