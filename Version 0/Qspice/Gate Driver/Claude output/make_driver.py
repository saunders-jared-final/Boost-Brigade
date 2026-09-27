# -*- coding: utf-8 -*-
"""
make_driver.py - writes the half-bridge gate driver for Qspice

  HalfBridge_Driver.qsch            the driver itself, fully drawn. It is a Qspice hierarchical sheet:
                                    its six port labels are flagged "This is a Port"
  HalfBridge_Driver_Testbench.qsch  a top sheet with one hierarchical block that points at the sheet above,
                                    two PWM sources and one half bridge. Runs as it is.

Qspice hierarchy in short (Help > Schematic Hierarchy): a block symbol with an empty Symbol Type stands for the
schematic file of the same name in the same folder; its pins are matched to the port labels by NAME.

Run:  python make_driver.py

Drawing rules used here
  * native Qspice symbols (copied from Driver.qsch and "Buck Boost Full Bridge - v3.qsch")
  * the signal path is wired end to end; net labels only on the block ports and on supply pins
  * spacing for Qspice text, which is about 100 sheet units per character and 140 high
All values are literal on the sheet (no .param indirection) so what you read is what is simulated.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
LQ, RQ = "«", "»"          # the Qspice record brackets

# ------------------------------------------------------------------ values (edit here, then re-run)
VDRV = "12"            # driver supply, V (ideal, floating on the FET source)
RON = "10"             # OUTH to gate resistor, ohm
ROFF = "4.7"           # OUTL to gate resistor, ohm
RSRC = "1.5"           # driver pull-up resistance  (12 V / 6.5 A peak), ohm
RSNK = "1"             # driver pull-down resistance, ohm
TPD = "70n"            # propagation delay
TEDGE = "10n"          # output rise / fall time
VTH = "1.5"            # input threshold on (IN+ - IN-), V
VHYS = "0.2"           # input hysteresis, V
FET_MODEL = ('.model STD45N10F7 VDMOS Rd=10.9m Rg=1.5 Vto=3.71 Kp=10.9 lambda=33.3m RonX=4.04 eta=75m '
             'Vtotc=-2m Is=46.5n N=1.58988 Rb=1.94m Eg=1.11 XTI=4.08312 trb1=4.33m Cgs=1.84n Cgdmin=64.7p '
             'Cgdmax=325p Cjo=1.2n tt=1.49n Tnom=25 mfg="ST Microelectronics" Vds=100 Ids=45 Ron=14.5m Qg=25n')

# ------------------------------------------------------------------ native symbol drawings
def line(x1, y1, x2, y2, tail="0 0 0x1000000 -1 -1"):
    return f"{LQ}line ({x1},{y1}) ({x2},{y2}) {tail}{RQ}"

PRIM = {
    "SCHMITT": [line(400, -100, 331, -100), line(-200, -300, -200, 300), line(-200, 300, 400, 0),
                line(-200, -300, 400, 0), line(400, 100, 203, 100), line(-25, 100, -25, -100),
                line(25, 100, 25, -100), line(75, 100, -25, 100), line(25, -100, -75, -100),
                line(-100, 200, -150, 200, "0 0 0x1000000 -1 4"), line(-100, -200, -150, -200, "0 0 0x1000000 -1 5"),
                line(-125, 175, -125, 225, "0 0 0x1000000 -1 4"),
                f"{LQ}ellipse (251,-60) (331,-140) 0 0 0 0x1000000 0x1000000 -1 -1{RQ}"],
    "V": [line(0, -130, 0, -200), line(0, 200, 0, 130),
          f"{LQ}rect (-25,77) (25,73) 0 0 0 0x1000000 0x3000000 -1 0 -1{RQ}",
          f"{LQ}rect (-2,50) (2,100) 0 0 0 0x1000000 0x3000000 -1 0 -1{RQ}",
          f"{LQ}rect (-25,-73) (25,-77) 0 0 0 0x1000000 0x3000000 -1 0 -1{RQ}",
          f"{LQ}ellipse (-130,130) (130,-130) 0 0 0 0x1000000 0x1000000 -1 -1{RQ}"],
    "Vpulse": [line(0, -130, 0, -200), line(0, 200, 0, 130), line(-70, -30, -50, -30), line(-50, -30, -40, 30),
               line(-40, 30, 0, 30), line(0, 30, 10, -30), line(10, -30, 70, -30),
               f"{LQ}rect (-25,77) (25,73) 0 0 0 0x1000000 0x3000000 -1 0 -1{RQ}",
               f"{LQ}rect (-2,50) (2,100) 0 0 0 0x1000000 0x3000000 -1 0 -1{RQ}",
               f"{LQ}rect (-25,-73) (25,-77) 0 0 0 0x1000000 0x3000000 -1 0 -1{RQ}",
               f"{LQ}ellipse (-130,130) (130,-130) 0 0 0 0x1000000 0x1000000 -1 -1{RQ}"],
    "R": [line(0, -200, 0, -150), line(0, 150, 0, 200),
          f"{LQ}rect (50,-150) (-50,150) 0 0 0 0x1000000 0x2000000 -1 0 -1{RQ}"],
    "I": [line(0, 200, 0, 150), line(0, -150, 0, -200),
          f"{LQ}rect (-25,102) (25,98) 0 0 0 0x1000000 0x3000000 -1 0 -1{RQ}",
          f"{LQ}rect (-2,75) (2,125) 0 0 0 0x1000000 0x3000000 -1 0 -1{RQ}",
          f"{LQ}rect (-25,-98) (25,-102) 0 0 0 0x1000000 0x3000000 -1 0 -1{RQ}",
          f"{LQ}ellipse (-100,-150) (100,50) 0 0 0 0x1000000 0x1000000 -1 -1{RQ}",
          f"{LQ}ellipse (-100,-50) (100,150) 0 0 0 0x1000000 0x1000000 -1 -1{RQ}"],
    "MN": [line(100, 200, 100, 150), line(100, -150, 100, -200), line(-100, 150, -100, -150),
           line(-100, 0, -200, 0), line(100, -150, -50, -150), line(100, 150, -50, 150), line(-50, 150, -50, -150),
           f"{LQ}triangle (70,-150) (-25,-125) (-25,-175) 0 0 0x1000000 0x3000000 -1 -1{RQ}"],
}
PINS = {   # name -> (x, y) in symbol space, in netlist order
    "SCHMITT": [("Vdd", 0, 200), ("Vss", 0, -200), ("Q", 400, 100), ("¬Q", 400, -100),
                ("b0", -200, 200), ("b1", -200, -200), ("EN", -200, 0)],
    "V": [("+", 0, 200), ("-", 0, -200)],
    "Vpulse": [("+", 0, 200), ("-", 0, -200)],
    "R": [("+", 0, -200), ("-", 0, 200)],
    "I": [("-", 0, -200), ("+", 0, 200)],
    "MN": [("D", 100, 200), ("G", -200, 0), ("S", 100, -200)],
}
DESC = {"SCHMITT": "SCHMITT trigger w/ complementary outputs", "V": "Independent Voltage Source",
        "Vpulse": "Independent Voltage Source", "R": "Resistor(UK Style Symbol)", "I": "Current Source",
        "MN": "Autogenerated symbol"}
TYPE = {"SCHMITT": "¥", "V": "V", "Vpulse": "V", "R": "R", "I": "I", "MN": "MN"}


def rot_pt(x, y, rot):
    for _ in range((rot % 8) // 2):
        x, y = -y, x
    if rot >= 8:
        x = -x
    return x, y


def text(x, y, s, just=7, flag=0, size=1):
    return f'{LQ}text ({x},{y}) {size} {just} {flag} 0x1000000 -1 -1 "{s}"{RQ}'


class Sheet:
    def __init__(self):
        self.comps, self.wires, self.labels, self.notes, self.pinpts = [], [], [], [], []

    # ---- components
    def place(self, kind, x, y, texts, rot=0, lib=None, symname=None):
        """texts: ready-made text records in symbol space. Returns {pin name: (x, y)} in sheet space."""
        out = [f"  {LQ}component ({x},{y}) {rot} 0", f"    {LQ}symbol {kind if symname is None else symname}",
               f"      {LQ}type: {TYPE[kind]}{RQ}", f"      {LQ}description: {DESC[kind]}{RQ}"]
        if lib:
            out.append(f"      {LQ}library file: {lib}{RQ}")
        out.append(f"      {LQ}shorted pins: false{RQ}")
        out += ["      " + p for p in PRIM[kind]]
        out += ["      " + t for t in texts]
        pins = {}
        for n, px, py in PINS[kind]:
            if kind == "SCHMITT" and n == "EN":
                out.append(f'      {LQ}pin ({px},{py}) (10,0) 0.681 7 0 0x1000000 -1 "{n}"{RQ}')
            elif kind == "SCHMITT":
                out.append(f'      {LQ}pin ({px},{py}) (0,0) 1 0 0 0x1000000 -1 "{n}"{RQ}')
            else:
                out.append(f'      {LQ}pin ({px},{py}) (0,0) 1 0 0 0x0 -1 "{n}"{RQ}')
            dx, dy = rot_pt(px, py, rot)
            pins[n] = (x + dx, y + dy)
        out += [f"    {RQ}", f"  {RQ}"]
        self.comps.append("\n".join(out))
        self.pinpts += list(pins.values())
        return pins

    # ---- wiring
    def wire(self, pts, net):
        for a, b in zip(pts[:-1], pts[1:]):
            if a != b:
                self.wires.append((a[0], a[1], b[0], b[1], net))

    def label(self, x, y, net, just, port=False):
        """port=True marks the label as a hierarchical port (Qspice: right click the net, 'This is a Port')."""
        self.labels.append((x, y, net, just, 1 if port else 0))

    def stub(self, pt, direction, length, net):
        dx, dy = {"up": (0, length), "down": (0, -length), "left": (-length, 0), "right": (length, 0)}[direction]
        end = (pt[0] + dx, pt[1] + dy)
        self.wire([pt, end], net)
        self.label(end[0], end[1], net, {"up": 14, "down": 13, "left": 11, "right": 7}[direction])

    # ---- free text
    def comment(self, x, y, s, size=1):
        self.notes.append(text(x, y, BOM_MARK + s, just=7, flag=1, size=size))

    def directive(self, x, y, s):
        self.notes.append(text(x, y, BOM_MARK + s, just=7, flag=0))

    # ---- output
    def junctions(self):
        from collections import Counter
        ends = Counter()
        for x1, y1, x2, y2, _ in self.wires:
            ends[(x1, y1)] += 1
            ends[(x2, y2)] += 1
        pins = Counter(self.pinpts)
        return sorted(p for p, c in ends.items() if c + pins.get(p, 0) >= 3)

    def write(self, path):
        body = [f"{LQ}schematic"] + self.comps
        body += [f'  {LQ}net ({x},{y}) 1 {j} {p} "{n}"{RQ}' for x, y, n, j, p in self.labels]
        body += [f"  {LQ}junction ({x},{y}){RQ}" for x, y in self.junctions()]
        body += [f'  {LQ}wire ({a},{b}) ({c},{d}) "{n}"{RQ}' for a, b, c, d, n in self.wires]
        body += ["  " + t for t in self.notes]
        body.append(RQ)
        data = b"\xff\xd8\xff\xdb"
        for ln in body:
            # strings that carry the BOM marker hold UTF-8, everything else is Windows-1252
            if BOM_MARK in ln:
                head, rest = ln.split(BOM_MARK, 1)
                data += head.encode("cp1252") + b"\xef\xbb\xbf" + rest.encode("utf-8") + b"\n"
            else:
                data += ln.encode("cp1252") + b"\n"
        with open(path, "wb") as f:
            f.write(data)


BOM_MARK = "\u0001BOM\u0001"          # placeholder, replaced by the three BOM bytes when writing


# ------------------------------------------------------------------ the circuit
def stage_params(source_stage):
    """Three short visible lines; together with the hidden 'HMITT' they form the element's model text."""
    drive = f"RSRC={RSRC} RSINK=1Meg" if source_stage else f"RSRC=1Meg RSINK={RSNK}"
    return [f"VT={VTH} VH={VHYS} TD={TPD}", f"TRISE={TEDGE} TFALL={TEDGE}", drive]


XS, XH, XL = 0, -1900, -1500            # Schmitt column, PWM_H trunk, PWM_L trunk
XR, XG, XV, XPORT = 1600, 3000, 3800, 4400
DY = 1100                               # source stage sits DY above the cell centre, sink stage DY below
YT, YB = 2800, -2800                    # cell centres: top FET driver, bottom FET driver


def driver_sheet():
    sh = Sheet()
    taps = {XH: [], XL: []}
    for tag, Y, x_own, x_other, own, other in (("T", YT, XH, XL, "PWM_H", "PWM_L"),
                                                ("B", YB, XL, XH, "PWM_L", "PWM_H")):
        vdd, src, gate = f"VDD_{tag}", f"S_{tag}", f"G_{tag}"
        for st, isrc, yc in (("H", True, Y + DY), ("L", False, Y - DY)):
            o = f"O{st}_{tag}"
            lines = stage_params(isrc)
            texts = [text(200, 300, f"¥{st}_{tag}"), text(50, 0, "HMITT", just=0, flag=2, size=0.769812)]
            texts += [text(500, -260 - 170 * i, s) for i, s in enumerate(lines)]
            p = sh.place("SCHMITT", XS, yc, texts)
            sh.stub(p["Vdd"], "up", 300, vdd)
            sh.stub(p["Vss"], "down", 300, src)
            sh.stub(p["EN"], "left", 300, vdd)
            sh.wire([(x_own, yc + 200), p["b0"]], own)          # IN+ : this FET's own PWM
            sh.wire([(x_other, yc - 200), p["b1"]], other)      # IN- : the other FET's PWM (interlock)
            taps[x_own].append(yc + 200)
            taps[x_other].append(yc - 200)
            # output -> gate resistor -> gate bus
            r = sh.place("R", XR, yc + 100, [text(50, 0, f"R{'on' if isrc else 'off'}_{tag}", just=110),
                                             text(-50, 0, RON if isrc else ROFF, just=109)], rot=2, symname="R1")
            sh.wire([p["Q"], r["-"]], o)
            sh.wire([r["+"], (XG, yc + 100)], gate)
            sh.comment(500, yc + 480, "source stage (OUTH pin)" if isrc else "sink stage (OUTL pin)")
        sh.wire([(XG, Y + DY + 100), (XG, Y)], gate)
        sh.wire([(XG, Y - DY + 100), (XG, Y)], gate)
        sh.wire([(XG, Y), (XPORT, Y)], gate)
        sh.label(XPORT, Y, gate, 7, port=True)
        # floating supply, referenced to the FET source
        v = sh.place("V", XV, Y - 900, [text(100, 150, f"V_{tag}"), text(100, -150, VDRV)])
        sh.stub(v["+"], "up", 300, vdd)
        sh.wire([v["-"], (XV, Y - 1600), (XPORT, Y - 1600)], src)
        sh.label(XPORT, Y - 1600, src, 7, port=True)
        sh.comment(500, Y + DY + 900, ("TOP" if tag == "T" else "BOTTOM") + " FET DRIVER (1ED3140)", size=1.3)
    # the two PWM trunks run the full height; each port joins its trunk between the two drivers
    taps[XH].append(400)
    taps[XL].append(-400)
    for x, net in ((XH, "PWM_H"), (XL, "PWM_L")):
        ys = sorted(set(taps[x]))
        sh.wire([(x, y) for y in ys], net)
    sh.wire([(-3000, 400), (XH, 400)], "PWM_H")
    sh.label(-3000, 400, "PWM_H", 11, port=True)
    sh.wire([(-3000, -400), (XL, -400)], "PWM_L")
    sh.label(-3000, -400, "PWM_L", 11, port=True)
    # notes
    notes = ["One 1ED3140 per FET, each drawn as two stages: a source stage (OUTH pin) and a sink stage (OUTL pin).",
             "A stage switches on only while its IN+ is high and its IN- is low.",
             "IN- carries the other FET's PWM: that is the 1ED3140 interlock against cross conduction.",
             "Ports (the six flagged labels): PWM_H and PWM_L are 3.3 V logic from the controller, which sets the dead time.",
             "G_T / S_T go to the top FET gate and source, G_B / S_B to the bottom FET.",
             "V_T and V_B are ideal 12 V supplies floating on the FET source. EN pins are tied to the supply."]
    sh.comment(-3600, 6700, "HALF-BRIDGE GATE DRIVER (hierarchical sheet, one per half bridge)", size=1.6)
    for i, n in enumerate(notes):
        sh.comment(-3600, 6350 - 200 * i, n)
    return sh


SHEET_NAME = "HalfBridge_Driver"        # the block points at <SHEET_NAME>.qsch in the same folder


def testbench_sheet():
    sh = Sheet()
    # ---- the block
    W, H = 2400, 2800
    left = [("PWM_H", 600), ("PWM_L", -600)]
    right = [("G_T", 900), ("S_T", 300), ("G_B", -300), ("S_B", -900)]
    # a hierarchical entry: empty symbol name and empty type; first text = instance, second = sheet name
    out = [f"  {LQ}component (0,0) 0 0", f"    {LQ}symbol", f"      {LQ}type: {RQ}",
           f"      {LQ}shorted pins: false{RQ}",
           f"      {LQ}rect ({-W // 2},{H // 2}) ({W // 2},{-H // 2}) 0 0 0 0xff0000 0x4000000 -1 0 -1{RQ}",
           "      " + text(0, H // 2 - 250, "X1", just=15), "      " + text(0, -H // 2 + 250, SHEET_NAME, just=15)]
    # ports are matched to the sheet's port labels by name
    side = {n: (-W // 2, y, 20, 7) for n, y in left}
    side.update({n: (W // 2, y, -20, 11) for n, y in right})
    pin = {}
    for n in ("PWM_H", "PWM_L", "G_T", "S_T", "G_B", "S_B"):
        x, y, dx, j = side[n]
        out.append(f'      {LQ}pin ({x},{y}) ({dx},0) 1 {j} 0 0x0 -1 "{n}"{RQ}')
        pin[n] = (x, y)
        sh.pinpts.append((x, y))
    out += [f"    {RQ}", f"  {RQ}"]
    sh.comps.append("\n".join(out))
    # ---- PWM sources, as the controller would provide them (200 kHz, 200 ns dead time)
    xs = -4600
    vh = sh.place("Vpulse", xs, 200, [text(100, 150, "V_PWMH"), text(100, -150, "PULSE(0 3.3 0.1µ 5n 5n 2.29µ 5µ)")])
    sh.wire([vh["+"], (xs, 600), pin["PWM_H"]], "PWM_H")
    sh.stub(vh["-"], "down", 200, "GND")
    vl = sh.place("Vpulse", xs, -1000, [text(100, 150, "V_PWML"), text(100, -150, "PULSE(0 3.3 2.6µ 5n 5n 2.29µ 5µ)")])
    sh.wire([vl["+"], (xs, -600), pin["PWM_L"]], "PWM_L")
    sh.stub(vl["-"], "down", 200, "GND")
    # ---- half bridge
    lib = "|" + FET_MODEL
    mt = sh.place("MN", 4000, 1500, [text(200, 200, "M_T"), text(200, -200, "STD45N10F7")], lib=lib, symname="")
    mb = sh.place("MN", 4000, -1500, [text(200, 200, "M_B"), text(200, -200, "STD45N10F7")], lib=lib, symname="")
    sh.wire([pin["G_T"], (2000, 900), (3200, 900), (3200, 1500), mt["G"]], "GT")
    sh.wire([pin["G_B"], (2000, -300), (3200, -300), (3200, -1500), mb["G"]], "GB")
    sh.wire([pin["S_T"], (2000, 300), (4100, 300)], "SW")
    sh.wire([mt["S"], (4100, 300)], "SW")
    sh.wire([(4100, 300), mb["D"]], "SW")
    # net names on the three block outputs, handy for plotting
    sh.label(2000, 900, "GT", 14)
    sh.label(2000, 300, "SW", 14)
    sh.label(2000, -300, "GB", 14)
    # ground rail
    YG = -2300
    sh.wire([pin["S_B"], (2600, -900), (2600, YG), (4100, YG), (5600, YG), (7000, YG)], "GND")
    sh.wire([mb["S"], (4100, YG)], "GND")
    sh.stub((7000, YG), "down", 200, "GND")
    # load: constant 13 A out of the switch node
    # rot 4 as in the user's sheets: the first netlist node of the I symbol is then the top pin, so the
    # source draws current out of SW into GND; its texts carry the 180 degree flag (+64) to stay upright
    il = sh.place("I", 5600, -700, [text(-150, -100, "I_LOAD", just=71), text(-150, 100, "13", just=71)], rot=4)
    sh.wire([(4100, 300), (5600, 300), il["-"]], "SW")       # pin "-" is the top pin after the rotation
    sh.wire([il["+"], (5600, YG)], "GND")
    # bus
    vb = sh.place("V", 7000, 0, [text(100, 150, "V_BUS"), text(100, -150, "80")])
    sh.wire([mt["D"], (4100, 2300), (5600, 2300), (7000, 2300), vb["+"]], "VBUS")
    sh.label(5600, 2300, "VBUS", 14)
    sh.wire([vb["-"], (7000, YG)], "GND")
    # text
    sh.comment(-5000, 4100, "TEST BENCH for the half-bridge gate driver", size=1.6)
    for i, n in enumerate(["Replace V_PWMH and V_PWML with the controller's PWM outputs (3.3 V logic, referenced to GND).",
                           "As drawn: 200 kHz, 50 % duty, 200 ns dead time between the two signals.",
                           "The block is a hierarchical entry: right click it, Enter Schematic, to see HalfBridge_Driver.qsch.",
                           "Copy the block once per half bridge and keep HalfBridge_Driver.qsch in the same folder."]):
        sh.comment(-5000, 3750 - 200 * i, n)
    sh.directive(-5000, -3100, ".tran 20µ")
    sh.directive(-5000, -3300, ".plot V(GT,SW) V(GB) V(SW)")
    return sh


if __name__ == "__main__":
    driver_sheet().write(os.path.join(HERE, "HalfBridge_Driver.qsch"))
    testbench_sheet().write(os.path.join(HERE, "HalfBridge_Driver_Testbench.qsch"))
    print("wrote HalfBridge_Driver.qsch and HalfBridge_Driver_Testbench.qsch")
