# -*- coding: utf-8 -*-
"""
check_readability.py - looks at a Qspice .qsch the way a reader would

  python check_readability.py <file.qsch> [more.qsch ...]

For every sheet it
  1. measures each visible text with Qspice's text size (calibrated on a screenshot of the user's own sheet:
     font size about 160 sheet units, so roughly 100 units per character) and reports every place where a text
     touches another text, a wire or a symbol outline
  2. draws the sheet as <name>.svg next to this script, overlaps outlined in red

It does not replace opening the file in Qspice; it catches crowding before that.
"""
import math
import os
import sys

F = 160.0                 # font size of a size-1 text, sheet units
HERE = os.path.dirname(os.path.abspath(__file__))

W_UP = {"I": 0.278, "M": 0.833, "W": 0.944, "J": 0.5, "L": 0.556, "T": 0.611, "F": 0.611}
W_LO = {"i": 0.222, "l": 0.222, "j": 0.222, "f": 0.278, "t": 0.278, "r": 0.333, "m": 0.833, "w": 0.722,
        "s": 0.5, "c": 0.5, "k": 0.5, "v": 0.5, "x": 0.5, "y": 0.5, "z": 0.5}
W_PU = {" ": 0.278, ".": 0.278, ",": 0.278, ":": 0.278, ";": 0.278, "/": 0.278, "(": 0.333, ")": 0.333,
        "{": 0.334, "}": 0.334, "-": 0.333, "+": 0.584, "=": 0.584, "_": 0.556, "|": 0.26, "'": 0.191,
        "µ": 0.576, "¥": 0.556, "¬": 0.584}


def text_width(s, size=1.0):
    w = 0.0
    for ch in s:
        if ch in W_PU:
            w += W_PU[ch]
        elif ch.isupper():
            w += W_UP.get(ch, 0.667)
        elif ch.islower():
            w += W_LO.get(ch, 0.556)
        else:
            w += 0.556
    return w * F * size


# ----------------------------------------------------------------------------- parsing
def records(t, i):
    """Children of the record that starts at t[i] == '«'. Returns (head, children, next index)."""
    assert t[i] == "«"
    i += 1
    head, kids = [], []
    while i < len(t):
        c = t[i]
        if c == '"':
            j = t.index('"', i + 1)
            head.append(t[i:j + 1])
            i = j + 1
        elif c == "«":
            h, k, i = records(t, i)
            kids.append((h, k))
        elif c == "»":
            return "".join(head).strip(), kids, i + 1
        else:
            head.append(c)
            i += 1
    return "".join(head).strip(), kids, i


def nums(s):
    out, cur = [], ""
    for ch in s:
        if ch in "0123456789.-+eE" and not (ch in "eE" and not cur):
            cur += ch
        else:
            if cur:
                try:
                    out.append(float(cur))
                except ValueError:
                    pass
                cur = ""
    if cur:
        try:
            out.append(float(cur))
        except ValueError:
            pass
    return out


def fix_bom(s):
    if s.startswith("ï»¿"):
        try:
            return s[3:].encode("cp1252").decode("utf-8"), True
        except Exception:
            return s[3:], True
    return s, False


def parse_text(head):
    """'text (x,y) size just flag colour a b "string"' -> dict"""
    q = head.index('"')
    s = head[q + 1:head.rindex('"')]
    f = head[:q].split()
    x, y = nums(f[1])
    s, bom = fix_bom(s)
    return {"x": x, "y": y, "size": float(f[2]) or 1.0, "just": int(f[3]), "flag": int(f[4]), "s": s, "bom": bom}


def parse(path):
    t = open(path, "rb").read()[4:].decode("cp1252")
    head, kids, _ = records(t, t.index("«"))
    comps, wires, nets, texts, juncs = [], [], [], [], []
    for h, k in kids:
        if h.startswith("component"):
            f = h.split()
            cx, cy = nums(f[1])
            rot = int(f[2])
            sym = k[0][1] if k else []
            c = {"x": cx, "y": cy, "rot": rot, "prims": [], "texts": [], "pins": [], "type": "?", "fill": False}
            for sh, _sk in sym:
                if sh.startswith("type:"):
                    c["type"] = sh[5:].strip()
                elif sh.startswith(("line", "rect", "ellipse", "triangle")):
                    kind = sh.split()[0]
                    body = sh[:sh.index("0x")] if "0x" in sh else sh
                    c["prims"].append((kind, nums(body[len(kind):]), sh))
                elif sh.startswith("text"):
                    c["texts"].append(parse_text(sh))
                elif sh.startswith("pin"):
                    q = sh.index('"')
                    f2 = sh[:q].split()
                    px, py = nums(f2[1])
                    dx, dy = nums(f2[2])
                    c["pins"].append({"x": px, "y": py, "dx": dx, "dy": dy, "size": float(f2[3]), "just": int(f2[4]),
                                      "name": sh[q + 1:sh.rindex('"')]})
            c["ref"] = c["texts"][0]["s"] if c["texts"] else "?"
            comps.append(c)
        elif h.startswith("wire"):
            q = h.index('"')
            n = nums(h[:q])
            wires.append((n[0], n[1], n[2], n[3], h[q + 1:h.rindex('"')]))
        elif h.startswith("net"):
            q = h.index('"')
            f = h[:q].split()
            x, y = nums(f[1])
            nets.append({"x": x, "y": y, "size": float(f[2]), "just": int(f[3]), "s": h[q + 1:h.rindex('"')]})
        elif h.startswith("junction"):
            juncs.append(tuple(nums(h)))
        elif h.startswith("text"):
            texts.append(parse_text(h))
    return comps, wires, nets, texts, juncs


# ----------------------------------------------------------------------------- geometry
def rot_only(x, y, rot):
    for _ in range((rot % 8) // 2):
        x, y = -y, x
    return x, y


def xform(x, y, c):
    x, y = rot_only(x, y, c["rot"])
    if c["rot"] >= 8:
        x = -x
    return c["x"] + x, c["y"] + y


def just_of(code):
    base = code % 32
    h = {1: "start", 2: "end"}.get((base >> 2) & 3, "middle")
    v = {1: "below", 2: "above"}.get(base & 3, "middle")
    return h, v


def text_box(x, y, s, size, just):
    h, v = just_of(just)
    w = text_width(s, size)
    hh = 0.46 * F * size                      # half height of a centred line (cap height plus a little)
    x0 = {"start": x, "end": x - w, "middle": x - w / 2}[h]
    if v == "middle":
        y0, y1 = y - hh, y + hh
    elif v == "above":
        y0, y1 = y, y + 2 * hh
    else:
        y0, y1 = y - 2 * hh, y
    return (x0, y0, x0 + w, y1)


def prim_segments(c):
    segs, rects = [], []
    for kind, n, _raw in c["prims"]:
        if kind == "line":
            segs.append((xform(n[0], n[1], c), xform(n[2], n[3], c)))
        elif kind == "rect":
            p = [xform(n[0], n[1], c), xform(n[2], n[1], c), xform(n[2], n[3], c), xform(n[0], n[3], c)]
            segs += [(p[i], p[(i + 1) % 4]) for i in range(4)]
            xs, ys = [q[0] for q in p], [q[1] for q in p]
            rects.append((min(xs), min(ys), max(xs), max(ys)))
        elif kind == "ellipse":
            cx, cy = (n[0] + n[2]) / 2, (n[1] + n[3]) / 2
            rx, ry = abs(n[2] - n[0]) / 2, abs(n[3] - n[1]) / 2
            pts = [xform(cx + rx * math.cos(a * math.pi / 12), cy + ry * math.sin(a * math.pi / 12), c) for a in range(25)]
            segs += list(zip(pts[:-1], pts[1:]))
        elif kind == "triangle":
            p = [xform(n[0], n[1], c), xform(n[2], n[3], c), xform(n[4], n[5], c)]
            segs += [(p[i], p[(i + 1) % 3]) for i in range(3)]
    return segs, rects


def seg_hits_box(a, b, box, shrink=20):
    x0, y0, x1, y1 = box[0] + shrink, box[1] + shrink, box[2] - shrink, box[3] - shrink
    if x0 >= x1 or y0 >= y1:
        return False
    # Liang-Barsky
    dx, dy = b[0] - a[0], b[1] - a[1]
    p = [-dx, dx, -dy, dy]
    q = [a[0] - x0, x1 - a[0], a[1] - y0, y1 - a[1]]
    u0, u1 = 0.0, 1.0
    for pi, qi in zip(p, q):
        if pi == 0:
            if qi < 0:
                return False
        else:
            u = qi / pi
            if pi < 0:
                u0 = max(u0, u)
            else:
                u1 = min(u1, u)
    return u0 <= u1


def boxes_hit(a, b, gap=15):
    return a[0] < b[2] - gap and b[0] < a[2] - gap and a[1] < b[3] - gap and b[1] < a[3] - gap


def collect(comps, wires, nets, texts):
    """Every visible text as (label, box, kind, owner index)."""
    items = []
    for ci, c in enumerate(comps):
        for t in c["texts"]:
            if t["flag"] == 2:
                continue                                   # hidden attribute
            dx, dy = rot_only(t["x"], t["y"], c["rot"])
            items.append((f'{c["ref"]}: "{t["s"]}"', text_box(c["x"] + dx, c["y"] + dy, t["s"], t["size"], t["just"]),
                          "part", ci, (c["x"] + dx, c["y"] + dy, t)))
        for p in c["pins"]:
            if p["dx"] or p["dy"]:
                x, y = xform(p["x"], p["y"], c)
                items.append((f'{c["ref"]} pin "{p["name"]}"',
                              text_box(x + p["dx"], y + p["dy"], p["name"], p["size"], p["just"]), "pin", ci,
                              (x + p["dx"], y + p["dy"], {"s": p["name"], "size": p["size"], "just": p["just"]})))
    for n in nets:
        if n["s"].upper() == "GND":
            box = (n["x"] - 110, n["y"] - 160, n["x"] + 110, n["y"])          # the ground symbol
        else:
            h, v = just_of(n["just"])
            ox = {"start": 30, "end": -30}.get(h, 0)
            oy = {"above": 20, "below": -20}.get(v, 0)
            box = text_box(n["x"] + ox, n["y"] + oy, n["s"], n["size"], n["just"])
        items.append((f'label "{n["s"]}" at ({n["x"]:.0f},{n["y"]:.0f})', box, "label", None, (n["x"], n["y"], n)))
    for t in texts:
        items.append((f'note "{t["s"][:40]}"', text_box(t["x"], t["y"], t["s"], t["size"], t["just"]), "note", None,
                      (t["x"], t["y"], t)))
    return items


def check(path):
    comps, wires, nets, texts, juncs = parse(path)
    items = collect(comps, wires, nets, texts)
    problems, bad = [], set()
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if boxes_hit(items[i][1], items[j][1]):
                problems.append(f"text on text:   {items[i][0]}  <->  {items[j][0]}")
                bad.update((i, j))
    for i, (name, box, kind, owner, _a) in enumerate(items):
        for (x1, y1, x2, y2, net) in wires:
            if seg_hits_box((x1, y1), (x2, y2), box):
                problems.append(f"text on wire:   {name}  <->  wire {net} ({x1:.0f},{y1:.0f})-({x2:.0f},{y2:.0f})")
                bad.add(i)
        for ci, c in enumerate(comps):
            segs, rects = prim_segments(c)
            inside_block = kind in ("part", "pin") and owner == ci and c["type"] in ("X", "")
            if inside_block:
                continue                                   # names and pin names live inside a block on purpose
            hit = any(seg_hits_box(a, b, box) for a, b in segs)
            if not hit:
                cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
                hit = any(r[0] < cx < r[2] and r[1] < cy < r[3] for r in rects)
            if hit and not (kind == "pin" and owner == ci):
                problems.append(f"text on symbol: {name}  <->  {c['ref']}")
                bad.add(i)
    return comps, wires, nets, texts, juncs, items, problems, bad


# ----------------------------------------------------------------------------- drawing
def draw(path, out_svg, crop=None, px_per_unit=None, width_px=1500):
    comps, wires, nets, texts, juncs, items, problems, bad = check(path)
    xs, ys = [], []
    for _n, b, _k, _o, _a in items:
        xs += [b[0], b[2]]
        ys += [b[1], b[3]]
    for w in wires:
        xs += [w[0], w[2]]
        ys += [w[1], w[3]]
    for c in comps:
        for a, b in prim_segments(c)[0]:
            xs += [a[0], b[0]]
            ys += [a[1], b[1]]
    if crop is None:
        crop = (min(xs) - 300, min(ys) - 300, max(xs) + 300, max(ys) + 300)
    x0, y0, x1, y1 = crop
    s = px_per_unit or width_px / (x1 - x0)
    X = lambda x: (x - x0) * s
    Y = lambda y: (y1 - y) * s
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {(x1 - x0) * s:.0f} {(y1 - y0) * s:.0f}" '
         f'width="{(x1 - x0) * s:.0f}" height="{(y1 - y0) * s:.0f}" font-family="Arial, Helvetica, sans-serif">',
         f'<rect width="100%" height="100%" fill="#ffffe6"/>']
    blue = "#0000c8"
    for c in comps:
        for kind, n, raw in c["prims"]:
            if kind == "line":
                a, b = xform(n[0], n[1], c), xform(n[2], n[3], c)
                o.append(f'<line x1="{X(a[0]):.1f}" y1="{Y(a[1]):.1f}" x2="{X(b[0]):.1f}" y2="{Y(b[1]):.1f}" stroke="{blue}" stroke-width="1.3"/>')
            elif kind == "rect":
                p = [xform(n[0], n[1], c), xform(n[2], n[3], c)]
                rx0, rx1 = sorted((X(p[0][0]), X(p[1][0])))
                ry0, ry1 = sorted((Y(p[0][1]), Y(p[1][1])))
                fill = "#ffff00" if "0x4000000" in raw else (blue if "0x3000000" in raw else "none")
                o.append(f'<rect x="{rx0:.1f}" y="{ry0:.1f}" width="{max(rx1 - rx0, 0.8):.1f}" height="{max(ry1 - ry0, 0.8):.1f}" fill="{fill}" stroke="{blue}" stroke-width="1.3"/>')
            elif kind == "ellipse":
                a, b = xform(n[0], n[1], c), xform(n[2], n[3], c)
                o.append(f'<ellipse cx="{X((a[0] + b[0]) / 2):.1f}" cy="{Y((a[1] + b[1]) / 2):.1f}" rx="{abs(b[0] - a[0]) / 2 * s:.1f}" ry="{abs(b[1] - a[1]) / 2 * s:.1f}" fill="none" stroke="{blue}" stroke-width="1.3"/>')
            elif kind == "triangle":
                p = [xform(n[0], n[1], c), xform(n[2], n[3], c), xform(n[4], n[5], c)]
                o.append('<polygon points="' + " ".join(f"{X(q[0]):.1f},{Y(q[1]):.1f}" for q in p) + f'" fill="{blue}"/>')
    for (a, b, c2, d, _n) in wires:
        o.append(f'<line x1="{X(a):.1f}" y1="{Y(b):.1f}" x2="{X(c2):.1f}" y2="{Y(d):.1f}" stroke="{blue}" stroke-width="1.6"/>')
    for j in juncs:
        o.append(f'<rect x="{X(j[0]) - 3:.1f}" y="{Y(j[1]) - 3:.1f}" width="6" height="6" fill="{blue}"/>')
    colour = {"part": "#000000", "pin": "#000000", "label": "#d00000", "note": "#0000c8"}
    for i, (name, box, kind, owner, (ax, ay, t)) in enumerate(items):
        if kind == "label" and t["s"].upper() == "GND":
            gx, gy = X(ax), Y(ay)
            o.append(f'<polygon points="{gx - 9:.1f},{gy:.1f} {gx + 9:.1f},{gy:.1f} {gx:.1f},{gy + 12:.1f}" fill="none" stroke="{blue}" stroke-width="1.3"/>')
            continue
        h, v = just_of(t["just"])
        fs = F * t["size"] * s
        if kind == "label":
            ax += {"start": 30, "end": -30}.get(h, 0)
            ay += {"above": 20, "below": -20}.get(v, 0)
        base = {"middle": 0.36, "above": -0.12, "below": 0.80}[v] * fs
        col = colour[kind]
        if kind == "note" and t.get("flag") == 0:
            col = "#000000"
        txt = t["s"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        o.append(f'<text x="{X(ax):.1f}" y="{Y(ay) + base:.1f}" font-size="{fs:.1f}" text-anchor="{h}" fill="{col}">{txt}</text>')
        if i in bad:
            o.append(f'<rect x="{X(box[0]):.1f}" y="{Y(box[3]):.1f}" width="{(box[2] - box[0]) * s:.1f}" height="{(box[3] - box[1]) * s:.1f}" fill="none" stroke="#ff0000" stroke-width="1.5"/>')
    o.append("</svg>")
    with open(out_svg, "w", encoding="utf-8") as f:
        f.write("\n".join(o))
    return problems


if __name__ == "__main__":
    files = sys.argv[1:] or [os.path.join(HERE, "..", "HalfBridge_Driver.qsch"),
                             os.path.join(HERE, "..", "HalfBridge_Driver_Testbench.qsch")]
    report = []
    for f in files:
        name = os.path.splitext(os.path.basename(f))[0]
        problems = draw(f, os.path.join(HERE, name + ".svg"))
        report.append(f"{name}: {len(problems)} overlap(s)")
        report += ["   " + p for p in problems]
    open(os.path.join(HERE, "report.txt"), "w", encoding="utf-8").write("\n".join(report) + "\n")
    print("\n".join(report))
