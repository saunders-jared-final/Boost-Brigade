"""
qsch_render.py - draw a Qspice .qsch schematic (or a cropped part of it) as SVG.

Used by build_book.py so that every schematic in the build book is the real stage file, not a
separate sketch.  Handles the records written by qsch_writer.py (and Qspice's own files for the
same primitives): component/symbol with line, rect, ellipse, triangle, text, pin; wire; net; junction.

  python qsch_render.py stages/S3.qsch out.svg --crop 8600,-3200,13900,900 --scale 0.14 --highlight MTA1,MBA1
"""

import re
import sys

LT, GT = "\xab", "\xbb"


# ----------------------------------------------------------------------------- parsing
def _records(text, start):
    """Parse «...» records starting at index `start` (just after a '«'). Returns (list_of_records, end_index).
    A record is (head_string, children) where head_string is the text up to the first child or the
    closing '»' and children is a list of records."""
    out = []
    i = start
    while i < len(text):
        if text[i] == GT:
            return out, i + 1
        if text[i] == LT:
            j = i + 1
            head = []
            children = []
            in_quote = False
            while j < len(text):
                ch = text[j]
                if ch == '"':
                    in_quote = not in_quote
                if in_quote:                       # « » inside quoted strings (directive BOM bytes) are text
                    head.append(ch)
                    j += 1
                    continue
                if ch == LT:
                    sub, j2 = _records(text, j)      # parse one level: returns siblings until the '»' of the parent
                    children.extend(sub)
                    j = j2
                    # _records consumed the closing '»' of THIS record, so we are done with it
                    out.append(("".join(head).strip(), children))
                    break
                if ch == GT:
                    out.append(("".join(head).strip(), children))
                    j += 1
                    break
                head.append(ch)
                j += 1
            i = j
        else:
            i += 1
    return out, i


def parse_qsch(path):
    data = open(path, "rb").read()
    if data[:4] == b"\xff\xd8\xff\xdb":
        data = data[4:]
    text = data.decode("cp1252", "replace")
    recs, _ = _records(text, 0)
    # top record is «schematic ...»
    sch = recs[0] if recs and recs[0][0].startswith("schematic") else ("schematic", recs)
    return sch[1]


_NUM = r"(-?\d+(?:\.\d+)?)"


def parse_symbol(children):
    sym = {"prims": [], "pins": [], "texts": [], "type": "", "name": ""}
    for head, kids in children:
        if head.startswith("type:"):
            sym["type"] = head.split(":", 1)[1].strip()
        elif head.startswith("line "):
            m = re.match(r"line \(" + _NUM + "," + _NUM + r"\) \(" + _NUM + "," + _NUM + r"\)", head)
            sym["prims"].append(("line", [float(v) for v in m.groups()]))
        elif head.startswith("rect "):
            m = re.match(r"rect \(" + _NUM + "," + _NUM + r"\) \(" + _NUM + "," + _NUM + r"\) \S+ \S+ \S+ (\S+) (\S+)", head)
            vals = [float(v) for v in m.groups()[:4]]
            sym["prims"].append(("rect", vals + [m.group(5), m.group(6)]))
        elif head.startswith("ellipse "):
            m = re.match(r"ellipse \(" + _NUM + "," + _NUM + r"\) \(" + _NUM + "," + _NUM + r"\)", head)
            sym["prims"].append(("ellipse", [float(v) for v in m.groups()]))
        elif head.startswith("triangle "):
            m = re.match(r"triangle \(" + _NUM + "," + _NUM + r"\) \(" + _NUM + "," + _NUM + r"\) \(" + _NUM + "," + _NUM + r"\)", head)
            sym["prims"].append(("triangle", [float(v) for v in m.groups()]))
        elif head.startswith("text "):
            m = re.match(r"text \(" + _NUM + "," + _NUM + r"\) (\S+) (\S+) (\S+) \S+ \S+ \S+ \"(.*)\"", head, re.S)
            if m:
                sym["texts"].append({"x": float(m.group(1)), "y": float(m.group(2)), "size": float(m.group(3)),
                                     "just": int(m.group(4)), "flag": int(m.group(5)), "s": m.group(6)})
        elif head.startswith("pin "):
            m = re.match(r"pin \(" + _NUM + "," + _NUM + r"\) \(" + _NUM + "," + _NUM + r"\) \S+ (\S+) \S+ \S+ \S+ \"(.*)\"", head)
            if m:
                sym["pins"].append({"x": float(m.group(1)), "y": float(m.group(2)), "dx": float(m.group(3)),
                                    "dy": float(m.group(4)), "just": int(m.group(5)), "name": m.group(6)})
    return sym


def parse_schematic(path, want_texts=False):
    comps, wires, nets, juncs, texts = [], [], [], [], []
    for head, kids in parse_qsch(path):
        if head.startswith("text ") and want_texts:
            m = re.match(r"text \(" + _NUM + "," + _NUM + r"\) (\S+) (\S+) (\S+) \S+ \S+ \S+ \"(.*)\"", head, re.S)
            if m:
                s = m.group(6)
                if s.startswith("ï»¿"):          # directive / comment marker bytes read as cp1252
                    s = s[3:].encode("cp1252", "replace").decode("utf-8", "replace")
                texts.append({"x": float(m.group(1)), "y": float(m.group(2)), "size": float(m.group(3)),
                              "flag": int(m.group(5)), "s": s})
            continue
        if head.startswith("component "):
            m = re.match(r"component \(" + _NUM + "," + _NUM + r"\) (\d+) (\d+)", head)
            x, y, rot = float(m.group(1)), float(m.group(2)), int(m.group(3))
            symrec = [k for k in kids if k[0].startswith("symbol")]
            if not symrec:
                continue
            sym = parse_symbol(symrec[0][1])
            sym["name"] = symrec[0][0].split(" ", 1)[1].strip() if " " in symrec[0][0] else ""
            ref = sym["texts"][0]["s"] if sym["texts"] else "?"
            comps.append({"x": x, "y": y, "rot": rot, "sym": sym, "ref": ref})
        elif head.startswith("wire "):
            m = re.match(r"wire \(" + _NUM + "," + _NUM + r"\) \(" + _NUM + "," + _NUM + r"\) \"(.*)\"", head)
            wires.append(([float(v) for v in m.groups()[:4]], m.group(5)))
        elif head.startswith("net "):
            m = re.match(r"net \(" + _NUM + "," + _NUM + r"\) \S+ (\S+) \S+ \"(.*)\"", head)
            nets.append({"x": float(m.group(1)), "y": float(m.group(2)), "just": int(m.group(3)), "s": m.group(4)})
        elif head.startswith("junction "):
            m = re.match(r"junction \(" + _NUM + "," + _NUM + r"\)", head)
            juncs.append((float(m.group(1)), float(m.group(2))))
    if want_texts:
        return comps, wires, nets, juncs, texts
    return comps, wires, nets, juncs


# ----------------------------------------------------------------------------- geometry
def xform(px, py, comp):
    """Symbol-local (x up) -> sheet coordinates, applying Qspice rotation code (see qsch_writer._rot)."""
    rot = comp["rot"]
    mirror = rot >= 8
    for _ in range((rot % 8) // 2):
        px, py = -py, px
    if mirror:
        px = -px
    return comp["x"] + px, comp["y"] + py


def just_of(code):
    """Anchor and vertical alignment of a Qspice justification code (see qsch_writer.SymbolDef.text_records)."""
    base = code % 32
    return {1: "start", 2: "end"}.get((base >> 2) & 3, "middle"), {1: "top", 2: "bottom"}.get(base & 3, "middle")


class Svg:
    def __init__(self, crop, scale, font_units=85):
        self.x0, self.y0, self.x1, self.y1 = crop        # sheet coords, y up
        self.scale = scale
        self.font = font_units
        self.w = (self.x1 - self.x0) * scale
        self.h = (self.y1 - self.y0) * scale
        self.parts = []

    def X(self, x):
        return (x - self.x0) * self.scale

    def Y(self, y):
        return (self.y1 - y) * self.scale

    def inside(self, x, y, margin=300):
        return self.x0 - margin <= x <= self.x1 + margin and self.y0 - margin <= y <= self.y1 + margin

    def line(self, pts, colour, width=1.4, dash=None):
        d = " ".join(f"{self.X(x):.1f},{self.Y(y):.1f}" for x, y in pts)
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        self.parts.append(f'<polyline points="{d}" fill="none" stroke="{colour}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"{extra}/>')

    def poly(self, pts, colour, fill):
        d = " ".join(f"{self.X(x):.1f},{self.Y(y):.1f}" for x, y in pts)
        self.parts.append(f'<polygon points="{d}" fill="{fill}" stroke="{colour}" stroke-width="1.4" stroke-linejoin="round"/>')

    def ellipse(self, x1, y1, x2, y2, colour, fill="none"):
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        rx, ry = abs(x2 - x1) / 2, abs(y2 - y1) / 2
        self.parts.append(f'<ellipse cx="{self.X(cx):.1f}" cy="{self.Y(cy):.1f}" rx="{rx * self.scale:.1f}" ry="{ry * self.scale:.1f}" fill="{fill}" stroke="{colour}" stroke-width="1.4"/>')

    def dot(self, x, y, colour):
        self.parts.append(f'<circle cx="{self.X(x):.1f}" cy="{self.Y(y):.1f}" r="{max(2.0, 30 * self.scale):.1f}" fill="{colour}"/>')

    def text(self, x, y, s, colour, size=1.0, anchor="start", weight="normal", cls="", valign="middle"):
        fs = self.font * size * self.scale
        if fs < 5.5:
            return
        s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        base = {"middle": 0.35, "top": 0.95, "bottom": -0.15}[valign]      # baseline offset from the anchor
        self.parts.append(f'<text x="{self.X(x):.1f}" y="{self.Y(y) + fs * base:.1f}" font-size="{fs:.1f}" text-anchor="{anchor}" fill="{colour}" font-weight="{weight}"{cls}>{s}</text>')

    def render(self, title=None):
        head = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w:.0f} {self.h:.0f}" '
                f'font-family="IBM Plex Mono, Menlo, Consolas, monospace" class="qsch">')
        return head + "".join(self.parts) + "</svg>"


JUST_ANCHOR = {0: "middle", 1: "start", 2: "end", 7: "start", 11: "middle", 13: "start", 14: "end"}


def render(path, crop, scale, highlight=(), hide_texts=False, hide_refs=(), colours=None):
    """Render the schematic region `crop` = (x0, y0, x1, y1) in sheet units at `scale` px/unit.
    `highlight`: iterable of reference designators drawn in the accent colour, the rest muted."""
    colours = colours or {"acc": "#b5652a", "ink": "#3b4a44", "muted": "#8a9a92", "wire": "#4b5b53",
                          "label": "#1f6b46", "fill_acc": "#f3e3d6", "fill": "#eef2f0", "directive": "#1b2d55"}
    comps, wires, nets, juncs, sheet_texts = parse_schematic(path, want_texts=True)
    hl = {h.lower() for h in highlight}
    hide = {h.lower() for h in hide_refs}
    svg = Svg(crop, scale)
    # free-standing sheet text: comments (flag 1) in muted ink, directives (flag 0) in blue
    if not hide_texts:
        for t in sheet_texts:
            if svg.inside(t["x"], t["y"], 0):
                col = colours["muted"] if t["flag"] == 1 else colours["directive"]
                svg.text(t["x"], t["y"], t["s"], col, size=t["size"] or 1.0, anchor="start",
                         weight="600" if (t["size"] or 1.0) > 1.1 else "normal")
    # wires first
    for (x1, y1, x2, y2), _net in wires:
        if svg.inside(x1, y1) or svg.inside(x2, y2):
            svg.line([(x1, y1), (x2, y2)], colours["wire"], width=1.6)
    for (x, y) in juncs:
        if svg.inside(x, y):
            svg.dot(x, y, colours["wire"])
    for c in comps:
        ref = c["ref"]
        if ref.lower() in hide:
            continue
        sym = c["sym"]
        pts_all = [xform(p["x"], p["y"], c) for p in sym["pins"]] or [(c["x"], c["y"])]
        if not any(svg.inside(x, y) for x, y in pts_all) and not svg.inside(c["x"], c["y"]):
            continue
        new = ref.lower() in hl
        col = colours["acc"] if new else colours["ink"]
        fill = colours["fill_acc"] if new else colours["fill"]
        for kind, v in sym["prims"]:
            if kind == "line":
                svg.line([xform(v[0], v[1], c), xform(v[2], v[3], c)], col, width=2.0 if new else 1.4)
            elif kind == "rect":
                x1, y1, x2, y2, fcode = v[0], v[1], v[2], v[3], v[5]
                corners = [xform(x1, y1, c), xform(x2, y1, c), xform(x2, y2, c), xform(x1, y2, c)]
                if fcode == "0x3000000":       # solid plate (capacitor plates, source marks)
                    svg.poly(corners, col, col)
                elif fcode == "0x4000000":     # subcircuit box: light fill
                    svg.poly(corners, col, fill)
                else:
                    svg.poly(corners, col, "none")
            elif kind == "ellipse":
                (ax, ay), (bx, by) = xform(v[0], v[1], c), xform(v[2], v[3], c)
                svg.ellipse(min(ax, bx), min(ay, by), max(ax, bx), max(ay, by), col)
            elif kind == "triangle":
                svg.poly([xform(v[0], v[1], c), xform(v[2], v[3], c), xform(v[4], v[5], c)], col, col if not new else colours["fill_acc"])
        if hide_texts:
            continue
        r = c["rot"] % 8
        for i, t in enumerate(sym["texts"]):
            if t["flag"] == 2 and scale < 0.15:
                continue                                   # parameter lines only when there is room
            txt = t["s"]
            if i == 1 and len(txt) > 16:
                txt = txt.split("(")[0].split("=")[0] + "(…)"  # long source expressions: keyword only, the netlist has the rest
            dx, dy = t["x"], t["y"]                        # Qspice: offsets rotate with the symbol, no mirroring
            for _ in range(r // 2):
                dx, dy = -dy, dx
            anchor, valign = just_of(t["just"])
            svg.text(c["x"] + dx, c["y"] + dy, txt, col if i == 0 else colours["ink"], size=(t["size"] or 1.0),
                     anchor=anchor, valign=valign, weight="600" if i == 0 else "normal")
        if scale >= 0.12:
            for p in sym["pins"]:
                if p["dx"] or p["dy"]:
                    x, y = xform(p["x"] + p["dx"], p["y"] + p["dy"], c)
                    anchor, valign = just_of(p["just"])
                    svg.text(x, y, p["name"], colours["muted"], size=0.7, anchor=anchor, valign=valign)
    if not hide_texts:
        # net labels: the justification code says which side of the point the text sits on (as in Qspice)
        for n in nets:
            if not svg.inside(n["x"], n["y"], 0):
                continue
            anchor, valign = just_of(n["just"])
            x = n["x"] + {"start": 40, "end": -40}.get(anchor, 0)
            y = n["y"] + {"top": -30, "bottom": 30}.get(valign, 0)
            svg.text(x, y, n["s"], colours["label"], size=0.9, anchor=anchor, valign=valign, weight="600")
    return svg.render()


def added_refs(cir_new, cir_old):
    """Reference designators present in cir_new but not in cir_old (both .cir netlists)."""
    def refs(p):
        out = set()
        if not p:
            return out
        for ln in open(p, "rb").read().decode("cp1252", "replace").splitlines():
            t = ln.strip()
            if t and t[0] not in ".*/" and not t.startswith("//"):
                out.add(t.split()[0].lower())
        return out
    return refs(cir_new) - refs(cir_old)


if __name__ == "__main__":
    args = sys.argv[1:]
    src, out = args[0], args[1]
    crop = (0, -10000, 10000, 1000)
    scale, hl = 0.1, ()
    for i, a in enumerate(args):
        if a == "--crop":
            crop = tuple(float(v) for v in args[i + 1].split(","))
        if a == "--scale":
            scale = float(args[i + 1])
        if a == "--highlight":
            hl = args[i + 1].split(",")
    open(out, "w", encoding="utf-8").write(render(src, crop, scale, hl))
    print("wrote", out)
