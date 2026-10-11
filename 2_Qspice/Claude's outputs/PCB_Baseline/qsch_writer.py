"""
qsch_writer.py - minimal writer for Qspice (.qsch) schematic files.

File format facts (verified against QUX.exe -Netlist on QSPICE build Sep 2026):
  * 4-byte magic FF D8 FF DB, then text in Windows-1252, LF line endings.
  * Record delimiters are the single bytes 0xAB / 0xBB (the cp1252 glyphs are guillemets).
  * SPICE directives / comments are «text …» records whose string starts with the bytes
    EF BB BF; the rest of THAT string is UTF-8 (everything else in the file is cp1252).
  * Every symbol is embedded in its «component» record.  QUX netlists the pins of a symbol
    in declaration order, the first «text» is the reference, the second is the value/model,
    further «text» records (flag 2) are appended to the netlist line as instance parameters.
  * Nets are joined by exact coordinate match of wire ends and pins; a «net» label placed on a
    wire end names the net.  The label "GND" is the SPICE ground node (netlists as 0).
  * «library file: name» on a symbol makes QUX add ".lib name" once at the end of the netlist.

Coordinate system: x to the right, y UP, grid of 100 units.
"""

import math

MAGIC = b"\xff\xd8\xff\xdb"
LT, GT = "\xab", "\xbb"          # « »
_BOM = "\x00BOM\x00"              # placeholder replaced by EF BB BF when writing

# --------------------------------------------------------------------------- primitives
def p_line(x1, y1, x2, y2):
    return f"{LT}line ({x1},{y1}) ({x2},{y2}) 0 0 0x1000000 -1 -1{GT}"

def p_rect(x1, y1, x2, y2, style="body"):
    fill = {"body": "0x2000000", "plate": "0x3000000", "box": "0x4000000"}[style]
    colour = "0xff0000" if style == "box" else "0x1000000"
    return f"{LT}rect ({x1},{y1}) ({x2},{y2}) 0 0 0 {colour} {fill} -1 0 -1{GT}"

def p_ellipse(x1, y1, x2, y2):
    return f"{LT}ellipse ({x1},{y1}) ({x2},{y2}) 0 0 0 0x1000000 0x1000000 -1 -1{GT}"

def p_triangle(x1, y1, x2, y2, x3, y3):
    return f"{LT}triangle ({x1},{y1}) ({x2},{y2}) ({x3},{y3}) 0 0 0x1000000 0x2000000 -1 -1{GT}"

def p_text(x, y, s, just=7, flag=0, size=1):
    return f"{LT}text ({x},{y}) {size} {just} {flag} 0x1000000 -1 -1 \"{s}\"{GT}"

def p_pin(x, y, name, dx=0, dy=0, just=0):
    return f"{LT}pin ({x},{y}) ({dx},{dy}) 1 {just} 0 0x0 -1 \"{name}\"{GT}"


# --------------------------------------------------------------------------- symbols
class SymbolDef:
    """A symbol: SPICE type letter, drawing primitives, pins [(name, x, y)] in netlist order."""

    def __init__(self, name, stype, description, prims, pins, libfile=None,
                 ref_pos=(100, 150), val_pos=(100, -150), extra_pos=(100, -250), text_just=7):
        self.name, self.stype, self.description = name, stype, description
        self.prims, self.pins, self.libfile = prims, pins, libfile
        self.ref_pos, self.val_pos, self.extra_pos, self.text_just = ref_pos, val_pos, extra_pos, text_just

    def text_records(self, ref, value, extra, rot, label_side="above"):
        """Qspice conventions, read off hand-drawn sheets: a text offset is rotated with the symbol but never
        mirrored; the justification code is a base (bits 2-3 horizontal: 1 = text runs right from the anchor,
        2 = runs left, 3 = centred; bits 0-1 vertical: 1 = text below the anchor, 2 = above, 3 = centred; 0 = centred)
        plus 96 / 64 / 32 for 90 / 180 / 270 degrees so the text stays upright. Labels are chosen in screen space
        (ref beside or above the body, value next to it, parameters below) and converted back to symbol space."""
        r, mirror = rot % 8, rot >= 8
        flag = {0: 0, 2: 96, 4: 64, 6: 32}[r]

        def local(sx, sy):                       # symbol-space offset that rotates onto the wanted screen offset
            for _ in range((4 - r // 2) % 4):
                sx, sy = -sy, sx
            return sx, sy

        recs = []

        def put(sx, sy, text, base, tflag=0):
            lx, ly = local(sx, sy)
            recs.append(p_text(lx, ly, text, just=base + flag, flag=tflag))

        (ax, ay), (vx, vy), (ex, ey) = self.ref_pos, self.val_pos, self.extra_pos
        if self.text_just == 0:                  # box symbol: texts centred inside it, parameter lines below
            if r in (2, 6):                      # standing box: labels and parameters beside it on the right
                hh = -ey - 100
                put(hh + 40, 60, ref, 7)
                put(hh + 40, -60, value, 7)
                for i, e in enumerate(extra):
                    put(hh + 40, -160 - 100 * i, e, 7, 2)
            else:
                put(ax, ay, ref, 0)
                put(vx, vy, value, 0)
                for i, e in enumerate(extra):
                    put(ex, ey - 100 * i, e, 0, 2)
        elif r in (2, 6):                        # two-terminal part lying flat: "ref value" on one line above it
            d = max(ax, 60)                      # (or below it, for the lower one of a stacked pair)
            if label_side == "above":
                put(-30, d, ref, 10)             # right-justified, above the anchor
                put(30, d, value, 6)             # left-justified, above the anchor
                for i, e in enumerate(extra):
                    put(0, -d - 100 * i, e, 13, 2)
            else:                                # one text height lower still, under a neighbour's parameter line
                put(-30, -d - 100, ref, 9)       # right-justified, below the anchor
                put(30, -d - 100, value, 5)      # left-justified, below the anchor
                for i, e in enumerate(extra):
                    put(0, -d - 100 * (i + 2), e, 13, 2)
        else:                                    # upright part: beside the body, on the side away from a mirror
            sgn, base = (-1, 11) if mirror else (1, 7)
            put(sgn * ax, ay, ref, base)
            put(sgn * vx, vy, value, base)
            for i, e in enumerate(extra):
                put(sgn * ex, ey - 100 * i, e, base, 2)
        return recs

    def lines(self, ref, value, extra=(), rot=0, label_side="above"):
        out = [f"{LT}symbol {self.name}", f"  {LT}type: {self.stype}{GT}",
               f"  {LT}description: {self.description}{GT}"]
        if self.libfile:
            out.append(f"  {LT}library file: {self.libfile}{GT}")
        out.append(f"  {LT}shorted pins: false{GT}")
        out += ["  " + p for p in self.prims]
        out += ["  " + t for t in self.text_records(ref, value, extra, rot, label_side)]
        for pin in self.pins:
            n, x, y = pin[:3]
            dx, dy, just = (pin[3], pin[4], pin[5]) if len(pin) > 3 else (0, 0, 0)
            out.append("  " + p_pin(x, y, n, dx, dy, just))
        out.append(GT)
        return out


def _two_pin_prims_R():
    return [p_line(0, -200, 0, -150), p_line(0, 150, 0, 200), p_rect(50, -150, -50, 150, "body")]

def _two_pin_prims_C():
    return [p_line(0, 200, 0, 40), p_line(0, -40, 0, -200),
            p_rect(-130, -40, 130, -30, "plate"), p_rect(-130, 30, 130, 40, "plate")]

def _two_pin_prims_L():
    pr = [p_line(0, 200, 0, 150), p_line(0, -150, 0, -200)]
    for i in range(3):
        y = 100 - 100 * i
        pr.append(p_ellipse(-45, y + 50, 45, y - 50))
    return pr

def _source_prims(kind):
    pr = [p_line(0, -130, 0, -200), p_line(0, 200, 0, 130), p_ellipse(-130, 130, 130, -130)]
    if kind == "V":
        pr += [p_rect(-25, 77, 25, 73, "plate"), p_rect(-2, 50, 2, 100, "plate"), p_rect(-25, -73, 25, -77, "plate")]
    elif kind == "I":
        pr += [p_line(0, -80, 0, 80), p_triangle(0, 90, -30, 30, 30, 30)]
    elif kind == "B":
        pr += [p_line(-60, -40, -20, 40), p_line(-20, 40, 20, -40), p_line(20, -40, 60, 40)]
    return pr

def _diode_prims():
    return [p_line(100, 80, -100, 80), p_line(0, 200, 0, 80), p_line(0, -200, 0, -70),
            p_triangle(0, 80, 100, -70, -100, -70)]

def _nmos_prims():
    return [p_line(100, 200, 100, 150), p_line(100, -150, 100, -200), p_line(-100, 150, -100, -150),
            p_line(-100, 0, -200, 0), p_line(100, -150, -50, -150), p_line(100, 150, -50, 150),
            p_line(-50, 150, -50, -150), p_triangle(70, -150, -25, -125, -25, -175)]


def sym_R():
    return SymbolDef("R", "R", "Resistor", _two_pin_prims_R(), [("1", 0, 200), ("2", 0, -200)],
                     ref_pos=(80, 60), val_pos=(80, -60), extra_pos=(80, -160))

def sym_C():
    return SymbolDef("C", "C", "Capacitor", _two_pin_prims_C(), [("1", 0, 200), ("2", 0, -200)],
                     ref_pos=(150, 100), val_pos=(150, -100), extra_pos=(150, -200))

def sym_L():
    return SymbolDef("L", "L", "Inductor", _two_pin_prims_L(), [("1", 0, 200), ("2", 0, -200)],
                     ref_pos=(80, 60), val_pos=(80, -60), extra_pos=(80, -160))

def sym_V():
    return SymbolDef("V", "V", "Independent Voltage Source", _source_prims("V"), [("+", 0, 200), ("-", 0, -200)])

def sym_I():
    return SymbolDef("I", "I", "Current Source", _source_prims("I"), [("+", 0, 200), ("-", 0, -200)])

def sym_B():
    return SymbolDef("B", "B", "Behavioral Source", _source_prims("B"), [("+", 0, 200), ("-", 0, -200)])

def sym_D(libfile):
    return SymbolDef("D", "D", "Diode", _diode_prims(), [("A", 0, -200), ("K", 0, 200)], libfile=libfile,
                     ref_pos=(120, 150), val_pos=(120, -150))

def sym_NMOS(libfile):
    return SymbolDef("NMOS", "MN", "N-channel MOSFET", _nmos_prims(), [("D", 100, 200), ("G", -200, 0), ("S", 100, -200)],
                     libfile=libfile, ref_pos=(200, 150), val_pos=(200, -150), extra_pos=(200, -250))

def sym_box(name, description, w, h, pins, libfile=None, stype="X"):
    """Rectangular subcircuit symbol. pins: list of (name, x, y) on the box outline (netlist order)."""
    hw, hh = w // 2, h // 2
    prims = [p_rect(-hw, -hh, hw, hh, "box")]
    pin_defs = []
    for (n, x, y) in pins:
        # pin name is drawn by Qspice at the pin's label offset (inside the box edge)
        if x <= -hw:
            pin_defs.append((n, x, y, 60, -40, 13))
        elif x >= hw:
            pin_defs.append((n, x, y, -60, -40, 14))
        elif y >= hh:
            pin_defs.append((n, x, y, 0, -90, 7))
        else:
            pin_defs.append((n, x, y, 0, 60, 11))
    return SymbolDef(name, stype, description, prims, pin_defs, libfile=libfile,
                     ref_pos=(0, 60), val_pos=(0, -60), extra_pos=(0, -hh - 100), text_just=0)


# --------------------------------------------------------------------------- schematic
def _rot(dx, dy, rot):
    """Rotation codes as used in Qspice files (verified with QUX -Netlist): 0=0deg, 2=90deg CCW,
    4=180deg, 6=270deg; +8 = mirrored about the vertical axis (x -> -x) AFTER the rotation."""
    mirror = rot >= 8
    for _ in range((rot % 8) // 2):
        dx, dy = -dy, dx
    if mirror:
        dx = -dx
    return dx, dy


class Placed:
    def __init__(self, ref, x, y, rot, sym):
        self.ref, self.x, self.y, self.rot = ref, x, y, rot
        self.pin = {}
        for pin in sym.pins:
            n, px, py = pin[:3]
            dx, dy = _rot(px, py, rot)
            self.pin[n] = (x + dx, y + dy)


class Schematic:
    def __init__(self):
        self.lines = []          # component/text/net/junction records
        self.wires = []          # (x1,y1,x2,y2,net)
        self.labels = []         # (x,y,net,just)
        self.pin_points = []     # absolute pin coordinates (for junction detection)
        self.placed = {}

    # ----- components
    def add(self, sym, x, y, ref, value, extra=(), rot=0, label_side="above"):
        self.lines.append(f"  {LT}component ({x},{y}) {rot} 0")
        self.lines += ["    " + l for l in sym.lines(ref, value, extra, rot, label_side)]
        self.lines.append(f"  {GT}")
        p = Placed(ref, x, y, rot, sym)
        self.placed[ref] = p
        self.pin_points += list(p.pin.values())
        return p

    # ----- wiring
    def wire(self, pts, net):
        """Polyline through pts [(x,y),...] on the named net."""
        for (x1, y1), (x2, y2) in zip(pts[:-1], pts[1:]):
            if (x1, y1) != (x2, y2):
                self.wires.append((x1, y1, x2, y2, net))

    def label(self, x, y, net, just=13):
        self.labels.append((x, y, net, just))

    def stub(self, pt, net, direction, length=200, just=None):
        """Short wire from a pin position outward, ending in a net label."""
        x, y = pt
        dx, dy = {"up": (0, length), "down": (0, -length), "left": (-length, 0), "right": (length, 0)}[direction]
        self.wire([(x, y), (x + dx, y + dy)], net)
        if just is None:                 # text on the far side of the label point, away from the stub
            just = {"up": 14, "down": 13, "left": 11, "right": 7}[direction]
        self.label(x + dx, y + dy, net, just)

    # ----- text
    def directive(self, x, y, text):
        self.lines.append(f"  " + p_text(x, y, _BOM + text, just=7, flag=0))

    def comment(self, x, y, text, size=1):
        self.lines.append(f"  " + p_text(x, y, _BOM + text, just=7, flag=1, size=size))

    # ----- output
    def _junctions(self):
        from collections import Counter
        ends = Counter()
        for (x1, y1, x2, y2, _n) in self.wires:
            ends[(x1, y1)] += 1
            ends[(x2, y2)] += 1
        pins = Counter(self.pin_points)
        pts = set()
        for pt, c in ends.items():
            if c + pins.get(pt, 0) >= 3:
                pts.add(pt)
        # T junctions: a wire end sitting on the interior of another (axis-aligned) wire
        for pt in list(ends.keys()):
            x, y = pt
            for (x1, y1, x2, y2, _n) in self.wires:
                if (x, y) in ((x1, y1), (x2, y2)):
                    continue
                if x1 == x2 == x and min(y1, y2) < y < max(y1, y2):
                    pts.add(pt)
                elif y1 == y2 == y and min(x1, x2) < x < max(x1, x2):
                    pts.add(pt)
        return sorted(pts)

    def to_bytes(self):
        out = bytearray(MAGIC)
        body = [f"{LT}schematic"] + self.lines
        for (x, y, n, j) in self.labels:
            body.append(f"  {LT}net ({x},{y}) 1 {j} 0 \"{n}\"{GT}")
        for (x, y) in self._junctions():
            body.append(f"  {LT}junction ({x},{y}){GT}")
        for (x1, y1, x2, y2, n) in self.wires:
            body.append(f"  {LT}wire ({x1},{y1}) ({x2},{y2}) \"{n}\"{GT}")
        body.append(GT)
        for ln in body:
            if _BOM in ln:
                pre, post = ln.split(_BOM, 1)
                out += pre.encode("cp1252") + b"\xef\xbb\xbf" + post.encode("utf-8") + b"\n"
            else:
                out += ln.encode("cp1252") + b"\n"
        return bytes(out)

    def write(self, path):
        with open(path, "wb") as f:
            f.write(self.to_bytes())
