#!/usr/bin/env python3
"""
build_power_shuffler_integrated.py - the hand-drawn "Buck Boost Full Bridge - v3.qsch" with the firmware control
stack, as a set of hierarchical QSPICE sheets:

    python build_power_shuffler_integrated.py            -> ../Power_Shuffler_Integrated.qsch   (top sheet)
                                                            ../Shuffler_1.qsch  ../Shuffler_2.qsch
                                                            ../Controller.qsch  ../PWM_Modulator.qsch
    python build_power_shuffler_integrated.py --dry-run  -> only report how the drawn sheet is partitioned

The v3 sheet is read, never written.  Its records are copied verbatim (translated) into the sheets:
  * top sheet: PV string with bypass diodes and cable / copper inductors, shade ramps, load, reference string,
    the three blocks XS1 / XS2 / XC and the PARAMETERS / SIMULATION / MEASUREMENTS text
  * Shuffler_1 / Shuffler_2: the drawn converters (board capacitors, coupled inductor, half bridges with their
    HalfBridge_Driver blocks, gate R/C, parasitics, 0 V sense sources) plus the TMCS1126 hall-sensor models
  * Controller: the shuffler_ctrl_dll2.dll C-block, enable / reference / ramp sources, the .param test inputs,
    the open-loop duty override and two PWM_Modulator blocks
  * PWM_Modulator: the HRTIM-style comparators of one converter
Expressions use .func definitions on the top sheet (hall, duty, pwm_top, pwm_bot), which QSPICE resolves inside
sub-sheets.  Hierarchical names in the measurements use QSPICE's bullet: I(V4•XS1).
Verification: verify_power_shuffler.py (QUX netlist, comparison with the flat control sheet, short run, renders).
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "PCB_Baseline"))
from qsch_writer import Schematic, SymbolDef, sym_B, sym_V, sym_R, sym_C, p_rect, p_text, p_pin, LT, GT, MAGIC   # noqa: E402
from qsch_render import parse_schematic, xform                                                                 # noqa: E402
from integrate_control_v3 import (ctrl_sym, wire_line, PWM_RELABEL, PWM_WIRES, SW_WIRES, SW_LABELS,            # noqa: E402
                                  SW_COMPONENTS, BUS_SPLIT, CTRL_INS, CTRL_OUTS)

QDIR = os.path.normpath(os.path.join(HERE, ".."))
SRC = os.path.join(QDIR, "Buck Boost Full Bridge - v3.qsch")
TOP = "Power_Shuffler_Integrated"
ENC = "latin-1"            # byte-transparent for the drawn file (cp1252); generated text goes through qsch_writer
BUL = "•"             # QSPICE hierarchical separator in sheet text (cp1252 0x95 in the netlist)

# ----------------------------------------------------------------------------- ports of the blocks (= .subckt order)
SHUFFLER_PORTS = ["T", "M", "B", "PWM_AH", "PWM_AL", "PWM_BH", "PWM_BL", "HS_A", "HS_B"]
CONTROLLER_PORTS = ["PV1P", "PV2P", "PV3P", "HS_A1", "HS_B1", "HS_A2", "HS_B2",
                    "PWM_AH1", "PWM_AL1", "PWM_BH1", "PWM_BL1", "PWM_AH2", "PWM_AL2", "PWM_BH2", "PWM_BL2"]
MODULATOR_PORTS = ["RAMPA", "RAMPB", "DA", "DB", "PWM_AH", "PWM_AL", "PWM_BH", "PWM_BL"]
SHEETS = {"Shuffler_1": SHUFFLER_PORTS, "Shuffler_2": SHUFFLER_PORTS, "Controller": CONTROLLER_PORTS,
          "PWM_Modulator": MODULATOR_PORTS}

# ----------------------------------------------------------------------------- how the drawn sheet is partitioned
# bbox (x0, y0, x1, y1) in v3 coordinates, d = translation into the target sheet, cuts = boundary crossing -> net name
OUT_BUS = [(-3000, 4300, 15600, 4300), (15600, 4300, 16900, 4300), (16900, 4300, 16900, -600)]   # re-labelled instead
REGIONS = {
    "S1":   dict(bbox=(400, -3500, 16600, 4000), d=(-400, -100),
                 cuts={(400, 3500): "T", (400, 100): "M", (400, -2900): "B"}),
    "S2":   dict(bbox=(-20500, -7000, -5600, 1000), d=(20500, 3000),
                 cuts={(-5600, 100): "T", (-5600, -2900): "M", (-5600, -6100): "B"}),
    "STR":  dict(bbox=(-5600, -7000, 400, 4600), d=(0, 0),
                 cuts={(400, 3500): "T1", (400, 100): "PV2P", (400, -2900): "B1",
                       (-5600, 100): "T2", (-5600, -2900): "M2", (-5600, -6100): "B2"}),
    "SRC":  dict(bbox=(-9500, 5000, -6000, 7200), d=(-2500, -400), cuts={}),
    "REF":  dict(bbox=(9800, 7000, 13800, 13000), d=(-21000, -9400), cuts={}),
    "LOAD": dict(bbox=(16600, -1500, 17200, -500), d=(-18400, 6400), cuts={}),
}
EXPECTED_REFS = {"S1": 31, "S2": 30, "STR": 20, "SRC": 4, "REF": 9, "LOAD": 1}
HALL = {1: (("V4", 0.1), ("V7", -0.025)), 2: (("V5", 0.1), ("V6", -0.025))}     # (A sense, gain V/A), (B sense, gain)

# ----------------------------------------------------------------------------- directives of the top sheet
PARAM_ROWS = [
    (None, "* PWM"),
    (".param Tsw=5u", "PWM period: 5 u = 200 kHz (FSWP for the DLL follows 1/Tsw)"),
    (".param Tdead=200n", "dead time cut from both edges of every FET pulse"),
    (".param Vlogic=3.3", "logic level of the PWM into the gate drivers"),
    (None, "* controller enable and open-loop duties"),
    (".param TEN=1m", "controller enable time: open loop before it, closed loop after"),
    (".param D0A1=0.5 D0B1=0.5 D0A2=0.5 D0B2=0.5", "duties before TEN (leg A / B of converter 1 / 2)"),
    (None, "* reference steps"),
    (".param VSTEP1=0 VSTEP2=0 TSTEP=10m", "voltage-difference references (VM1-VM2, VM2-VM3) stepped at TSTEP"),
    (None, "* DLL test inputs"),
    (".param KSCALE=0.3", "gain scale; 0.3 = firmware boot default (kscale in 7_Pi/pod/params.yaml)"),
    (".param MSEL=0", "0 = M compiled into the DLL (params.h), 1 = the 100 kHz S9i M, 2 = ctrl_M2.txt"),
    (".param FILT=0 FC=2000", "0 = first-order IIR at FC Hz; 1..8 = moving average over that many control ticks"),
    (".param NOISE=0", "sensor noise: 1 = bench level"),
    (".param SAMP=1", "1 = firmware hall sampling (4 samples per PWM period), 0 = ideal average, 2 = old firmware"),
    (".param KBERR=1", "B-phase gain error factor"),
    (".param VM1SRC=0 VSTRP=0", "VM1 source (0 = INA239); VSTRP string-voltage option"),
    (None, "* kept from the drawn v3 sheet"),
    (".param VT=0.009", None),
]
FUNCS = [
    (".func hall(cur,gain) = 1.65+gain*cur", "TMCS1126 output: 1.65 V + gain * winding current"),
    (".func duty(en,cmd,dflt) = if(en>0.5,cmd,dflt)", "commanded duty: the DLL output when enabled, else the open-loop duty"),
    (".func pwm_top(rmp,dty) = if(time<1n,0,if(rmp<dty-Tdead/Tsw,Vlogic,0))", "top FET on while RAMP < D - Tdead/Tsw (all low at t = 0)"),
    (".func pwm_bot(rmp,dty) = if(time<1n,0,if(rmp>dty,if(rmp<1-Tdead/Tsw,Vlogic,0),0))", "bottom FET on while D < RAMP < 1 - Tdead/Tsw"),
]
SAVE = [".save V(Out) V(PV2P) V(PV3P) V(T1) V(B1) V(HS_A1) V(HS_B1) V(HS_A2) V(HS_B2) I(I1)",
        ".save V(PWM_AH1) V(PWM_BH1) V(PWM_AH2) V(PWM_BH2) " + " ".join(f"I({v}{BUL}XS{k})" for k, v in
                                                                      ((1, "V4"), (1, "V7"), (2, "V5"), (2, "V6"))),
        ".save " + " ".join(f"V({n}{BUL}XC)" for n in ("DA1", "DB1", "DA2", "DB2", "STRESS", "BETA", "RV1", "RV2"))]
SIM_ROWS = [
    (".tran 20m", "the 15 ms shade ramp of V1 / V2 starts inside the window"),
    (".culltime = 1n", None),
    (".plot I(I1)*V(Out)", None),
    (None, "* .save keeps the .qraw small: every node of the measurements, add what you want to plot"),
] + [(s, None) for s in SAVE] + [
    (None, "* functions used inside the sub-sheets (a top-level .func is visible there)"),
] + [(f, None) for f, _c in FUNCS] + [(None, "  " + c) for _f, c in FUNCS] + [
    (None, "* quick check: .tran 1.5m with TEN=0.3m VSTEP2=1 TSTEP=0.8m (meas window 1.3m-1.5m) solves in about 30 s"),
    (None, "* usual next move: .step param KSCALE list 0.3 1"),
]
W = "FROM 18m TO 20m"
MEAS = [
    f".meas tran vd1 AVG V(Out,PV2P)-V(PV2P,PV3P) {W}",
    f".meas tran vd2 AVG V(PV2P,PV3P)-V(PV3P) {W}",
    f".meas tran ic1 AVG I(V4{BUL}XS1)-I(V7{BUL}XS1) {W}",
    f".meas tran ic2 AVG I(V5{BUL}XS2)-I(V6{BUL}XS2) {W}",
    f".meas tran ish1 AVG I(V4{BUL}XS1)+I(V7{BUL}XS1) {W}",
    f".meas tran ish2 AVG I(V5{BUL}XS2)+I(V6{BUL}XS2) {W}",
    f".meas tran da1 AVG V(DA1{BUL}XC) {W}",
    f".meas tran db1 AVG V(DB1{BUL}XC) {W}",
    f".meas tran da2 AVG V(DA2{BUL}XC) {W}",
    f".meas tran db2 AVG V(DB2{BUL}XC) {W}",
    f".meas tran pout AVG I(I1)*V(Out) {W}",
    f".meas tran vout AVG V(Out) {W}",
    f".meas tran iout AVG I(I1) {W}",
    f".meas tran stressmax MAX V(STRESS{BUL}XC)",
    f".meas tran hsa1 AVG V(HS_A1) {W}",
    f".meas tran hsb1 AVG V(HS_B1) {W}",
    f".meas tran hsa2 AVG V(HS_A2) {W}",
    f".meas tran hsb2 AVG V(HS_B2) {W}",
    f".meas tran pwmah1 AVG V(PWM_AH1) {W}",
    f".meas tran pwmah2 AVG V(PWM_AH2) {W}",
]
MEAS_NOTES = ["vd1 / vd2: module voltage differences the controller nulls; ic / ish: circulating / shuffled",
              "inductor currents of each converter; da / db: commanded duties; pout / vout / iout: string power, voltage, current;",
              "stressmax: supervisor peak stress; hs*: hall outputs (1.65 V at zero current); pwmah*: top-FET PWM average"]


# ----------------------------------------------------------------------------- records of the drawn sheet
class Rec:
    def __init__(self, kind, lines, x, y, x2=None, y2=None, name=None, just=None, flag=None):
        self.kind, self.lines, self.x, self.y, self.x2, self.y2 = kind, lines, x, y, x2, y2
        self.name, self.just, self.flag = name, just, flag

    @property
    def pt(self):
        return (self.x, self.y)

    @property
    def seg(self):
        return (self.x, self.y, self.x2, self.y2)


COMP_RE = re.compile(rf"\s*{LT}component \((-?\d+),(-?\d+)\) (\d+) (\d+)")
WIRE_RE = re.compile(rf"\s*{LT}wire \((-?\d+),(-?\d+)\) \((-?\d+),(-?\d+)\) \"([^\"]*)\"{GT}")
NET_RE = re.compile(rf"\s*{LT}net \((-?\d+),(-?\d+)\) (\d+) (\d+) (\d+) \"([^\"]*)\"{GT}")
JUNC_RE = re.compile(rf"\s*{LT}junction \((-?\d+),(-?\d+)\){GT}")
TEXT_RE = re.compile(rf"\s*{LT}text \((-?\d+),(-?\d+)\) ")
POINT_RE = re.compile(r"\((-?\d+),(-?\d+)\)")


def read_v3():
    raw = open(SRC, "rb").read()
    assert raw[:4] == MAGIC, "not a QSPICE schematic"
    lines = raw[4:].decode(ENC).replace("\r\n", "\n").split("\n")
    while lines and lines[-1] == "":
        lines.pop()
    assert lines[0] == LT + "schematic" and lines[-1] == GT, (lines[0], lines[-1])
    return lines


def span_end(lines, i):
    """Index after the record that starts at line i (guillemets inside quotes do not count)."""
    depth = 0
    for j in range(i, len(lines)):
        s = re.sub(r'"[^"]*"', '""', lines[j])
        depth += s.count(LT) - s.count(GT)
        if depth == 0:
            return j + 1
    raise ValueError(f"unterminated record at line {i}")


def split_records(lines):
    recs, i = [], 1
    while i < len(lines) - 1:
        l = lines[i]
        m = COMP_RE.match(l)
        if m:
            j = span_end(lines, i)
            recs.append(Rec("component", lines[i:j], int(m.group(1)), int(m.group(2))))
            i = j
            continue
        if (m := WIRE_RE.match(l)):
            recs.append(Rec("wire", [l], *[int(v) for v in m.groups()[:4]], name=m.group(5)))
        elif (m := NET_RE.match(l)):
            recs.append(Rec("net", [l], int(m.group(1)), int(m.group(2)), name=m.group(6), just=int(m.group(4)), flag=int(m.group(5))))
        elif (m := JUNC_RE.match(l)):
            recs.append(Rec("junction", [l], int(m.group(1)), int(m.group(2))))
        elif (m := TEXT_RE.match(l)):
            recs.append(Rec("text", [l], int(m.group(1)), int(m.group(2))))
        else:
            raise ValueError(f"unexpected top-level line {i}: {l[:80]}")
        i += 1
    return recs


def geometry():
    """(anchor) -> (ref, [absolute pin points]) of every drawn component."""
    comps, _w, _n, _j = parse_schematic(SRC)
    geo = {}
    for c in comps:
        key = (int(c["x"]), int(c["y"]))
        assert key not in geo, f"two components at {key}"
        geo[key] = (c["ref"], [(int(round(x)), int(round(y))) for x, y in (xform(p["x"], p["y"], c) for p in c["sym"]["pins"])])
    return geo


def shift_points(line, dx, dy, count):
    return POINT_RE.sub(lambda m: f"({int(m.group(1)) + dx},{int(m.group(2)) + dy})", line, count=count)


def translate(rec, dx, dy):
    if rec.kind == "component":
        return [shift_points(rec.lines[0], dx, dy, 1)] + rec.lines[1:]
    if rec.kind == "wire":
        return [shift_points(rec.lines[0], dx, dy, 2)]
    return [shift_points(rec.lines[0], dx, dy, 1)]


def net_line(x, y, just, port, name):
    return f"  {LT}net ({x},{y}) 1 {just} {port} \"{name}\"{GT}"


def inside(bbox, x, y):
    x0, y0, x1, y1 = bbox
    return x0 <= x <= x1 and y0 <= y <= y1


def extract(recs, geo, region, port, relabel=(), wire_names=(), splits=(), used=None):
    """Copy the records of one drawn region, translated. Wires leaving the bbox are cut on its edge and end on a
    net label from region['cuts'] (port = 1 makes it a sub-sheet port). relabel: {(x,y): (newname, port)} for
    drawn labels; wire_names: {(x1,y1,x2,y2): newname} cosmetic cache renames; splits: {(x1,y1,x2,y2): [lines]}
    replacement records (already in target coordinates)."""
    bbox, (dx, dy), cuts = region["bbox"], region["d"], region["cuts"]
    relabel, wire_names, splits = dict(relabel), dict(wire_names), dict(splits)
    out, refs, hits = [], [], set()
    pins_abs = []
    for k, r in enumerate(recs):
        if r.kind == "component":
            if not inside(bbox, *r.pt):
                continue
            ref, pins = geo[r.pt]
            for (px, py) in pins:
                assert inside(bbox, px, py), f"{ref}: pin ({px},{py}) outside {bbox}"
            pins_abs += [(px + dx, py + dy) for (px, py) in pins]
            out += translate(r, dx, dy)
            refs.append(ref)
        elif r.kind == "wire":
            if r.seg in OUT_BUS or r.seg in SW_WIRES:
                continue
            a, b = inside(bbox, r.x, r.y), inside(bbox, r.x2, r.y2)
            if not (a or b):
                continue
            if a and b:
                if r.seg in splits:
                    out += splits[r.seg]
                elif r.seg in wire_names:
                    out.append(wire_line(r.x + dx, r.y + dy, r.x2 + dx, r.y2 + dy, wire_names[r.seg]))
                else:
                    out += translate(r, dx, dy)
            else:
                (ix, iy), (ox, oy) = ((r.x, r.y), (r.x2, r.y2)) if a else ((r.x2, r.y2), (r.x, r.y))
                assert ix == ox or iy == oy, f"diagonal wire leaves {bbox}: {r.seg}"
                x0, y0, x1, y1 = bbox
                if iy == oy:
                    px, py = (x1 if ox > x1 else x0), iy
                    just = 7 if ox > x1 else 11
                else:
                    px, py = ix, (y1 if oy > y1 else y0)
                    just = 14 if oy > y1 else 13
                if (px, py) not in cuts:
                    raise KeyError(f"wire {r.seg} leaves {bbox} at ({px},{py}) with no cut name")
                name = cuts[(px, py)]
                out.append(wire_line(ix + dx, iy + dy, px + dx, py + dy, name))
                out.append(net_line(px + dx, py + dy, just, port, name))
                hits.add((px, py))
        elif r.kind == "net":
            if not inside(bbox, *r.pt):
                continue
            if r.pt in relabel:
                new, pflag = relabel[r.pt]
                out.append(net_line(r.x + dx, r.y + dy, r.just, pflag, new))
            else:
                out += translate(r, dx, dy)
        elif r.kind == "junction":
            if inside(bbox, *r.pt):
                out += translate(r, dx, dy)
        else:
            continue                                  # sheet texts are regenerated
        if used is not None:
            used.add(k)
    assert hits == set(cuts), f"cuts hit {sorted(hits)} but expected {sorted(cuts)}"
    check_junctions(out, pins_abs, bbox)
    return out, refs


def check_junctions(lines, pins, bbox):
    """Every copied junction must still join three things (wire ends / pins / a wire interior)."""
    from collections import Counter
    ends, wires = Counter(), []
    for l in lines:
        if (m := WIRE_RE.match(l)):
            x1, y1, x2, y2 = [int(v) for v in m.groups()[:4]]
            wires.append((x1, y1, x2, y2))
            ends[(x1, y1)] += 1
            ends[(x2, y2)] += 1
    pc = Counter(pins)
    for l in lines:
        if (m := JUNC_RE.match(l)):
            x, y = int(m.group(1)), int(m.group(2))
            n = ends[(x, y)] + pc[(x, y)]
            on_interior = any((x1 == x2 == x and min(y1, y2) < y < max(y1, y2)) or (y1 == y2 == y and min(x1, x2) < x < max(x1, x2))
                              for (x1, y1, x2, y2) in wires)
            assert n >= 3 or (n >= 1 and on_interior), f"junction ({x},{y}) in {bbox} joins only {n} ends"


# ----------------------------------------------------------------------------- symbols for the hierarchical blocks
class HierBlock(SymbolDef):
    """A hierarchical-sheet block exactly as QSPICE writes one: nameless symbol, empty type, value = sheet name."""

    def __init__(self, sheet, w, h, pins):
        super().__init__("", "", "", [p_rect(-w // 2, h // 2, w // 2, -h // 2, "box")], pins, text_just=0)
        self.sheet = sheet

    def lines(self, ref, value, extra=(), rot=0, label_side="above"):
        out = [f"{LT}symbol", f"  {LT}type: {GT}", f"  {LT}shorted pins: false{GT}"]
        out += ["  " + p for p in self.prims]
        out.append("  " + p_text(0, 120, ref, 15))
        out.append("  " + p_text(0, -120, value, 15))
        for (n, x, y, dx, dy, just) in self.pins:
            out.append("  " + p_pin(x, y, n, dx, dy, just))
        out.append(GT)
        return out


def hier_sym(sheet, w, h, order, left=(), right=(), top=(), bottom=(), pitch=400):
    """Block symbol; left/right/top/bottom name the pins on each edge (centred, pitch apart), order = port order."""
    hw, hh = w // 2, h // 2
    pos = {}
    for names, mk in ((left, lambda i, n: (n, -hw, (len(left) - 1) * pitch // 2 - i * pitch, 60, -40, 13)),
                      (right, lambda i, n: (n, hw, (len(right) - 1) * pitch // 2 - i * pitch, -60, -40, 14)),
                      (top, lambda i, n: (n, -(len(top) - 1) * pitch // 2 + i * pitch, hh, 0, -90, 7)),
                      (bottom, lambda i, n: (n, -(len(bottom) - 1) * pitch // 2 + i * pitch, -hh, 0, 60, 11))):
        for i, n in enumerate(names):
            pos[n] = mk(i, n)
    assert set(pos) == set(order), (sorted(pos), order)
    return HierBlock(sheet, w, h, [pos[n] for n in order])


def sym_shuffler(k):
    return hier_sym(f"Shuffler_{k}", 2400, 2800, SHUFFLER_PORTS, top=["T"], bottom=["B"],
                    left=["M", "PWM_AH", "PWM_AL", "PWM_BH", "PWM_BL"], right=["HS_A", "HS_B"])


def sym_controller():
    return hier_sym("Controller", 3000, 3800, CONTROLLER_PORTS, left=CONTROLLER_PORTS[:7], right=CONTROLLER_PORTS[7:])


def sym_modulator():
    return hier_sym("PWM_Modulator", 2400, 2000, MODULATOR_PORTS, left=MODULATOR_PORTS[:4], right=MODULATOR_PORTS[4:])


def block(s, sym, x, y, ref, nets):
    """Place a block and hang a 600-unit stub with a net label on every pin. nets: pin name -> net label."""
    p = s.add(sym, x, y, ref, sym.sheet)
    for (n, px, py, _dx, _dy, _j) in sym.pins:
        side = "left" if px < 0 else "right" if px > 0 else "up" if py > 0 else "down"
        s.stub(p.pin[n], nets[n], side, 600 if side in ("left", "right") else 400)
    return p


# ----------------------------------------------------------------------------- generated pieces
def notes(s, x, y, title, lines, size=1.6):
    s.comment(x, y, title, size=size)
    for i, t in enumerate(lines):
        s.comment(x, y - 400 - 200 * i, t)


def titled_column(s, x, y0, title, rows, cx=4000, pitch=150):
    """Title then rows of (directive, comment): the comment beside the directive at x+cx, or alone at x."""
    s.comment(x, y0 + 250, title, size=1.4)
    for i, (d, c) in enumerate(rows):
        y = y0 - pitch * i
        if d:
            s.directive(x, y, d)
            if c:
                s.comment(x + cx, y, c)
        elif c:
            s.comment(x, y, c)


def hall_sensor(s, x, y, vsense, gain, port):
    """TMCS1126 model: B-source 1.65 V + gain * I(sense source), 1k + 318.3p output pole, port label at the end."""
    b = s.add(sym_B(), x, y, "Bhs" + port[-1], f"V=hall(I({vsense}),{gain:g})")
    s.stub(b.pin["-"], "GND", "down", 200)
    r = s.add(sym_R(), x + 600, y + 500, "Rhs" + port[-1], "1k", rot=2)
    c = s.add(sym_C(), x + 1200, y, "Chs" + port[-1], "318.3p")
    s.stub(c.pin["2"], "GND", "down", 200)
    s.wire([b.pin["+"], (x, y + 500), r.pin["1"]], port + "R")
    s.wire([r.pin["2"], (x + 1200, y + 500), c.pin["1"]], port)
    s.wire([(x + 1200, y + 500), (x + 1600, y + 500)], port)
    s.label(x + 1600, y + 500, port, 7)


def portify(line, ports):
    """Turn generated net labels of the given names into sub-sheet ports (4th field 0 -> 1)."""
    if not line.startswith(b"  " + LT.encode("cp1252") + b"net "):
        return line
    for n in ports:
        tail = b' 0 "' + n.encode("cp1252") + b'"' + GT.encode("cp1252")
        if line.endswith(tail):
            return line[:-len(tail)] + b' 1 "' + n.encode("cp1252") + b'"' + GT.encode("cp1252")
    return line


def emit(name, copied, s, ports=()):
    body = s.to_bytes()[len(MAGIC):].split(b"\n")
    assert body[0] == LT.encode("cp1252") + b"schematic" and body[-1] == b"" and body[-2] == GT.encode("cp1252")
    gen = [portify(l, ports) for l in body[1:-2]]
    data = b"\n".join([LT.encode("cp1252") + b"schematic"] + [l.encode(ENC) for l in copied] + gen + [GT.encode("cp1252"), b""])
    path = os.path.join(QDIR, name + ".qsch")
    open(path, "wb").write(MAGIC + data)
    return path


# ----------------------------------------------------------------------------- the sheets
def build_shuffler(k, recs, geo, used):
    region = REGIONS[f"S{k}"]
    relabel = {pt: (new[:-1], 1) for pt, (old, new) in PWM_RELABEL.items() if new.endswith(str(k))}
    wnames = {seg: new[:-1] for seg, new in PWM_WIRES.items() if new.endswith(str(k))}
    copied, refs = extract(recs, geo, region, port=1, relabel=relabel, wire_names=wnames, used=used)
    s = Schematic()
    (va, ga), (vb, gb) = HALL[k]
    if k == 1:
        title = "SHUFFLER 1 - converter between PV1+ (T) and PV3+ (B) with the midpoint on PV2+ (M): the hand-drawn v3 power stage"
        legs = "Leg A = M3 / M4 (driver X6, PWM_AH / PWM_AL), leg B = M1 / M2 (driver X7, PWM_BH / PWM_BL); X4 = ERUC23 inverse-coupled inductor."
        parts = "Board capacitors C1 / C3 (130 uF) and C5 (225 nF); V13 = 0 V midpoint sense; V4 (A) and V7 (B) = 0 V sources in the windings, positive into the midpoint."
        pos = (0, 5200)
        hx, hy = 3000, -4600
    else:
        title = "SHUFFLER 2 - converter between PV2+ (T) and GND (B) with the midpoint on PV3+ (M): the hand-drawn v3 power stage (mirror image of converter 1)"
        legs = "Leg A = M5 / M6 (driver X8, PWM_AH / PWM_AL), leg B = M7 / M8 (driver X9, PWM_BH / PWM_BL); X5 = ERUC23 inverse-coupled inductor."
        parts = "Board capacitors C2 / C4 (130 uF) and C6 (225 nF); V5 (A) and V6 (B) = 0 V sources in the windings, positive into the midpoint."
        pos = (0, 5200)
        hx, hy = 3000, -4700
    notes(s, pos[0], pos[1], title, [
        legs, parts,
        "Ports: T / M / B = the converter rails (cable and copper inductances are on the top sheet); PWM_* = 3.3 V logic from the Controller block;",
        "HS_A / HS_B = TMCS1126 hall-sensor outputs to the Controller (1.65 V + 100 mV/A on A, 1.65 V - 25 mV/A on B: reversed as mounted on the board).",
        f"Measure the winding currents from the top sheet as I({va}{BUL}XS{k}) and I({vb}{BUL}XS{k}); their difference is the circulating current, their sum the shuffled current.",
    ])
    s.comment(hx, hy + 900, "TMCS1126 HALL SENSORS - on the board at the inductor; 1k + 318.3p = the 500 kHz output pole", size=1.2)
    hall_sensor(s, hx, hy, va, ga, "HS_A")
    hall_sensor(s, hx + 3000, hy, vb, gb, "HS_B")
    return emit(f"Shuffler_{k}", copied, s, ports=SHUFFLER_PORTS), refs


def build_modulator():
    s = Schematic()
    notes(s, 0, 4200, "PWM MODULATOR - HRTIM-style comparators of one converter", [
        "Top FET on while RAMP < D - Tdead/Tsw, bottom FET on while D < RAMP < 1 - Tdead/Tsw: Tdead is cut from both edges of every pulse.",
        "RAMPA / RAMPB are the 0..1 sawtooth ramps of leg A and leg B (leg B half a period later), DA / DB the commanded duties of the legs.",
        "All outputs are low for t < 1 ns so the operating point is found with the FETs off (pwm_top / pwm_bot are .func on the top sheet).",
    ], size=1.4)
    for i, n in enumerate(MODULATOR_PORTS[:4]):
        y = 2400 - 800 * i
        s.wire([(0, y), (600, y)], n)
        s.label(0, y, n, 11)
    for i, (ref, fn, ramp, d, out) in enumerate((("BpTA", "pwm_top", "RAMPA", "DA", "PWM_AH"), ("BpBA", "pwm_bot", "RAMPA", "DA", "PWM_AL"),
                                                 ("BpTB", "pwm_top", "RAMPB", "DB", "PWM_BH"), ("BpBB", "pwm_bot", "RAMPB", "DB", "PWM_BL"))):
        y = 2400 - 1200 * i
        b = s.add(sym_B(), 3000, y, ref, f"V={fn}(V({ramp}),V({d}))")
        s.stub(b.pin["-"], "GND", "down", 200)
        s.wire([b.pin["+"], (3000, y + 400), (6000, y + 400)], out)
        s.label(6000, y + 400, out, 7)
    return emit("PWM_Modulator", [], s, ports=MODULATOR_PORTS)


def build_controller():
    s = Schematic()
    notes(s, 0, 6400, "CONTROLLER - shuffler_ctrl_dll2.dll: the firmware control stack (6_RTOS/ctrl_core) as a QSPICE C-block", [
        "The DLL models the INA239 / hall sampling and quantisation, the 10 kHz control tick and the gain matrix M from params.h (MSEL = 0),",
        "the 100 kHz S9i M (MSEL = 1) or ctrl_M2.txt (MSEL = 2). shuffler_ctrl_dll2.dll and ctrl_M2.txt must sit next to the top sheet.",
        "Open loop until TEN (CTRL_EN low: the duties D0A1 .. D0B2), closed loop after. Every test input of the DLL is a .param on the top sheet.",
        "Inputs: PV1P / PV2P / PV3P = the string nodes the INA239s see, HS_* = hall outputs of the shufflers. Outputs: one PWM pair per leg.",
        "Signal flow left to right: sources -> DLL -> duty override (duty() .func) -> PWM_Modulator XP1 (converter 1) and XP2 (converter 2).",
    ])
    # band 1: enable, references, ramps
    s.comment(0, 4600, "ENABLE, REFERENCE STEPS AND PWM RAMPS", size=1.2)
    for i, (ref, val, net) in enumerate((("Ven", "PWL(0 0 {TEN} 0 {TEN+1u} 1)", "CTRL_EN"),
                                         ("Vref1", "PWL(0 0 {TSTEP} 0 {TSTEP+1u} {VSTEP1})", "VREF1"),
                                         ("Vref2", "PWL(0 0 {TSTEP} 0 {TSTEP+1u} {VSTEP2})", "VREF2"),
                                         ("Vrampa", "PULSE(0 1 0 {Tsw-2n} 1n 1n {Tsw})", "RAMPA"),
                                         ("Vrampb", "PULSE(0 1 {Tsw/2} {Tsw-2n} 1n 1n {Tsw})", "RAMPB"))):
        p = s.add(sym_V(), 2800 * i, 3800, ref, val)
        s.stub(p.pin["+"], net, "up", 200)
        s.stub(p.pin["-"], "GND", "down", 200)
    # band 2: test inputs from .param
    s.comment(0, 2400, "DLL TEST INPUTS - each a .param of the top sheet", size=1.2)
    for i, pin in enumerate(CTRL_INS[10:]):
        p = s.add(sym_B(), 1000 * i, 1600, "Bt" + pin, "V=" + ("1/Tsw" if pin == "FSWP" else pin))
        s.stub(p.pin["+"], pin, "up", 200)
        s.stub(p.pin["-"], "GND", "down", 200)
    # the DLL
    xd = 14500
    p = s.add(ctrl_sym(), xd, 0, "Xc", "shuffler_ctrl_dll2", extra=("Rout=1 Cout=1p",))
    ports_in = dict(zip(CTRL_INS[:7], CONTROLLER_PORTS[:7]))
    for n in CTRL_INS:
        s.stub(p.pin[n], ports_in.get(n, n), "left", 600)
    for n in CTRL_OUTS:
        s.stub(p.pin[n], n, "right", 600)
    s.stub(p.pin["GND"], "GND", "down", 400)
    s.comment(xd - 1400, 2800, "shuffler_ctrl_dll2.dll - INA239 / hall sampling, 10 kHz control tick, M from params.h", size=1.2)
    # duty override
    s.comment(17500, 3000, "COMMANDED DUTIES - DLL output when CTRL_EN, else D0*", size=1.2)
    for i, (dn, d0) in enumerate((("DA1", "D0A1"), ("DB1", "D0B1"), ("DA2", "D0A2"), ("DB2", "D0B2"))):
        b = s.add(sym_B(), 18500, 2100 - 1400 * i, "Bd" + dn, f"V=duty(V(CTRL_EN),V({dn}),{d0})")
        s.stub(b.pin["+"], dn + "C", "up", 200)
        s.stub(b.pin["-"], "GND", "down", 200)
    # the two modulators
    s.comment(23800, 3000, "PWM MODULATORS - one per converter (hierarchical sheet PWM_Modulator)", size=1.2)
    for k in (1, 2):
        nets = {"RAMPA": "RAMPA", "RAMPB": "RAMPB", "DA": f"DA{k}C", "DB": f"DB{k}C"}
        nets.update({n: n + str(k) for n in MODULATOR_PORTS[4:]})
        block(s, sym_modulator(), 25000, 1500 if k == 1 else -1500, f"XP{k}", nets)
    return emit("Controller", [], s, ports=CONTROLLER_PORTS)


def build_top(recs, geo, used):
    copied, refs = [], {}
    splits = {}
    for new, ((x1, y1, x2, y2), (sx, sy), (lx, ly), just) in BUS_SPLIT.items():
        splits[(x1, y1, x2, y2)] = [wire_line(x1, y1, sx, sy, new), wire_line(sx, sy, x2, y2, new), wire_line(sx, sy, lx, ly, new),
                                    net_line(lx, ly, just, 0, new), f"  {LT}junction ({sx},{sy}){GT}"]
    for name in ("STR", "SRC", "REF", "LOAD"):
        c, r = extract(recs, geo, REGIONS[name], port=0, splits=splits if name == "STR" else (), used=used)
        copied += c
        refs[name] = r
    # the Out net: label on the string top and a short wire from the load
    copied.append(net_line(-3000, 4300, 14, 0, "Out"))
    copied.append(wire_line(-1500, 5800, -1500, 6200, "Out"))
    copied.append(net_line(-1500, 6200, 14, 0, "Out"))
    s = Schematic()
    notes(s, -12000, 9600, "POWER SHUFFLER - the hand-drawn v3 string and converters with the firmware control stack, as hierarchical sheets", [
        "Blocks: XS1 / XS2 = Shuffler_1.qsch / Shuffler_2.qsch (the drawn converters with their hall sensors), XC = Controller.qsch (the DLL, its sources,",
        "and two PWM_Modulator.qsch comparator sheets). Right-click a block and open its schematic to look inside; every sheet carries its own notes.",
        "Files that must sit next to this sheet: the four sub-sheets, HalfBridge_Driver.qsch, shuffler_ctrl_dll2.dll, ctrl_M2.txt (MSEL = 2); MyLibrary.lib via the library path.",
        "Nodes: Out = PV1+ at the load, PV2P / PV3P = the INA239 string nodes, T1 / B1 and T2 / M2 / B2 = the converter rails behind the cable and copper inductors L23-L28.",
        "Inside a block, name a current or node with QSPICE's bullet: I(V4" + BUL + "XS1), V(DA1" + BUL + "XC). The PARAMETERS column is the one place to edit.",
        "Generated by Claude's outputs/build_power_shuffler_integrated.py from Buck Boost Full Bridge - v3.qsch (which it never writes); hand edits and the generator do not mix.",
    ], size=2)
    s.comment(-12000, 7100, "SHADE RAMPS V1 / V2 (Vtest, Vtest2: irradiance of module 2 in both strings), Vref and Vcc as drawn", size=1.2)
    s.comment(-11200, 3950, "REFERENCE STRING - the same modules and load, never gets a converter (comparison only)", size=1.2)
    s.comment(-5600, 4900, "PV STRING - X1-X3 Aiko modules, L1-L6 lead inductors, D4-D6 bypass diodes, L23-L28 cable / copper to the converters", size=1.2)
    s.comment(-2500, 6700, "LOAD I1 on Out (13 A ramp, VSAT 137.4 V)", size=1.2)
    # blocks
    s.comment(3300, 4100, "SHUFFLER 1 - converter 1 on PV1+ / PV2+ / PV3+ (Shuffler_1.qsch)", size=1.2)
    block(s, sym_shuffler(1), 4500, 1500, "XS1", {"T": "T1", "M": "PV2P", "B": "B1", "PWM_AH": "PWM_AH1", "PWM_AL": "PWM_AL1",
                                                   "PWM_BH": "PWM_BH1", "PWM_BL": "PWM_BL1", "HS_A": "HS_A1", "HS_B": "HS_B1"})
    s.comment(3300, -1900, "SHUFFLER 2 - converter 2 on PV2+ / PV3+ / GND (Shuffler_2.qsch)", size=1.2)
    block(s, sym_shuffler(2), 4500, -4500, "XS2", {"T": "T2", "M": "M2", "B": "B2", "PWM_AH": "PWM_AH2", "PWM_AL": "PWM_AL2",
                                                    "PWM_BH": "PWM_BH2", "PWM_BL": "PWM_BL2", "HS_A": "HS_A2", "HS_B": "HS_B2"})
    s.comment(10000, 1100, "CONTROLLER - firmware control stack, DLL + PWM modulators (Controller.qsch)", size=1.2)
    nets = {n: n for n in CONTROLLER_PORTS}
    nets["PV1P"] = "Out"
    block(s, sym_controller(), 11500, -1500, "XC", nets)
    # text columns
    titled_column(s, -12000, -8000, "PARAMETERS - edit values here (units: m = milli, u = micro, n = nano, p = pico)", PARAM_ROWS, cx=4000)
    titled_column(s, -2500, -8000, "SIMULATION", SIM_ROWS, cx=2200)
    titled_column(s, 7500, -8000, "MEASUREMENTS - settled window 18-20 ms of the 20 ms run", [(m, None) for m in MEAS] + [(None, "* " + n) for n in MEAS_NOTES])
    return emit(TOP, copied, s), refs


# ----------------------------------------------------------------------------- main
def main():
    dry = "--dry-run" in sys.argv
    lines = read_v3()
    recs = split_records(lines)
    geo = geometry()
    all_refs = sorted(ref for ref, _p in geo.values())
    used = set()
    partition = {}
    if dry:
        for name, region in REGIONS.items():
            port = 1 if name in ("S1", "S2") else 0
            _c, refs = extract(recs, geo, region, port=port, used=used,
                               splits={seg: [] for seg in [v[0] for v in BUS_SPLIT.values()]} if name == "STR" else ())
            partition[name] = refs
    else:
        for k in (1, 2):
            _p, refs = build_shuffler(k, recs, geo, used)
            partition[f"S{k}"] = refs
        build_modulator()
        build_controller()
        _p, refs = build_top(recs, geo, used)
        partition.update(refs)
    # the partition must cover every drawn component except SW1 / SW2
    for name, refs in partition.items():
        print(f"{name:5s} {len(refs):3d} refs: {' '.join(refs)}")
        assert len(refs) == EXPECTED_REFS[name], (name, len(refs), EXPECTED_REFS[name])
    flat = sum(partition.values(), [])
    assert len(flat) == len(set(flat)), "a component landed in two regions"
    left = sorted(set(all_refs) - set(flat))
    assert left == ["SW1", "SW2"], f"components in no region: {left}"
    unused = [r for k, r in enumerate(recs) if k not in used]
    others = [r for r in unused if r.kind != "text"]
    expect = set(OUT_BUS) | set(SW_WIRES)
    for r in others:
        ok = ((r.kind == "wire" and r.seg in expect) or (r.kind == "net" and (r.pt in SW_LABELS or r.pt == (15600, 4300)))
              or (r.kind == "component" and r.pt in SW_COMPONENTS))
        assert ok, f"drawn record dropped unexpectedly: {r.kind} {r.lines[0][:80]}"
    print(f"{len(unused) - len(others)} sheet texts regenerated; {len(others)} drawn records dropped on purpose (SW1/SW2 and the Out bus)")
    if not dry:
        print("wrote", TOP + ".qsch", "and", ", ".join(f"{n}.qsch" for n in SHEETS))


if __name__ == "__main__":
    main()
