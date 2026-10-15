"""
gen_shuffler.py - single source of truth for the Qspice baseline model of the
"Version 0" shuffler PCB (3 PV modules, 2 two-phase interleaved converters).

Run:  python gen_shuffler.py            -> writes shuffler_models.lib and stages/S*.qsch + S*.cir
      python gen_shuffler.py --verify   -> also netlists every .qsch with QUX.exe and checks that
                                           the connectivity equals the generated .cir

Everything about the circuit lives in this file; parasitic numbers come from parasitics.json
(made by pcb_parasitics.py).  Node names are the same in the schematic and the netlist so a
waveform such as V(SWA1) means the same thing in both.

Stage (Lego) order
  S1  PV string (Karmalkar-Haneefa modules, bypass diodes) + loads, plus an identical
      reference string that never gets a converter  -> the "unshuffled" baseline
  S2  + module terminal capacitance and the four 130 uF board capacitors
  S3  + converter 1 power stage (Q1..Q4, ERUC23-4R1K, TMCS1126 paths), ideal gate pulses
  S4  + converter 2 (identical block one module lower)
  S5  ideal gate pulses -> 1ED3140 drivers, 10R/4R7 gate paths, 12 V rails, bootstrap
  S6  + PCB copper, package, capacitor ESL and cable parasitics (parasitics.json)
  S7  = S6 with the full measurement set (the baseline table)
  S8  = S7 with the placeholder RC snubbers / HF caps populated and stepped (design-space)
"""

import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qsch_writer import (Schematic, sym_R, sym_C, sym_L, sym_V, sym_B, sym_D, sym_NMOS, sym_box, p_rect, SymbolDef)

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = "shuffler_models.lib"
STAGES = os.path.join(HERE, "stages")
QSPICE_DIR = r"C:\Program Files\QSPICE"

# ----------------------------------------------------------------------------- parameters
# Aiko module fit (from "PVMI 2 - Aiko.qsym"), E = irradiance in W/m2
AIKO = "avoc=0.004013 bvoc=42.5365990991 aisc=0.0148652612 bisc=0 avm=0.00116836 bvm=37.2775900901 aim=0.0141475710 bim=0.0082493126 Rs=1m Rsh=1meg"
VM_1000 = 0.00116836 * 1000 + 37.2775900901     # 38.45 V
IM_1000 = 0.0141475710 * 1000 + 0.0082493126    # 14.16 A
RMPP = 3 * VM_1000 / IM_1000                     # 8.15 ohm: resistor near the 3-module MPP at 1000 W/m2
ICC = 10.0                                       # constant-current bench load, A.  Keep it below the
# (Isc_full + Isc_shaded)/2 = 11.9 A that one equalising converter can hold with the middle module at
# 600 W/m2: at 12 A the single-converter stage (S3) has no steady state and the inductor current runs away.

# 150 W hard-frame panel (README datasheet: Voc 22.407 V, Isc 8.721 A, Vmp 18.28 V, Imp 8.207 A at 1000 W/m2):
# the Aiko irradiance fit scaled to the 150 W STC points, same irradiance dependence shape
PANEL150 = ("avoc=%.6g bvoc=%.6g aisc=%.6g bisc=0 avm=%.6g bvm=%.6g aim=%.6g bim=%.6g Rs=1m Rsh=1meg" % (
    0.004013 * 22.407 / 46.5496, 42.5365990991 * 22.407 / 46.5496,
    0.0148652612 * 8.721 / 14.8653,
    0.00116836 * 18.28 / 38.4460, 37.2775900991 * 18.28 / 38.4460,
    0.0141475710 * 8.207 / 14.1558, 0.0082493126 * 8.207 / 14.1558))
# KickAss KAUSSP80 80 W panel (Voc 25.07 V, Isc 4.35 A; Vmp/Imp not on the datasheet: 20.5 V / 3.90 A assumed,
# 36 cells), same scaling of the Aiko fit as the 150 W panel - the carpark string for the S10 PV80 runs
PANEL80 = ("avoc=%.6g bvoc=%.6g aisc=%.6g bisc=0 avm=%.6g bvm=%.6g aim=%.6g bim=%.6g Rs=1m Rsh=1meg" % (
    0.004013 * 25.07 / 46.5496, 42.5365990991 * 25.07 / 46.5496,
    0.0148652612 * 4.35 / 14.8653,
    0.00116836 * 20.5 / 38.4460, 37.2775900991 * 20.5 / 38.4460,
    0.0141475710 * 3.90 / 14.1558, 0.0082493126 * 3.90 / 14.1558))
PV_SUB = "pvmi_aiko"          # module subcircuit used by pv_string(); S9 switches to pvmi_150w
ICC_150 = 6.5                 # S9 load: current sink below what the shaded string can carry (module 2 at 600 W/m2: Isc 5.2 A + shuffling)

FSW = 200e3
TSW = 1 / FSW
FSW_CTRL = 100e3              # S9: PWM as flashed on the Nucleo then (HW_PWM_HZ); build() sets it per stage
TSW_CTRL = 1 / FSW_CTRL
# S10 family (Gate 4, fw-0.3.0): 200 kHz, bench NGE103 source / DL3021 CV load, shuffler_ctrl_dll2
S10_STAGES = ("S10c", "S10i", "S10", "S10n", "S10p", "S10xb", "S10xp")   # S10x*: overnight report matrix
S10_FSW = {"S10c": 100e3}                 # S10c = the 13 Oct bench run (100 kHz); the rest 200 kHz
BENCH_ILIM = (0.8, 1.0, 1.3)              # NGE103 current limits [A] (user, 15 Oct); VSET 25 V each
S1OFF_PARAM = None                        # S10c: converter-1 gates held low (only shuffler 2 switched on 13 Oct)
HALL_BW = None                            # S10*: TMCS1126 500 kHz output pole on the hall signals
CAP_IC = None                             # S10*: initial module voltages (v1, v2, v3) on every capacitor: with uic,
                                          # .ic only reaches the first .step run
VLOGIC = 3.3
TDEAD = 200e-9
VDRV = 12.0
IRRADIANCE_CASES = {1: (1000, 1000, 1000), 2: (1000, 600, 1000), 3: (1000, 1000, 400)}


def load_parasitics():
    p = os.path.join(HERE, "parasitics.json")
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    return {"components": {}, "lumps": {}}


PARA = load_parasitics()
COMP = PARA.get("components", {})
LUMP = PARA.get("lumps", {})


def comp(key, default):
    return COMP.get(key, default)


def lump(name):
    d = LUMP.get(name)
    if d is None:
        return 1.0, 2.0
    return d["R_mOhm"], d["L_nH"]


# When PARAM_REG is a dict (report layout), every parasitic / setting is emitted as {NAME} and the
# name -> (value, comment) pair is collected for a PARAMETERS block on the sheet.  When it is None
# (stage files) the literal value is emitted, exactly as before.
PARAM_REG = None


def pval(name, value, unit="", comment=None, fmt="g"):
    literal = f"{value:{fmt}}{unit}" if not isinstance(value, str) else value
    if PARAM_REG is None:
        return literal
    if name not in PARAM_REG:
        PARAM_REG[name] = (literal, comment)
    return "{" + name + "}"


# ----------------------------------------------------------------------------- model library
def write_lib():
    lib = f"""* shuffler_models.lib - models for the Version 0 shuffler PCB baseline (generated by gen_shuffler.py)
* Encoding: Windows-1252 (Qspice's ¥, ×, « » characters).  Values with 'u' mean micro.
*
* ---- PV module: Karmalkar-Haneefa explicit I-V model (copied verbatim from MyLibrary.lib as pvmi_orig) ----
.subckt pvmi_orig A K E
* Main Current Equation
B1 K S I=V(isc)*( 1 - (V(A,K)/V(voc))**V(m) )
* Dynamic Parameter Calculation based on Node E (Irradiance)
B2 voc 0 V=avoc*V(E)+bvoc
R1 voc 0 10K
B3 isc 0 V=aisc*V(E)+bisc
R3 isc 0 10K
B4 vm 0 V=avm*V(E)+bvm
R4 vm 0 10K
B5 im 0 V=aim*V(E)+bim
R5 im 0 10K
* High impedance input for Node E
Re E 0 10Meg
* Dynamic M-factor calculation
B6 m 0 V= log( 1 - V(im)/V(isc) ) / log( V(vm)/V(voc) )
R6 m 0 10K
* Parasitics
Rsh S K {{Rsh}}
Rs S A {{Rs}}
.ends pvmi_orig
*
* ---- same model, numerically robust: the power law is clamped at V(A,K) = 0 so a bypassed (reverse-biased)
*      module simply delivers Isc instead of evaluating a negative base to a non-integer power ----
.subckt pvmi A K E
* Main Current Equation
B1 K S I=V(isc)*( 1 - (max(V(A,K),0)/V(voc))**V(m) )
* Dynamic Parameter Calculation based on Node E (Irradiance)
B2 voc 0 V=avoc*V(E)+bvoc
R1 voc 0 10K
B3 isc 0 V=aisc*V(E)+bisc
R3 isc 0 10K
B4 vm 0 V=avm*V(E)+bvm
R4 vm 0 10K
B5 im 0 V=aim*V(E)+bim
R5 im 0 10K
* High impedance input for Node E
Re E 0 10Meg
* Dynamic M-factor calculation
B6 m 0 V= log( 1 - V(im)/V(isc) ) / log( V(vm)/V(voc) )
R6 m 0 10K
* Parasitics
Rsh S K {{Rsh}}
Rs S A {{Rs}}
.ends pvmi
*
* ---- Aiko module wrapper with the fitted coefficients (worst-case module for this test) ----
.subckt pvmi_aiko A K E
X1 A K E pvmi {AIKO}
.ends pvmi_aiko
*
* ---- 150 W hard-frame panel (carpark string), same Karmalkar-Haneefa model, STC points scaled from the Aiko fit ----
.subckt pvmi_150w A K E
X1 A K E pvmi {PANEL150}
.ends pvmi_150w
*
* ---- 80 W KAUSSP80 panel (carpark, S10p), same model ----
.subckt pvmi_80w A K E
X1 A K E pvmi {PANEL80}
.ends pvmi_80w
*
* ---- R&S NGE103 channel as a bench "module" (S10): current limit V(E)/1000 A (node E carries the limit in mA),
*      voltage clamp at VSET through RCLAMP (the CV regulator), i.e. the rectangular I-V of a PSU ----
.subckt nge_ch A K E
B1 K A I=max(V(E),0)*1m
B2 A K I=max(V(A,K)-VSET,0)/RCLAMP
Re E 0 10Meg
.ends nge_ch
*
* ---- one lumped bypass diode per module (junction box has three, this is enough for the string) ----
.model dbypass D(Is=2u N=1.05 Rs=8m Cjo=500p Vj=0.5 m=0.4)
*
* ---- TDK ERUC23-4R1K coupled inductor: user's model (Lk 2.05u + Lm 5.85u per winding, Rdc 1.85m, inverse coupled)
*      pins: 1 <-> 4 = winding A,  2 <-> 3 = winding B  (same numbering as the KiCad symbol)
.subckt ERUC23-4R1K 1 2 3 4
Rdc1 N01 1 1.85m
Lk1 N01 N02 2.05u
Rdc2 N04 2 1.85m
Lk2 N04 N03 2.05u
×1 «N03 3 N02 4» Turns=1 -1
Lm N03 3 5.85u
.ends ERUC23-4R1K
*
* ---- STMicro STD45N10F7 (100 V, 18 mOhm max, Qg 25 nC, Ciss 1640 pF, Coss 360 pF) ----
*      ESTIMATED VDMOS from datasheet headline numbers.  Replace with the model made by
*      C:\\Program Files\\QSPICE\\MOSFET.exe (or ST's PSpice model) for higher fidelity.
.model STD45N10F7 VDMOS(Rg=1.5 Vto=3.5 Kp=22 Lambda=0.005 Rd=6m Rs=2m Rb=4m Cgdmax=0.8n Cgdmin=30p a=0.5 Cgs=1.6n Cjo=1.8n m=0.5 Vj=0.8 Is=3e-12 N=1.3 tt=50n ksubthres=0.1 mfg=STMicro Vds=100 Ron=15m Qg=25n)
*
* ---- Vishay VSSA210 bootstrap Schottky (100 V, 2 A) ----
.model VSSA210 D(Is=6u N=1.08 Rs=40m Cjo=60p Vj=0.55 m=0.42 BV=100 Ibv=50u)
*
* ---- Infineon 1ED3140MU12F isolated gate driver, behavioural ----
*      OUT = (IN+ high) AND NOT (IN- high)  [the on-board cross-conduction interlock],
*      propagation delay TPD, separate source (OUTH) and sink (OUTL) pins, UVLO on VCC2-VEE2.
.subckt 1ED3140 INP INN VCC2 VEE2 OUTH OUTL params: TPD=70n TR=8n TF=8n RH=1.4 RL=1.0 VTH=1.5 UVLO=8
¥H VCC2 VEE2 OUTH ¥ INP INN VCC2 ¥ ¥ ¥ ¥ ¥ ¥ ¥ ¥ ¥ HMITT VT={{VTH}} VH=0.2 TD={{TPD}} TRISE={{TR}} TFALL={{TF}} RSRC={{RH}} RSINK=1e6 UVLO={{UVLO}}
¥L VCC2 VEE2 OUTL ¥ INP INN VCC2 ¥ ¥ ¥ ¥ ¥ ¥ ¥ ¥ ¥ HMITT VT={{VTH}} VH=0.2 TD={{TPD}} TRISE={{TR}} TFALL={{TF}} RSRC=1e6 RSINK={{RL}} UVLO={{UVLO}}
* quiescent supply current (about 0.6 mA at 12 V): gives every driver supply, bootstrap nodes included,
* a DC path so the operating point is well posed (without it the high-side supply node is singular at DC)
Rq VCC2 VEE2 20k
.ends 1ED3140
*
* ---- TI TMCS1126B4 hall sensor: conductor path only (sensor output not modelled) ----
.subckt TMCS1126 IN OUT params: RSH=0.7m LSH=0.5n
R1 IN N1 {{RSH}}
L1 N1 OUT {{LSH}} RPAR=5
.ends TMCS1126
*
* ---- generic PCB trace / cable / connector lump ----
*      RP = parallel damping on the inductance (skin/dielectric loss at tens of MHz); without it the
*      nH loops with the MOSFET capacitances ring with Q > 100 and the simulator stalls.
.subckt trace A B params: R=1m L=1n RP=5
R1 A N1 {{R}}
L1 N1 B {{L}} RPAR={{RP}}
.ends trace
"""
    with open(os.path.join(HERE, LIB), "wb") as f:
        f.write(lib.encode("cp1252"))


# ----------------------------------------------------------------------------- circuit builder
class Circuit:
    """Builds the netlist (.cir) and the schematic (.qsch) from the same calls."""

    def __init__(self, stage, title):
        self.stage, self.title = stage, title
        self.sch = Schematic()
        self.lines = []      # netlist element lines
        self.directives = []
        self.meas = []
        self.syms = {"R": sym_R(), "C": sym_C(), "L": sym_L(), "V": sym_V(), "B": sym_B(),
                     "D": sym_D(LIB), "M": sym_NMOS(LIB)}

    # --- netlist + symbol placement -------------------------------------------------
    def el(self, line):
        self.lines.append(line)

    def two(self, kind, ref, n1, n2, value, x, y, rot=0, extra=(), stubs=None, wire=True, label_side="above"):
        """Two-terminal element. Pin order: (1,2) = (+,-) = (K,A for diodes handled separately).
        label_side: for a part lying flat, "above" (default) or "below" the body."""
        p = self.sch.add(self.syms[kind], x, y, ref, value, extra=extra, rot=rot, label_side=label_side)
        self.el(" ".join([ref, n1, n2, value] + list(extra)))
        return p

    def R(self, ref, n1, n2, value, x, y, rot=0, extra=(), label_side="above"):
        return self.two("R", ref, n1, n2, value, x, y, rot, extra, label_side=label_side)

    def C(self, ref, n1, n2, value, x, y, rot=0, extra=()):
        return self.two("C", ref, n1, n2, value, x, y, rot, extra)

    def Lel(self, ref, n1, n2, value, x, y, rot=0, extra=()):
        return self.two("L", ref, n1, n2, value, x, y, rot, extra)

    def V(self, ref, np_, nm, value, x, y, rot=0):
        return self.two("V", ref, np_, nm, value, x, y, rot)

    def B(self, ref, np_, nm, expr, x, y, rot=0):
        return self.two("B", ref, np_, nm, expr, x, y, rot)

    def D(self, ref, na, nk, model, x, y, rot=0):
        p = self.sch.add(self.syms["D"], x, y, ref, model, rot=rot)
        self.el(f"{ref} {na} {nk} {model}")
        return p

    def M(self, ref, nd, ng, ns, model, x, y, rot=0):
        p = self.sch.add(self.syms["M"], x, y, ref, model, rot=rot)
        self.el(f"{ref} {nd} {ng} {ns} {ns} {model}")
        return p

    def X(self, ref, sym, nodes, subname, x, y, rot=0, params=""):
        p = self.sch.add(sym, x, y, ref, subname, extra=([params] if params else ()), rot=rot)
        self.el(" ".join([ref] + nodes + [subname] + ([params] if params else [])))
        return p

    def DLL(self, ref, sym, ins, outs, gnd, dll, x, y, params="Rout=1 Cout=1p"):
        """QSPICE C-block (Ø(.DLL) symbol). Netlist form as QUX writes it:
        Ø´ref «in´d ...» «out´d ...» «ref»  dllname params"""
        p = self.sch.add(sym, x, y, ref, dll, extra=tuple(params.split()), rot=0)
        ins_s = " ".join(n + "\u00b4d" for n in ins)
        outs_s = " ".join(n + "\u00b4d" for n in outs)
        self.el(f"\u00d8\u00b4{ref} \u00ab{ins_s}\u00bb \u00ab{outs_s}\u00bb \u00ab{gnd}\u00bb  {dll} {params}")
        return p

    # --- schematic helpers ------------------------------------------------------------
    def wire(self, pts, net):
        self.sch.wire(pts, net)

    def stub(self, pt, net, direction, length=200):
        self.sch.stub(pt, net, direction, length)

    def rail(self, y, x_from, x_to, net, taps=(), label_at="left"):
        """Horizontal rail split at every tap x so that taps become wire vertices (junctions)."""
        xs = sorted(set([x_from, x_to] + [t for t in taps if x_from < t < x_to]))
        self.wire([(x, y) for x in xs], net)
        self.sch.label(x_from if label_at == "left" else x_to, y, net, 14)     # centred above the rail end, off the feeding wire

    def directive(self, text):
        self.directives.append(text)

    def measure(self, text):
        self.meas.append(text)

    # --- output ---------------------------------------------------------------------
    def netlist_text(self):
        def cir_nodes(line):
            return line.replace(" GND ", " 0 ").replace(" GND\n", " 0\n")
        out = [f"* {self.title}", f".lib {LIB}"]
        for l in self.lines:
            toks = l.split(" ")
            toks = ["0" if t == "GND" else t for t in toks]
            out.append(" ".join(toks))
        out += self.directives + self.meas + [".end", ""]
        return "\n".join(out)

    def write(self, path_base, x_text=-9000, y_text=-14000, place_directives=True):
        with open(path_base + ".cir", "wb") as f:
            f.write(self.netlist_text().encode("cp1252"))
        if place_directives:
            y = y_text
            self.sch.comment(x_text, y + 600, self.title, size=1.5)
            for d in self.directives + self.meas:
                self.sch.directive(x_text, y, d)
                y -= 150
        self.sch.write(path_base + ".qsch")


# ----------------------------------------------------------------------------- blocks
def pv_string(c, x0, y0, prefix, nets, load_ref, with_cpv, with_cables, sense_prefix, label_side="right"):
    """Three modules in series between the rails in `nets` (top to bottom), rail spacing 2800."""
    rails = nets                                   # [top, mid12, mid23, bottom]
    ys = [y0 - 2800 * i for i in range(4)]
    xr = x0 + (1000 if with_cpv else 600)          # right end of the module mini-rails
    for k in range(3):
        yt = ys[k]
        n_top, n_bot = rails[k], rails[k + 1]
        a_node = f"{sense_prefix}a{k+1}"                 # module anode after the sense source
        e_node = f"E{k+1}"
        if with_cables:
            # board net label at the rail height, cable lump down to the module-side mini rail
            top_term, bot_term = f"{prefix}m{k+1}p", f"{prefix}m{k+1}n"
            Rc = comp("cable_R_mOhm_per_m", 4.3) * comp("cable_len_m", 1.5) + comp("XT60_R_mOhm", 0.5)
            Lc = comp("cable_L_nH_per_m", 500) * comp("cable_len_m", 1.5)
            cab = (f"R={pval('Rcab', Rc, 'm', 'module cable, one lead: 1.5 m of 4 mm2 + XT60 contact', '.2f')} "
                   f"L={pval('Lcab', Lc, 'n', 'module cable, one lead (about 1 uH/m loop)', '.0f')} RP=50")
            c.X(f"Xcab{prefix}{k+1}p", TRACE_SYM, [top_term, n_top], "trace", x0, yt - 300, rot=2,
                params=cab)                                    # A (module) at yt-600, B (board) at yt
            c.stub((x0, yt), n_top, "left", 400)
            c.X(f"Xcab{prefix}{k+1}n", TRACE_SYM, [bot_term, n_bot], "trace", x0, yt - 2300, rot=6,
                params=cab)                                    # A (module) at yt-2000, B (board) at yt-2600
            c.wire([(x0, yt - 2600), (x0, yt - 2800)], n_bot)
            y_top_rail, y_bot_rail = yt - 600, yt - 2000
        else:
            top_term, bot_term = n_top, n_bot
            c.wire([(x0, yt), (x0, yt - 600)], n_top)
            c.wire([(x0, yt - 2000), (x0, yt - 2800)], n_bot)
            y_top_rail, y_bot_rail = yt, yt - 2800
        # sense source: "+" at the module side (rot 4 puts + at the bottom) -> I(Vi) = module current
        c.V(f"Vi{sense_prefix}{k+1}", a_node, top_term, "0", x0, yt - 800, rot=4)
        c.X(f"Xpv{sense_prefix}{k+1}", PV_SYM, [a_node, bot_term, e_node], PV_SUB, x0, yt - 1500)
        c.stub((x0 - 300, yt - 1500), e_node, "left", 300)
        # bypass diode (K at top) and module capacitance between the module terminals
        c.D(f"Dbp{sense_prefix}{k+1}", bot_term, top_term, "dbypass", x0 + 600, yt - 1300)
        c.wire([(x0 + 600, yt - 1100), (x0 + 600, y_top_rail)], top_term)
        c.wire([(x0 + 600, yt - 1500), (x0 + 600, y_bot_rail)], bot_term)
        if with_cpv:
            c.C(f"Cpv{sense_prefix}{k+1}", top_term, bot_term, pval("Cpv", comp('Cpv_nF', 10), "n", "PV module terminal capacitance (ballpark)"),
                x0 + 1000, yt - 1300, extra=("RSER=0.1" + (f" IC={CAP_IC[k]:g}" if CAP_IC and sense_prefix == "" else ""),))
            c.wire([(x0 + 1000, yt - 1100), (x0 + 1000, y_top_rail)], top_term)
            c.wire([(x0 + 1000, yt - 1500), (x0 + 1000, y_bot_rail)], bot_term)
        if with_cables:
            # module-side mini rails carry the diode / Cpv taps (separate nets from the board rails)
            c.rail(y_top_rail, x0, xr, top_term, taps=[x0 + 600], label_at="right")
            c.rail(y_bot_rail, x0, xr, bot_term, taps=[x0 + 600], label_at="right")
    if not with_cables:
        taps = [x0, x0 + 600] + ([x0 + 1000] if with_cpv else [])
        for i, y in enumerate(ys):
            c.rail(y, x0 - 400, x0 + 1400, rails[i], taps=taps, label_at="right" if label_side == "right" else "left")
    else:
        c.stub((x0, ys[3]), rails[3], "left", 400)
    # load: behavioural source = resistor near MPP or constant current sink
    # the current sink ramps up over the first 200 us: a 10 A step at t=0 into a string that starts at 0 V
    # broke the operating point of the single-sheet file (the stage files only survived it by luck of the solver)
    vstr_ex = f"V({rails[0]})" if rails[3] == "GND" else f"V({rails[0]},{rails[3]})"
    c.B(load_ref, rails[0], rails[3], f"I=if(LOADSEL<0.5, V({rails[0]})/Rmpp, if(LOADSEL<1.5, Icc*min(1, time/200u), max({vstr_ex}-VCV,0)/RCV))", x0 + 2000, y0 - 1400)
    c.stub((x0 + 2000, y0 - 1200), rails[0], "up", 300)
    c.stub((x0 + 2000, y0 - 1600), rails[3], "down", 300)


PV_SYM = sym_box("pvmi_aiko", "PV module (Karmalkar-Haneefa)", 600, 1000, [("A", 0, 500), ("K", 0, -500), ("E", -300, 0)], libfile=LIB)
TRACE_SYM = sym_box("trace", "PCB trace / cable lump", 600, 200, [("A", -300, 0), ("B", 300, 0)], libfile=LIB)
L_SYM = sym_box("ERUC23-4R1K", "TDK coupled inductor", 800, 600, [("1", -200, 300), ("2", 200, 300), ("3", 400, -100), ("4", -400, 100)], libfile=LIB)
TMCS_SYM = sym_box("TMCS1126", "hall current sensor (conductor path)", 200, 400, [("IN", 0, -200), ("OUT", 0, 200)], libfile=LIB)
DRV_SYM = sym_box("1ED3140", "isolated gate driver", 800, 600, [("INP", -400, 100), ("INN", -400, -100), ("VCC2", 0, 300), ("VEE2", 0, -300), ("OUTH", 400, 100), ("OUTL", 400, -100)], libfile=LIB)


def bulk_caps(c, x0, y0, with_esl):
    """C1: PV1P-PV2P, C2/C3: PV2P-PV3P, C4: PV3P-GND (as on the board)."""
    esr = "RSER=" + pval("ESR130", comp('C130_ESR_mOhm', 28), "m", "TDK B40910A0137M000 130 uF: ESR")
    esl = pval("ESL130", comp('C130_ESL_nH', 15), "n", "130 uF radial can: ESL")
    caps = [("C1", "PV1P", "PV2P", x0, y0 - 1400), ("C2", "PV2P", "PV3P", x0, y0 - 4200),
            ("C3", "PV2P", "PV3P", x0 + 500, y0 - 4200), ("C4", "PV3P", "GND", x0, y0 - 7000)]
    for ref, nt, nb, x, y in caps:
        if CAP_IC:
            v = CAP_IC[{"C1": 0, "C2": 1, "C3": 1, "C4": 2}[ref]]
            esr = esr.split(" IC=")[0] + f" IC={v:g}"
        if with_esl:
            mid = f"{ref.lower()}n"
            c.C(ref, nt, mid, "130u", x, y, extra=(esr,))
            c.Lel(f"L{ref.lower()}", mid, nb, esl, x, y - 400, extra=("RPAR=5",))
            c.wire([(x, y - 200), (x, y - 200)], mid)
            c.stub((x, y + 200), nt, "up", 300)
            c.stub((x, y - 600), nb, "down", 300)
        else:
            c.C(ref, nt, nb, "130u", x, y, extra=(esr,))
            c.stub((x, y + 200), nt, "up", 300)
            c.stub((x, y - 200), nb, "down", 300)


def converter(c, k, X0, Y0, T, M, B, drive, paras, snub, ctrl=False):
    """One two-phase converter.  T/M/B: board nets for Input_T / Output(midpoint) / Input_B.
    drive: 'ideal' (pulse sources) or 'driver' (1ED3140 + bootstrap + Vreg)."""
    s = str(k)
    # ---- rail nets (with parasitics the FET rails are behind trace lumps)
    if paras:
        Tn, Mn, Bn = f"T{s}", f"M{s}", f"B{s}"
        for nm, (nfrom, nto, y) in {"T": (T, Tn, Y0), "B": (B, Bn, Y0 - 2400)}.items():
            R, L = lump(f"{nm}{s}")
            c.X(f"Xt{nm}{s}", TRACE_SYM, [nfrom, nto], "trace", X0 + 600, y, params=lump_params(f"{nm}{s}", R, L))
            # board-net label stub points away from the driver column (up for the top rail, down for the bottom)
            c.stub((X0 + 300, y), nfrom, "up" if nm == "T" else "down", 300)
            c.wire([(X0 + 900, y), (X0 + 1200, y)], nto)
    else:
        Tn, Mn, Bn = T, M, B
    xa, xb = X0 + 2000, X0 + 7400          # leg A (normal), leg B (mirrored)
    xL = X0 + 4700                          # coupled inductor between the legs
    xsnA, xsnB = X0 + 2800, X0 + 6600       # snubber columns (between each FET junction and its switch-node lump)
    swa, swb = f"SWA{s}", f"SWB{s}"
    # rails (the top rail is split around the sensor column that rises through it)
    c.rail(Y0, X0 + 1200, X0 + 4200, Tn, taps=[xa + 100, xsnA], label_at="left")
    c.rail(Y0, X0 + 5200, X0 + 8200, Tn, taps=[xb - 100, xsnB], label_at="right")
    c.rail(Y0 - 2400, X0 + 1200, X0 + 8200, Bn, taps=[xa + 100, xb - 100, xsnA, xsnB], label_at="left")
    # ---- MOSFET legs
    Ld = pval("Ld_pkg", comp('TO252_Ld_nH', 1.5), "n", "TO-252 drain tab inductance")
    Ls = pval("Ls_pkg", comp('TO252_Ls_nH', 3), "n", "TO-252 source lead inductance (common-source)")
    for leg, xl, rot, sw in (("A", xa, 0, swa), ("B", xb, 8, swb)):
        xp = xl + 100 if rot == 0 else xl - 100          # D/S pin x
        xg = xl - 200 if rot == 0 else xl + 200          # gate pin x
        qt, qb = f"MT{leg}{s}", f"MB{leg}{s}"
        gT, gB = f"gT{leg}{s}", f"gB{leg}{s}"
        if paras:
            dT, sT, dB, sB = f"dT{leg}{s}", f"sT{leg}{s}", f"dB{leg}{s}", f"sB{leg}{s}"
            damp = ("RPAR=5",)      # lead loss at ~70 MHz; undamped, Ls resonates with Cds at Q>100
            lrot = 8 if rot == 0 else 0     # package-inductor labels face away from the inductor side
            c.Lel(f"LdT{leg}{s}", Tn, dT, Ld, xp, Y0 - 200, rot=lrot, extra=damp)
            c.Lel(f"LsT{leg}{s}", sT, sw, Ls, xp, Y0 - 1000, rot=lrot, extra=damp)
            c.Lel(f"LdB{leg}{s}", sw, dB, Ld, xp, Y0 - 1400, rot=lrot, extra=damp)
            c.Lel(f"LsB{leg}{s}", sB, Bn, Ls, xp, Y0 - 2200, rot=lrot, extra=damp)
        else:
            dT, sT, dB, sB = Tn, sw, sw, Bn
            c.wire([(xp, Y0), (xp, Y0 - 400)], Tn)
            c.wire([(xp, Y0 - 800), (xp, Y0 - 1200)], sw)
            c.wire([(xp, Y0 - 1200), (xp, Y0 - 1600)], sw)
            c.wire([(xp, Y0 - 2000), (xp, Y0 - 2400)], Bn)
        c.M(qt, dT, gT, sT, "STD45N10F7", xl, Y0 - 600, rot=rot)
        c.M(qb, dB, gB, sB, "STD45N10F7", xl, Y0 - 1800, rot=rot)
        # gate networks
        for pos, g, y, src_ref in (("T", gT, Y0 - 600, qt), ("B", gB, Y0 - 1800, qb)):
            ref_src = "SW" if pos == "T" else "B"
            src_node = sw if pos == "T" else Bn
            if drive == "ideal":
                # one 4.7 ohm resistor and an ideal 12 V pulse referenced to the FET source
                xr = xg - 200 if rot == 0 else xg + 200
                gs = f"gs{pos}{leg}{s}"
                c.R(f"Rg{pos}{leg}{s}", gs, g, pval("Rgate", 4.7, "", "gate resistor (ideal-drive stages)"), xr, y, rot=2 if rot == 0 else 6)
                xe = xr - 200 if rot == 0 else xr + 200
                c.stub((xe, y), gs, "left" if rot == 0 else "right", 200)
                pulse = pulse_expr(pos, leg, k)
                xv = X0 - 800 if rot == 0 else X0 + 10200
                p = c.V(f"Vg{pos}{leg}{s}", gs, src_node, pulse, xv, y - 200)
                c.stub(p.pin["+"], gs, "up", 200)
                c.stub(p.pin["-"], src_node, "down", 200)
            else:
                # separate source (10 R) and sink (4R7) paths as on the Gate_Drivers sheet
                oh, ol = f"oh{pos}{leg}{s}", f"ol{pos}{leg}{s}"
                if paras:
                    Rgl, Lgl = lump(f"g{pos}{leg}{s}")
                    gi = f"gi{pos}{leg}{s}"
                    # trace lump between the gate pin and the resistor junction (mirrored for leg B)
                    c.X(f"Xtg{pos}{leg}{s}", TRACE_SYM, [gi, g], "trace", xg - 500 if rot == 0 else xg + 500, y,
                        rot=rot, params=lump_params(f"g{pos}{leg}{s}", Rgl, Lgl))
                    c.wire([(xg, y), (xg - 200 if rot == 0 else xg + 200, y)], g)
                    xj = xg - 900 if rot == 0 else xg + 900
                    c.wire([(xj, y), (xg - 800 if rot == 0 else xg + 800, y)], gi)
                    gnet = gi
                else:
                    xj = xg - 100 if rot == 0 else xg + 100
                    c.wire([(xg, y), (xj, y)], g)
                    gnet = g
                c.wire([(xj, y + 100), (xj, y - 100)], gnet)
                xr = xj - 200 if rot == 0 else xj + 200
                c.R(f"Ron{pos}{leg}{s}", oh, gnet, pval("Ron", 10, "", "driver OUTH (source) path resistor, KOA SG73S 10R"), xr, y + 100, rot=2 if rot == 0 else 6)
                c.R(f"Roff{pos}{leg}{s}", ol, gnet, pval("Roff", 4.7, "", "driver OUTL (sink) path resistor, KOA SG73P 4R7"), xr, y - 100, rot=2 if rot == 0 else 6,
                    label_side="below")     # the lower one of the stacked pair: labels under it, clear of the junction
                # with the gate trace lumps in place the drivers move outward to leave room for the labels
                xd = (X0 - 400 if paras else X0 + 200) if rot == 0 else (X0 + 10000 if paras else X0 + 9200)
                vcc = f"BOOT{leg}{s}" if pos == "T" else f"VREG{s}"
                vee = sw if pos == "T" else Bn
                inp, inn = pwm_nets(pos, leg, k)
                p = c.X(f"Xd{pos}{leg}{s}", DRV_SYM, [inp, inn, vcc, vee, oh, ol], "1ED3140", xd, y, rot=rot)
                c.wire([p.pin["OUTH"], (xr - 200 if rot == 0 else xr + 200, y + 100)], oh)
                c.wire([p.pin["OUTL"], (xr - 200 if rot == 0 else xr + 200, y - 100)], ol)
                c.stub(p.pin["VCC2"], vcc, "up", 200)
                c.stub(p.pin["VEE2"], vee, "down", 200)
                c.stub(p.pin["INP"], inp, "left" if rot == 0 else "right", 200)
                c.stub(p.pin["INN"], inn, "left" if rot == 0 else "right", 200)
        # snubber placeholders (S8): R in series with C across each FET; labels face away from the inductor
        if snub:
            xs = xsnA if rot == 0 else xsnB
            srot = 0 if rot == 0 else 8
            c.R(f"RsnT{leg}{s}", Tn, f"snT{leg}{s}", "{Rsn}", xs, Y0 - 600, rot=srot)
            c.C(f"CsnT{leg}{s}", f"snT{leg}{s}", sw, "{Csn}", xs, Y0 - 1000, rot=srot)
            c.wire([(xs, Y0), (xs, Y0 - 400)], Tn)
            c.wire([(xs, Y0 - 1200), (xp, Y0 - 1200)], sw)
            c.R(f"RsnB{leg}{s}", sw, f"snB{leg}{s}", "{Rsn}", xs, Y0 - 1400, rot=srot)
            c.C(f"CsnB{leg}{s}", f"snB{leg}{s}", Bn, "{Csn}", xs, Y0 - 1800, rot=srot)
            c.wire([(xs, Y0 - 2000), (xs, Y0 - 2400)], Bn)
    # ---- coupled inductor, sense sources, hall sensor paths, midpoint
    yL = Y0 - 1200
    la2, lb2 = f"LA2_{s}", f"LB2_{s}"
    if paras:
        # switch-node copper between the FET pads and the inductor pad (KiCad M_T_xph_S nets)
        swa_l, swb_l = f"SWAL{s}", f"SWBL{s}"
        R, L = lump(f"SWA{s}")
        c.X(f"XtSWA{s}", TRACE_SYM, [swa, swa_l], "trace", xL - 1100, Y0 - 1200, params=lump_params(f"SWA{s}", R, L))
        # the FET-junction side keeps the name the drivers / bootstrap / measurements refer to;
        # its label hangs off a short stub on the gate side of the column where nothing else lives
        c.wire([(xa + 100, Y0 - 1200), (xL - 1400, Y0 - 1200)], swa)
        c.sch.label(xa + 500, Y0 - 1200, swa, 13)          # on the wire, below it, clear of the package-L labels
        c.wire([(xL - 800, Y0 - 1200), (xL - 700, Y0 - 1200), (xL - 700, Y0 - 1100), (xL - 400, Y0 - 1100)], swa_l)
        c.sch.label(xL - 700, Y0 - 1200, swa_l, 13)
        R, L = lump(f"SWB{s}")
        c.X(f"XtSWB{s}", TRACE_SYM, [swb_l, swb], "trace", xL + 1100, Y0 - 1200, params=lump_params(f"SWB{s}", R, L))
        c.wire([(xb - 100, Y0 - 1200), (xL + 1400, Y0 - 1200)], swb)
        c.sch.label(xb - 500, Y0 - 1200, swb, 13)
        c.wire([(xL + 800, Y0 - 1200), (xL + 700, Y0 - 1200), (xL + 700, Y0 - 1300), (xL + 400, Y0 - 1300)], swb_l)
        c.sch.label(xL + 700, Y0 - 1200, swb_l, 14)
    else:
        swa_l, swb_l = swa, swb
        c.wire([(xa + 100, Y0 - 1200), (xL - 700, Y0 - 1200), (xL - 700, Y0 - 1100), (xL - 400, Y0 - 1100)], swa)
        c.sch.label(xL - 700, Y0 - 1200, swa, 13)
        c.wire([(xb - 100, Y0 - 1200), (xL + 700, Y0 - 1200), (xL + 700, Y0 - 1300), (xL + 400, Y0 - 1300)], swb)
        c.sch.label(xL + 700, Y0 - 1200, swb, 14)
    c.X(f"XL{s}", L_SYM, [la2, lb2, swb_l, swa_l], "ERUC23-4R1K", xL, yL)
    Rs_ = pval("Rtmcs", comp("TMCS_R_mOhm", 0.7), "m", "TMCS1126 conductor resistance")
    Ls_ = pval("Ltmcs", comp("TMCS_L_nH", 0.5), "n", "TMCS1126 conductor inductance")
    for leg, xsn, l2 in (("A", xL - 200, la2), ("B", xL + 200, lb2)):
        l2s = f"L{leg}2s_{s}"
        # sense source with + at the inductor side (rot 4): I(Vs) = current from inductor into the midpoint
        c.V(f"Vs{leg}{s}", l2, l2s, "0", xsn, Y0 - 700, rot=4)
        if paras:
            R, L = lump(f"L{leg}{s}")
            lt = f"L{leg}2t_{s}"
            # vertical trace lump: A (module side of the box, rot 2 -> bottom) at Y0-500, B at Y0+100
            c.X(f"XtL{leg}{s}", TRACE_SYM, [l2s, lt], "trace", xsn, Y0 - 200, rot=2, params=lump_params(f"L{leg}{s}", R, L))
            c.X(f"Xs{leg}{s}", TMCS_SYM, [lt, Mn], "TMCS1126", xsn, Y0 + 300, params=f"RSH={Rs_} LSH={Ls_}")
            c.wire([(xsn, Y0 + 500), (xsn, Y0 + 600)], Mn)
        else:
            c.X(f"Xs{leg}{s}", TMCS_SYM, [l2s, Mn], "TMCS1126", xsn, Y0 - 300, params=f"RSH={Rs_} LSH={Ls_}")
            c.wire([(xsn, Y0 - 100), (xsn, Y0 + 600)], Mn)
    c.rail(Y0 + 600, xL - 200, xL + 200, Mn, label_at="right")
    if paras:
        R, L = lump(f"M{s}")
        c.X(f"XtM{s}", TRACE_SYM, [Mn, M], "trace", xL + 800, Y0 + 600, params=lump_params(f"M{s}", R, L))
        c.wire([(xL + 200, Y0 + 600), (xL + 500, Y0 + 600)], Mn)
        c.stub((xL + 1100, Y0 + 600), M, "right", 300)
    # ---- driver supplies
    if drive == "driver":
        xv = X0 - 3600                       # 12 V rail cluster, well left of the bootstrap parts and driver labels
        vreg = f"VREG{s}"
        p = c.V(f"Vreg{s}", vreg, Bn, pval("Vreg", VDRV, "", "gate-drive rail from the Wurth 173951275 module (ideal source)"), xv, Y0 - 1200)
        c.stub(p.pin["+"], vreg, "up", 200)
        c.stub(p.pin["-"], Bn, "down", 200)
        # low-side driver decoupling (C41/C43 equivalents)
        p = c.C(f"CvL{s}", vreg, Bn, "100n", xv + 400, Y0 - 1200, extra=(f"RSER={comp('C100n_ESR_mOhm', 20):g}m",))
        c.stub(p.pin["1"], vreg, "up", 200); c.stub(p.pin["2"], Bn, "down", 200)
        p = c.C(f"Cv2L{s}", vreg, Bn, "10u", xv + 800, Y0 - 1200, extra=(f"RSER={comp('C10u_ESR_mOhm', 5):g}m",))
        c.stub(p.pin["1"], vreg, "up", 200); c.stub(p.pin["2"], Bn, "down", 200)
        # bootstrap networks: VREG -> 10R -> VSSA210 -> BOOT, 100n || 10u to the switch node
        # with parasitics the leg-A driver sits at X0-400 and its input labels reach X0-1000: keep the bootstrap clear of them
        for leg, xbs, sw in (("A", X0 - 2000 if paras else X0 - 1400, swa), ("B", X0 + 12600, swb)):
            boot, dn = f"BOOT{leg}{s}", f"bsa{leg}{s}"      # (not 'dbA1': SPICE names are case-insensitive and dBA1 is a drain node)
            p = c.D(f"Db{leg}{s}", dn, boot, "VSSA210", xbs, Y0 - 200)
            c.stub(p.pin["K"], boot, "up", 200)
            c.R(f"Rb{leg}{s}", dn, vreg, pval("Rboot", 10, "", "bootstrap series resistor"), xbs, Y0 - 600)
            c.stub((xbs, Y0 - 800), vreg, "down", 200)
            p = c.C(f"Cb{leg}{s}", boot, sw, "100n", xbs - 400, Y0 - 200, extra=(f"RSER={comp('C100n_ESR_mOhm', 20):g}m",))
            c.stub(p.pin["1"], boot, "up", 200); c.stub(p.pin["2"], sw, "down", 200)
            p = c.C(f"Cb2{leg}{s}", boot, sw, "10u", xbs - 800, Y0 - 200, extra=(f"RSER={comp('C10u_ESR_mOhm', 5):g}m",))
            c.stub(p.pin["1"], boot, "up", 200); c.stub(p.pin["2"], sw, "down", 200)
        # PWM sources (NUCLEO timer outputs, 3.3 V logic, dead time from the PWM)
        for i, (pos, leg) in enumerate((("T", "A"), ("B", "A"), ("T", "B"), ("B", "B"))):
            inp, _ = pwm_nets(pos, leg, k)
            if ctrl:
                # closed loop (S9): HRTIM-style comparator of the controller duty D{leg}{k} (0..1, held by the
                # DLL between control ticks) against a sawtooth RAMP{leg} (leg B shifted half a period); the
                # 200 ns dead time is cut from both edges exactly as the HRTIM dead-time generator does
                dead = TDEAD / TSW_CTRL
                ramp, dnet = f"RAMP{leg}", f"D{leg}{s}C"
                if pos == "T":
                    expr = f"V=if(V({ramp}) < V({dnet})-{dead:g}, {VLOGIC}, 0)"
                else:
                    expr = f"V=if(V({ramp}) > V({dnet}), if(V({ramp}) < {1 - dead:g}, {VLOGIC}, 0), 0)"
                if S1OFF_PARAM and k == 1:
                    expr = f"V=if({S1OFF_PARAM}>0.5, 0, {expr[2:]})"
                p = c.B(f"Bp{pos}{leg}{s}", inp, "GND", expr, xv + 400 * i, Y0 - 3200)
            else:
                p = c.V(f"Vp{pos}{leg}{s}", inp, "GND", pulse_expr(pos, leg, k, logic=True), xv + 400 * i, Y0 - 3200)
            c.stub(p.pin["+"], inp, "up", 200)
            c.stub(p.pin["-"], "GND", "down", 200)
    # HF decoupling placeholders (S8): 3 x Chf per leg between the FET rails (C91..C96 positions)
    if snub:
        for leg, xh in (("A", X0 + 13800), ("B", X0 + 14800)):   # 1000 apart so the RSER texts do not touch
            hn = f"hf{leg}{s}"
            p = c.C(f"Chf{leg}{s}", Tn, hn, "{3*Chf}", xh, Y0 - 800, extra=(f"RSER={comp('C100n_ESR_mOhm', 20)/3:g}m",))
            c.stub(p.pin["1"], Tn, "up", 200)
            c.Lel(f"Lhf{leg}{s}", hn, Bn, f"{comp('C100n_ESL_nH', 0.8)/3:g}n", xh, Y0 - 1200)
            c.stub((xh, Y0 - 1400), Bn, "down", 200)


CTRL_INS = ["PV1P", "PV2P", "PV3P", "HSA1", "HSB1", "HSA2", "HSB2", "CTRL_EN", "VREF1", "VREF2"]
CTRL_OUTS = ["DA1", "DB1", "DA2", "DB2", "RV1", "RV2", "BETA", "STRESS", "IM1R", "IM2R"]


def ctrl_sym():
    """Ø(.DLL) symbol for shuffler_ctrl_dll.dll: inputs left, outputs right, reference at the bottom."""
    w, h = 1600, 2200
    prims = [p_rect(-w // 2, h // 2, w // 2, -h // 2, "box")]
    pins = []
    for i, n in enumerate(CTRL_INS):
        pins.append((n, -w // 2, h // 2 - 200 - 200 * i, 60, -40, 13, 145))
    for i, n in enumerate(CTRL_OUTS):
        pins.append((n, w // 2, h // 2 - 200 - 200 * i, -60, -40, 14, 146))
    pins.append(("GND", 0, -h // 2, 0, 60, 11, 147))
    return SymbolDef("shuffler_ctrl_dll", "\u00d8(.DLL)", "control stack C-block (6_RTOS/ctrl_core via 2_Qspice/ctrl_dll)",
                     prims, pins, libfile=None, ref_pos=(0, h // 2 + 150), val_pos=(0, 0), extra_pos=(0, -h // 2 - 150),
                     text_just=0)


def ctrl_block(c, x0, y0, vstep=1.0, t_en=1e-3, t_step=8e-3):
    """Closed-loop control around the two converters (stage S9):
    hall-sensor voltages from the inductor sense sources (A phases 100 mV/A into the midpoint, B phases
    25 mV/A reversed as mounted = positive OUT of the midpoint, which is the control stack's convention), the controller DLL (samples/quantises like the firmware, 10 kHz tick, module currents
    reconstructed), sawtooth ramps for the HRTIM-style PWM comparators in converter(), enable and
    Vref test inputs."""
    # hall sensor outputs (the TMCS1126 output stage, 1.65 V + S*I)
    for k, (leg, S) in enumerate(((("A", 0.1), ("B", -0.025)) * 2)):
        conv = 1 + k // 2
        p = c.B(f"Bhs{leg}{conv}", f"HS{leg}{conv}", "GND", f"V=1.65+{S:g}*I(Vs{leg}{conv})", x0 + 500 * k, y0)
        c.stub(p.pin["+"], f"HS{leg}{conv}", "up", 200)
        c.stub(p.pin["-"], "GND", "down", 200)
    # PWM ramps, leg B half a period behind
    tsw, tr = TSW_CTRL, TSW_CTRL - 2e-9
    p = c.V("Vrampa", "RAMPA", "GND", f"PULSE(0 1 0 {tr:.4g} 1n 1n {tsw:g})", x0 + 2200, y0)
    c.stub(p.pin["+"], "RAMPA", "up", 200); c.stub(p.pin["-"], "GND", "down", 200)
    p = c.V("Vrampb", "RAMPB", "GND", f"PULSE(0 1 {tsw / 2:g} {tr:.4g} 1n 1n {tsw:g})", x0 + 2700, y0)
    c.stub(p.pin["+"], "RAMPB", "up", 200); c.stub(p.pin["-"], "GND", "down", 200)
    # enable (open loop at 0.5 duty until t_en) and the Vref step test
    p = c.V("Ven", "CTRL_EN", "GND", f"PWL(0 0 {t_en:g} 0 {t_en + 1e-6:g} 1)", x0 + 3200, y0)
    c.stub(p.pin["+"], "CTRL_EN", "up", 200); c.stub(p.pin["-"], "GND", "down", 200)
    p = c.V("Vref1", "VREF1", "GND", f"PWL(0 0 {t_step:g} 0 {t_step + 1e-6:g} {{VSTEP}})", x0 + 3700, y0)
    c.stub(p.pin["+"], "VREF1", "up", 200); c.stub(p.pin["-"], "GND", "down", 200)
    p = c.V("Vref2", "VREF2", "GND", "0", x0 + 4200, y0)
    c.stub(p.pin["+"], "VREF2", "up", 200); c.stub(p.pin["-"], "GND", "down", 200)
    # commanded duties: the DLL output while enabled, else 0.5 + the identification offsets
    # (RUN 1 baseline, 2 u_comm_1, 3 u_comm_2, 4 u_diff_1, 5 u_diff_2; DU = modal step)
    offs = {"DA1": "table(RUN, 1,0, 2,DU/2, 3,0, 4,DU/2, 5,0)",
            "DB1": "table(RUN, 1,0, 2,DU/2, 3,0, 4,-DU/2, 5,0)",
            "DA2": "table(RUN, 1,0, 2,0, 3,DU/2, 4,0, 5,DU/2)",
            "DB2": "table(RUN, 1,0, 2,0, 3,DU/2, 4,0, 5,-DU/2)"}
    for i, (dn, off) in enumerate(offs.items()):
        p = c.B(f"Bd{dn}", dn + "C", "GND", f"V=if(V(CTRL_EN)>0.5, V({dn}), 0.5+{off})", x0 + 500 * i, y0 - 3200)
        c.stub(p.pin["+"], dn + "C", "up", 200)
        c.stub(p.pin["-"], "GND", "down", 200)
    # the controller
    sym = ctrl_sym()
    p = c.DLL("Xc", sym, CTRL_INS, CTRL_OUTS, "0", "shuffler_ctrl_dll", x0 + 6000, y0 - 1400)
    for n in CTRL_INS:
        c.stub(p.pin[n], n, "left", 400)
    for n in CTRL_OUTS:
        c.stub(p.pin[n], n, "right", 400)
    c.stub(p.pin["GND"], "GND", "down", 200)
    c.sch.comment(x0, y0 + 900, "S9 closed loop: shuffler_ctrl_dll.dll = the firmware control stack (6_RTOS/ctrl_core) "
                               "with the firmware's sensor quantisation; duties -> HRTIM-style PWM comparators in the converters.")


CTRL_INS2 = CTRL_INS + ["KSCALE", "MSEL", "FILT", "FC", "NOISE", "SAMP", "KBERR", "FSWP", "VM1SRC", "VSTRP"]


def ctrl_sym2():
    w, h = 1600, 4400
    prims = [p_rect(-w // 2, h // 2, w // 2, -h // 2, "box")]
    pins = []
    for i, n in enumerate(CTRL_INS2):
        pins.append((n, -w // 2, h // 2 - 200 - 200 * i, 60, -40, 13, 145))
    for i, n in enumerate(CTRL_OUTS):
        pins.append((n, w // 2, h // 2 - 200 - 200 * i, -60, -40, 14, 146))
    pins.append(("GND", 0, -h // 2, 0, 60, 11, 147))
    return SymbolDef("shuffler_ctrl_dll2", "\u00d8(.DLL)", "control stack C-block with test inputs (2_Qspice/ctrl_dll/shuffler_ctrl_dll2)",
                     prims, pins, libfile=None, ref_pos=(0, h // 2 + 150), val_pos=(0, 0), extra_pos=(0, -h // 2 - 150),
                     text_just=0)


def ctrl_block2(c, x0, y0, t_en, t_step, offs, tests):
    """S10 control block: hall outputs (+ TMCS1126 500 kHz pole), ramps at TSW_CTRL, enable, VREF2 step of VSTEP2
    at t_step, duty override offsets `offs` (open loop), the test inputs `tests` {pin: B-source V= expression}
    and shuffler_ctrl_dll2."""
    for k, (leg, S) in enumerate(((("A", 0.1), ("B", -0.025)) * 2)):
        conv = 1 + k // 2
        hs = f"HS{leg}{conv}"
        if HALL_BW:
            raw = hs + "R"
            p = c.B(f"Bhs{leg}{conv}", raw, "GND", f"V=1.65+{S:g}*I(Vs{leg}{conv})", x0 + 500 * k, y0)
            c.stub(p.pin["+"], raw, "up", 200); c.stub(p.pin["-"], "GND", "down", 200)
            c.R(f"Rhs{leg}{conv}", raw, hs, "1k", x0 + 500 * k, y0 + 700)
            p = c.C(f"Chs{leg}{conv}", hs, "GND", f"{1 / (2 * 3.141592653589793 * HALL_BW * 1e3):.4g}", x0 + 500 * k + 250, y0 + 700)
            c.stub(p.pin["1"], hs, "up", 200); c.stub(p.pin["2"], "GND", "down", 200)
        else:
            p = c.B(f"Bhs{leg}{conv}", hs, "GND", f"V=1.65+{S:g}*I(Vs{leg}{conv})", x0 + 500 * k, y0)
            c.stub(p.pin["+"], hs, "up", 200); c.stub(p.pin["-"], "GND", "down", 200)
    tsw, tr = TSW_CTRL, TSW_CTRL - 2e-9
    p = c.V("Vrampa", "RAMPA", "GND", f"PULSE(0 1 0 {tr:.4g} 1n 1n {tsw:g})", x0 + 2200, y0)
    c.stub(p.pin["+"], "RAMPA", "up", 200); c.stub(p.pin["-"], "GND", "down", 200)
    p = c.V("Vrampb", "RAMPB", "GND", f"PULSE(0 1 {tsw / 2:g} {tr:.4g} 1n 1n {tsw:g})", x0 + 2700, y0)
    c.stub(p.pin["+"], "RAMPB", "up", 200); c.stub(p.pin["-"], "GND", "down", 200)
    p = c.V("Ven", "CTRL_EN", "GND", f"PWL(0 0 {t_en:g} 0 {t_en + 1e-6:g} 1)", x0 + 3200, y0)
    c.stub(p.pin["+"], "CTRL_EN", "up", 200); c.stub(p.pin["-"], "GND", "down", 200)
    p = c.V("Vref1", "VREF1", "GND", "0", x0 + 3700, y0)
    c.stub(p.pin["+"], "VREF1", "up", 200); c.stub(p.pin["-"], "GND", "down", 200)
    p = c.V("Vref2", "VREF2", "GND", f"PWL(0 0 {t_step:g} 0 {t_step + 1e-6:g} {{VSTEP2}})", x0 + 4200, y0)
    c.stub(p.pin["+"], "VREF2", "up", 200); c.stub(p.pin["-"], "GND", "down", 200)
    for i, (dn, off) in enumerate(offs.items()):
        p = c.B(f"Bd{dn}", dn + "C", "GND", f"V=if(V(CTRL_EN)>0.5, V({dn}), 0.5+{off})", x0 + 500 * i, y0 - 3200)
        c.stub(p.pin["+"], dn + "C", "up", 200); c.stub(p.pin["-"], "GND", "down", 200)
    for i, pin in enumerate(CTRL_INS2[10:]):
        p = c.B(f"Bt{pin}", pin, "GND", f"V={tests[pin]}", x0 + 2200 + 500 * i, y0 - 3200)
        c.stub(p.pin["+"], pin, "up", 200); c.stub(p.pin["-"], "GND", "down", 200)
    sym = ctrl_sym2()
    p = c.DLL("Xc", sym, CTRL_INS2, CTRL_OUTS, "0", "shuffler_ctrl_dll2", x0 + 8500, y0 - 1400)
    for n in CTRL_INS2:
        c.stub(p.pin[n], n, "left", 400)
    for n in CTRL_OUTS:
        c.stub(p.pin[n], n, "right", 400)
    c.stub(p.pin["GND"], "GND", "down", 200)
    c.sch.comment(x0, y0 + 1300, "S10: shuffler_ctrl_dll2.dll = firmware control stack (runtime gains) + test inputs "
                                "KSCALE MSEL FILT FC NOISE SAMP KBERR FSWP VM1SRC VSTRP (B-sources from .param)")


def bench_sources(c, x0, y0, ilim3_expr):
    """S10 bench: node Ek carries the NGE103 current limit of channel k in mA (nge_ch subcircuit)."""
    vals = (["1000", "1000"] if "IRR3" in ilim3_expr else ["ILIM1*1000", "ILIM2*1000"]) + [ilim3_expr]
    for i, v in enumerate(vals):
        p = c.B(f"BE{i+1}", f"E{i+1}", "GND", f"V={v}", x0 + 600 * i, y0)
        c.stub(p.pin["+"], f"E{i+1}", "up", 200)
        c.stub(p.pin["-"], "GND", "down", 200)


S10_SAVE = (".save V(PV1P) V(PV2P) V(PV3P) I(VsA1) I(VsB1) I(VsA2) I(VsB2) V(DA1) V(DB1) V(DA2) V(DB2) "
            "V(BETA) V(STRESS) V(RV1) V(RV2) V(IM1R) V(IM2R) I(Bload) I(Vi1) I(Vi2) I(Vi3) V(VREF2) V(HSA2) V(HSB2) V(SWA2)")


def s10_cl_measurements(c, ta, tstep, tb, tshade, tc, tend):
    """Closed loop: settled (ta..tstep), Vref2 step at tstep (overshoot, 98 % time), settled (tb..tshade),
    shade at tshade, settled (tc..tend); noise/limit-cycle std via AVG + RMS; peak phase currents."""
    vd1, vd2 = "V(PV1P,PV2P)-V(PV2P,PV3P)", "V(PV2P,PV3P)-V(PV3P)"
    ic1, ic2 = "I(VsA1)-I(VsB1)", "I(VsA2)-I(VsB2)"
    for tag, a, b in (("a", ta, tstep), ("b", tb, tshade), ("c", tc, tend)):
        for nm, ex in (("vd1", vd1), ("vd2", vd2), ("ic1", ic1), ("ic2", ic2), ("da1", "V(DA1)"), ("da2", "V(DA2)"),
                       ("sh1", "I(VsA1)+I(VsB1)"), ("sh2", "I(VsA2)+I(VsB2)")):
            c.measure(f".meas tran {nm}{tag} AVG {ex} FROM {a:g} TO {b:g}")
            c.measure(f".meas tran {nm}{tag}r RMS {ex} FROM {a:g} TO {b:g}")
    c.measure(f".meas tran vd2max MAX {vd2} FROM {tstep:g} TO {tshade:g}")
    c.measure(f".meas tran t98 WHEN {vd2}=1.96 RISE=1")
    for nm in ("VsA1", "VsB1", "VsA2", "VsB2"):
        c.measure(f".meas tran {nm.lower()}max MAX I({nm}) FROM {ta:g} TO {tend:g}")
        c.measure(f".meas tran {nm.lower()}min MIN I({nm}) FROM {ta:g} TO {tend:g}")
    c.measure(f".meas tran betamax MAX V(BETA) FROM {ta:g} TO {tend:g}")
    c.measure(f".meas tran stressmax MAX V(STRESS) FROM {ta:g} TO {tend:g}")
    c.measure(f".meas tran pout AVG V(PV1P)*I(Bload) FROM {tc:g} TO {tend:g}")
    for k in (1, 2, 3):
        c.measure(f".meas tran i{k}c AVG I(Vi{k}) FROM {tc:g} TO {tend:g}")


def ctrl_measurements(c, t0, t1, t2, t3):
    """Settled means before (t0..t1) and after (t2..t3) the Vref step, supervisor extrema, harvest."""
    for tag, a, b in (("", t0, t1), ("s", t2, t3)):
        c.measure(f".meas tran vd1{tag} AVG V(PV1P,PV2P)-V(PV2P,PV3P) FROM {a:g} TO {b:g}")
        c.measure(f".meas tran vd2{tag} AVG V(PV2P,PV3P)-V(PV3P) FROM {a:g} TO {b:g}")
        c.measure(f".meas tran vm1{tag} AVG V(PV1P,PV2P) FROM {a:g} TO {b:g}")
        c.measure(f".meas tran vm2{tag} AVG V(PV2P,PV3P) FROM {a:g} TO {b:g}")
        c.measure(f".meas tran vm3{tag} AVG V(PV3P) FROM {a:g} TO {b:g}")
        c.measure(f".meas tran ish1{tag} AVG I(VsA1)+I(VsB1) FROM {a:g} TO {b:g}")
        c.measure(f".meas tran ish2{tag} AVG I(VsA2)+I(VsB2) FROM {a:g} TO {b:g}")
        c.measure(f".meas tran idf1{tag} AVG I(VsA1)-I(VsB1) FROM {a:g} TO {b:g}")
        c.measure(f".meas tran idf2{tag} AVG I(VsA2)-I(VsB2) FROM {a:g} TO {b:g}")
        for d in ("DA1", "DB1", "DA2", "DB2"):
            c.measure(f".meas tran {d.lower()}{tag} AVG V({d}) FROM {a:g} TO {b:g}")
        c.measure(f".meas tran pout{tag} AVG V(PV1P)*I(Bload) FROM {a:g} TO {b:g}")
        c.measure(f".meas tran pref{tag} AVG V(R1P)*I(Bref) FROM {a:g} TO {b:g}")
    c.measure(".meas tran betamax MAX V(BETA)")
    c.measure(".meas tran stressmax MAX V(STRESS)")
    c.measure(".meas tran im1r AVG V(IM1R) FROM %g TO %g" % (t2, t3))
    c.measure(".meas tran im2r AVG V(IM2R) FROM %g TO %g" % (t2, t3))
    c.measure(".meas tran i1 AVG I(Vi1) FROM %g TO %g" % (t2, t3))
    c.measure(".meas tran i2 AVG I(Vi2) FROM %g TO %g" % (t2, t3))
    c.measure(".meas tran i3 AVG I(Vi3) FROM %g TO %g" % (t2, t3))


def pwm_nets(pos, leg, k):
    """(IN+, IN-) nets of the driver for FET `pos` (T/B) of `leg`: IN+ is its own PWM, IN- the complementary one."""
    hi, lo = f"PWM_{leg}H{k}", f"PWM_{leg}L{k}"
    return (hi, lo) if pos == "T" else (lo, hi)


def pulse_expr(pos, leg, k, logic=False):
    """PULSE(): 50 % duty minus dead time; leg B shifted by half a period; T on first, B on second half."""
    if PARAM_REG is not None:
        amp = pval("Vlogic", 3.3, "", "PWM logic level (NUCLEO)") if logic else pval("Vgdrive", VDRV, "", "ideal gate pulse amplitude")
        pval("Tsw", f"{TSW * 1e6:g}u", "", "switching period (5 us = 200 kHz)")
        pval("Tdead", f"{TDEAD * 1e9:g}n", "", "dead time between the two FETs of a leg")
        shift = " + ".join(x for x in (["Tsw/2"] if leg == "B" else []) + (["Tsw/2"] if pos == "B" else []))
        t0 = "{" + (shift if shift else "0") + "}"
        return f"PULSE(0 {amp} {t0} 5n 5n {{Tsw/2-Tdead}} {{Tsw}})"
    amp = 3.3 if logic else VDRV
    t0 = (TSW / 2 if leg == "B" else 0.0) + (TSW / 2 if pos == "B" else 0.0)
    ton = TSW / 2 - TDEAD
    return f"PULSE(0 {amp:g} {t0:.3e} 5n 5n {ton:.3e} {TSW:.3e})"


def lump_params(name, R, L):
    """'R=.. L=..' for a trace lump; in report mode as {R_name} {L_name} parameters."""
    src = LUMP.get(name, {}).get("from", "")
    return (f"R={pval('R_' + name, R, 'm', f'copper lump {name} (KiCad net {src})' if src else None, '.3g')} "
            f"L={pval('L_' + name, L, 'n', None, '.3g')}")


# ----------------------------------------------------------------------------- stages
def base_directives(c, tstop, tsave, maxstep, steps=True, case=1, loadsel=0):
    c.directive(f".param Rmpp={RMPP:.3f} Icc={ICC:g} CASE={case} LOADSEL={loadsel} VCV=70 RCV=0.05")
    c.directive(".option savepowers")
    c.directive(f".tran 0 {tstop:g} {tsave:g} {maxstep:g}")
    if steps:
        c.directive(".step param CASE list 1 2 3")
        c.directive(".step param LOADSEL list 0 1")


def irradiance_sources(c, x0, y0):
    for i in range(3):
        vals = [IRRADIANCE_CASES[cs][i] for cs in (1, 2, 3)]
        expr = f"V=table(CASE, 1,{vals[0]}, 2,{vals[1]}, 3,{vals[2]})"
        p = c.B(f"BE{i+1}", f"E{i+1}", "GND", expr, x0 + 600 * i, y0)
        c.stub(p.pin["+"], f"E{i+1}", "up", 200)
        c.stub(p.pin["-"], "GND", "down", 200)


def string_measurements(c, refstring=True, modules=True):
    c.measure(".meas tran vstr AVG V(PV1P)")
    c.measure(".meas tran istr AVG I(Bload)")
    c.measure(".meas tran pout AVG V(PV1P)*I(Bload)")
    if refstring:
        c.measure(".meas tran pref AVG V(R1P)*I(Bref)")
    if modules:
        for k, (a, b) in enumerate((("PV1P", "PV2P"), ("PV2P", "PV3P"), ("PV3P", "GND")), 1):
            vb = f"V({a},{b})" if b != "GND" else f"V({a})"
            c.measure(f".meas tran v{k} AVG {vb}")
            c.measure(f".meas tran i{k} AVG I(Vi{k})")
            c.measure(f".meas tran p{k} AVG {vb}*I(Vi{k})")
        if refstring:
            for k, (a, b) in enumerate((("R1P", "R2P"), ("R2P", "R3P"), ("R3P", "GND")), 1):
                vb = f"V({a},{b})" if b != "GND" else f"V({a})"
                c.measure(f".meas tran vr{k} AVG {vb}")
                c.measure(f".meas tran ir{k} AVG I(Vir{k})")


def converter_measurements(c, k, drive, paras, Bn):
    s = str(k)
    c.measure(f".meas tran ila{s} AVG I(VsA{s})")
    c.measure(f".meas tran ilb{s} AVG I(VsB{s})")
    c.measure(f".meas tran ilapp{s} PP I(VsA{s})")
    c.measure(f".meas tran ish{s} AVG I(VsA{s})+I(VsB{s})")
    c.measure(f".meas tran vswamax{s} MAX V(SWA{s},{Bn})")
    c.measure(f".meas tran vswamin{s} MIN V(SWA{s},{Bn})")
    c.measure(f".meas tran vswbmax{s} MAX V(SWB{s},{Bn})")
    for q in ("MTA", "MBA", "MTB", "MBB"):
        c.measure(f".meas tran p{q.lower()}{s} AVG P({q}{s})")
    c.measure(f".meas tran pconv{s} AVG P(MTA{s})+P(MBA{s})+P(MTB{s})+P(MBB{s})")
    if drive == "driver":
        c.measure(f".meas tran vgta{s} MAX V(gTA{s},SWA{s})")
        c.measure(f".meas tran vgtamin{s} MIN V(gTA{s},SWA{s})")
        c.measure(f".meas tran vboota{s} MIN V(BOOTA{s},SWA{s})")
        # saved window starts on a cycle boundary: the top gate's 1st rise precedes the bottom gate's 1st fall,
        # so take the 2nd rise (a negative result means the window did not start on a boundary; add Tsw)
        c.measure(f".meas tran tdead{s} TRIG V(gBA{s},{Bn})=6 FALL=1 TARG V(gTA{s},SWA{s})=6 RISE=2")


def build(stage):
    """Return a Circuit for the given stage id."""
    S = dict(string=True, cpv=False, bulk=False, conv=[], drive=None, paras=False, snub=False, full_meas=False)
    titles = {
        "S1": "S1 - PV string (3 x Aiko, Karmalkar-Haneefa) + bench loads; reference (unshuffled) string",
        "S2": "S2 - + module capacitance and the four 130 uF board capacitors",
        "S3": "S3 - + converter 1 power stage, ideal 12 V gate pulses (200 kHz, 50 %, 200 ns dead time)",
        "S4": "S4 - + converter 2 (both converters, 3 modules)",
        "S5": "S5 - 1ED3140 drivers with 10R/4R7 gate paths, 12 V rails, bootstrap supplies",
        "S6": "S6 - + PCB copper, package, capacitor ESL and cable parasitics (snubber/HF footprints present, not fitted)",
        "S7": "S7 - full baseline measurement set (same circuit as S6)",
        "S8": "S8 - snubber / HF decoupling design sweep (placeholder positions populated)",
        "S8b": "S8b - HF decoupling sweep (snubber fixed at 470 pF / 4.7 R)",
        "S9": "S9 - CLOSED LOOP: 150 W panels, drivers (S5 circuit), 100 kHz PWM, firmware control stack as a C-block DLL",
        "S9i": "S9i - IDENTIFICATION of the S9 plant: open loop, baseline + 4 modal duty steps (RUN 1..5) -> G -> M (qspice_ident.py)",
        "S10c": "S10c - BENCH CALIBRATION: NGE103 sources, DL3021 CV 70 V, 100 kHz, shuffler 1 off, shuffler 2 at D2 (13 Oct run)",
        "S10i": "S10i - IDENTIFICATION at 200 kHz on the bench operating point (RUN 1..5, DU) -> G200 -> M200",
        "S10": "S10 - CLOSED LOOP 200 kHz bench: MSEL x KSCALE grid, VREF2 step, shade step (shuffler_ctrl_dll2, comb sampling)",
        "S10n": "S10n - NOISE + FILTER A/B 200 kHz bench: bench-level sensor noise, IIR 2k / IIR 500 / MA4 / old sampling",
        "S10p": "S10p - CLOSED LOOP 200 kHz carpark: 3 x KAUSSP80, DL3021 CV, VREF2 step, shade step",
        "S10xb": "S10xb - MATRIX bench: FILT {IIR2k, MA4} x VM1SRC {INA, CV} x KBERR {1, 4} x KSCALE {0.3, 1}, noise on",
        "S10xp": "S10xp - MATRIX carpark 3 x KAUSSP80: FILT {IIR2k, MA4} x VM1SRC {INA, CV} x KBERR {1, 4} x KSCALE {0.3, 1}, noise on",
    }
    order = ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S8b"]
    global PV_SUB, FSW_CTRL, TSW_CTRL, S1OFF_PARAM, HALL_BW, CAP_IC
    PV_SUB = "pvmi_150w" if stage in ("S9", "S9i") else "pvmi_aiko"
    s10 = stage in S10_STAGES
    FSW_CTRL = S10_FSW.get(stage, 200e3) if s10 else 100e3
    TSW_CTRL = 1 / FSW_CTRL
    S1OFF_PARAM = "S1OFF" if stage == "S10c" else None
    HALL_BW = 500e3 if s10 else None
    if s10:
        vcv0 = 61.5 if stage in ("S10p", "S10xp") else 70.0
        CAP_IC = (22.4, 23.8, 23.8) if stage == "S10c" else (vcv0 / 3,) * 3
    else:
        CAP_IC = None
    if s10:
        PV_SUB = "pvmi_80w" if stage in ("S10p", "S10xp") else "nge_ch"
    if stage in ("S9", "S9i") or s10:
        stage_flags = dict(cpv=True, bulk=True, conv=[1, 2], drive="driver", paras=False, snub=False, full_meas=False)
        idx = order.index("S5")
    else:
        stage_flags = None
        idx = order.index(stage)
    if idx >= 1: S["cpv"] = S["bulk"] = True
    if idx >= 2: S["conv"] = [1]; S["drive"] = "ideal"
    if idx >= 3: S["conv"] = [1, 2]
    if idx >= 4: S["drive"] = "driver"
    if idx >= 5: S["paras"] = True; S["snub"] = True   # placeholder footprints present (1 pF = not fitted)
    if idx >= 6: S["full_meas"] = True
    if stage_flags:
        S.update(stage_flags)
    ctrl = stage in ("S9", "S9i") or s10

    c = Circuit(stage, titles[stage])
    # ---- geometry anchors
    Xs, Ys = 0, 0
    # main string with board rails
    pv_string(c, Xs, Ys, "", ["PV1P", "PV2P", "PV3P", "GND"], "Bload", S["cpv"], S["paras"], "")
    # reference string (no converter ever); it keeps the module capacitance so that a bypassed module
    # (12 A sink, shaded module) does not chatter at picosecond timesteps
    if not s10:
        pv_string(c, Xs - 5000, Ys, "r", ["R1P", "R2P", "R3P", "GND"], "Bref", True, False, "r")
        irradiance_sources(c, Xs - 5000, Ys - 10000)
    elif stage in ("S10p", "S10xp"):
        bench_sources(c, Xs - 5000, Ys - 10000, "if(time<TSHADE, IRR3, IRR3*SHADE)")
    else:
        bench_sources(c, Xs - 5000, Ys - 10000, "1000*if(time<TSHADE, ILIM3, ILIM3*SHADE)")
    if S["bulk"]:
        bulk_caps(c, Xs + 3000, Ys, S["paras"])
    conv_nets = {1: ("PV1P", "PV2P", "PV3P"), 2: ("PV2P", "PV3P", "GND")}
    for k in S["conv"]:
        T, M, B = conv_nets[k]
        converter(c, k, Xs + 8000, Ys - 4600 * (k - 1), T, M, B, S["drive"], S["paras"], S["snub"], ctrl=ctrl)
    if s10:
        modal = {"DA1": "table(RUN, 1,0, 2,DU/2, 3,0, 4,DU/2, 5,0)",
                 "DB1": "table(RUN, 1,0, 2,DU/2, 3,0, 4,-DU/2, 5,0)",
                 "DA2": "table(RUN, 1,0, 2,0, 3,DU/2, 4,0, 5,DU/2)",
                 "DB2": "table(RUN, 1,0, 2,0, 3,DU/2, 4,0, 5,-DU/2)"}
        if stage == "S10c":
            modal = {"DA1": "0", "DB1": "0", "DA2": "(D2-0.5)", "DB2": "(D2-0.5)"}
        tests = {n: n for n in CTRL_INS2[10:]}
        tests["FSWP"] = f"{FSW_CTRL:g}"
        if stage == "S10n":   # RUN 1 IIR 2k comb, 2 IIR 500 Hz comb, 3 MA4 comb, 4 IIR 2k old sampling, 5 = 1 with B hall x4
            tests["FILT"] = "table(RUN, 1,0, 2,0, 3,4, 4,0, 5,0)"
            tests["FC"] = "table(RUN, 1,2000, 2,500, 3,2000, 4,2000, 5,2000)"
            tests["SAMP"] = "table(RUN, 1,1, 2,1, 3,1, 4,2, 5,1)"
            tests["KBERR"] = "table(RUN, 1,1, 2,1, 3,1, 4,1, 5,4)"
        t_en = 0.5e-3 if stage in ("S10", "S10n", "S10p", "S10xb", "S10xp") else 1.0
        ctrl_block2(c, Xs + 8000, Ys - 12000, t_en=t_en, t_step=2e-3, offs=modal, tests=tests)
    elif ctrl:
        ctrl_block(c, Xs + 8000, Ys - 12000, t_en=(0.5e-3 if stage == "S9" else 1.0), t_step=3e-3)
    # ---- simulation control
    if stage == "S9":
        # one case (CASE: 1 uniform, 2 = module 2 at 600, 3 = module 3 at 400 W/m2), constant-current load
        # current-sink load (the resistor B-source stalls the solver at t=0 with this PV model; a sink above the
        # shaded string's capability collapses the string - keep Icc below it), 6 ms: open loop 0-0.5 ms, closed loop from 0.5 ms, Vref1 step at 3 ms
        # (no savepowers, 250 ns max step: the .qraw stays near 1 GB for the 6 ms run)
        c.directive(f".param Rmpp={3 * 18.28 / 8.207:.3f} Icc={ICC_150:g} CASE=2 LOADSEL=1 VSTEP=1 DU=0 RUN=1 VCV=70 RCV=0.05")
        c.directive(".tran 0 6m 0 250n")
    elif stage == "S9i":
        c.directive(f".param Rmpp={3 * 18.28 / 8.207:.3f} Icc={ICC_150:g} CASE=2 LOADSEL=1 VSTEP=0 DU=0.04 RUN=1 VCV=70 RCV=0.05")
        c.directive(".step param RUN list 1 2 3 4 5")
        c.directive(".tran 0 4m 2.5m 250n")
    elif s10:
        # common: bench NGE103 (VSET 25 V, ILIM*), DL3021 CV (LOADSEL 2: VCV through RCV), test-input defaults
        vcv = 61.5 if stage in ("S10p", "S10xp") else 70
        P = dict(LOADSEL=2, VCV=vcv, RCV=0.05, Rmpp=1, Icc=1,
                 VSET=25, RCLAMP=0.05, ILIM1=BENCH_ILIM[0], ILIM2=BENCH_ILIM[1], ILIM3=BENCH_ILIM[2],
                 IRR3=1000, SHADE=0.5, TSHADE="3m",
                 KSCALE=1, MSEL=0, FILT=0, FC=2000, NOISE=0, SAMP=1, KBERR=1, VM1SRC=0, VSTRP=vcv,
                 VSTEP2=2, DU=0, RUN=1, D2=0.5, S1OFF=0)
        P.update({"S10c": dict(S1OFF=1, TSHADE=1), "S10i": dict(DU=0.02, TSHADE=1),
                  "S10n": dict(NOISE=1, MSEL=2, KSCALE=1),
                  "S10xb": dict(NOISE=0.22), "S10xp": dict(NOISE=0.22), "S10p": dict(NOISE=0.22)}.get(stage, {}))
        items = [f"{k}={v:g}" if isinstance(v, (int, float)) else f"{k}={v}" for k, v in P.items()]
        for i in range(0, len(items), 8):
            c.directive(".param " + " ".join(items[i:i + 8]))
        c.directive(S10_SAVE)
        # no DC operating point (it hangs with the PSU clamps + CV load + static switch state): start from the
        # string split the bench showed (13 Oct: 22.4 / 23.8 / 23.8 V at CV 70 V) and let the switching settle
        v3 = 23.8 if stage == "S10c" else vcv / 3
        c.directive(f".ic V(PV1P)={vcv:g} V(PV2P)={2 * v3:g} V(PV3P)={v3:g}")
        if stage == "S10c":
            c.directive(".step param D2 list 0.49 0.5 0.51")
            c.directive(".tran 0 3m 0 250n uic")
        elif stage == "S10i":
            c.directive(".step param RUN list 1 2 3 4 5")
            c.directive(".tran 0 3m 0 125n uic")
        elif stage == "S10":
            c.directive(".step param MSEL list 0 2")
            c.directive(".step param KSCALE list 0.3 1")
            c.directive(".tran 0 4m 0 125n uic")
        elif stage == "S10n":
            c.directive(".step param RUN list 1 2 3 4 5")
            c.directive(".tran 0 4m 0 125n uic")
        elif stage == "S10p":
            c.directive(".step param KSCALE list 0.3 1")
            c.directive(".tran 0 4m 0 125n uic")
        elif stage in ("S10xb", "S10xp"):
            c.directive(".step param FILT list 0 4")
            c.directive(".step param VM1SRC list 0 1")
            c.directive(".step param KBERR list 1 4")
            c.directive(".step param KSCALE list 0.3 1")
            c.directive(".tran 0 4m 0 125n uic")
    elif stage in ("S1", "S2"):
        base_directives(c, 2e-3, 1.9e-3, 1e-6)
    elif stage in ("S3", "S4", "S5"):
        base_directives(c, 2.5e-3, 2.4e-3, 20e-9)
    elif stage in ("S6", "S7"):
        base_directives(c, 2.5e-3, 2.45e-3, 10e-9)
        # snubber / HF-cap footprints exist on the board but are not populated: 1 pF keeps the
        # positions in the netlist (and, as a side effect, keeps the solver away from a stall)
        c.directive(".param Csn=1p Rsn=4.7 Chf=1p")
    elif stage == "S8":
        base_directives(c, 2.5e-3, 2.45e-3, 5e-9, steps=False, case=2, loadsel=0)
        c.directive(".param Chf=1p")
        c.directive(".step param Csn list 1p 220p 470p 1n 2.2n")
        c.directive(".step param Rsn list 2.2 4.7 10")
    elif stage == "S8b":
        base_directives(c, 2.5e-3, 2.45e-3, 5e-9, steps=False, case=2, loadsel=0)
        c.directive(".param Csn=470p Rsn=4.7")
        c.directive(".step param Chf list 1p 100n 470n 1u")
    # ---- measurements
    if stage in ("S10c", "S10i"):
        a, b = (2.5e-3, 3e-3) if stage == "S10c" else (2e-3, 3e-3)
        c.measure(f".meas tran y1 AVG V(PV1P,PV2P)-V(PV2P,PV3P) FROM {a:g} TO {b:g}")
        c.measure(f".meas tran y2 AVG V(PV2P,PV3P)-V(PV3P) FROM {a:g} TO {b:g}")
        c.measure(f".meas tran y3 AVG I(VsA1)-I(VsB1) FROM {a:g} TO {b:g}")
        c.measure(f".meas tran y4 AVG I(VsA2)-I(VsB2) FROM {a:g} TO {b:g}")
        c.measure(f".meas tran ish1 AVG I(VsA1)+I(VsB1) FROM {a:g} TO {b:g}")
        c.measure(f".meas tran ish2 AVG I(VsA2)+I(VsB2) FROM {a:g} TO {b:g}")
        for k, ex in ((1, "V(PV1P,PV2P)"), (2, "V(PV2P,PV3P)"), (3, "V(PV3P)")):
            c.measure(f".meas tran vm{k} AVG {ex} FROM {a:g} TO {b:g}")
            c.measure(f".meas tran i{k} AVG I(Vi{k}) FROM {a:g} TO {b:g}")
        c.measure(f".meas tran vstr AVG V(PV1P) FROM {a:g} TO {b:g}")
        c.measure(f".meas tran istr AVG I(Bload) FROM {a:g} TO {b:g}")
        for nm in ("VsA2", "VsB2"):
            c.measure(f".meas tran {nm.lower()}avg AVG I({nm}) FROM {a:g} TO {b:g}")
            c.measure(f".meas tran {nm.lower()}max MAX I({nm}) FROM {b - 20e-6:g} TO {b:g}")
            c.measure(f".meas tran {nm.lower()}min MIN I({nm}) FROM {b - 20e-6:g} TO {b:g}")
            c.measure(f".meas tran {nm.lower()}rms RMS I({nm}) FROM {a:g} TO {b:g}")
    elif stage in ("S10", "S10n", "S10p", "S10xb", "S10xp"):
        s10_cl_measurements(c, 1.5e-3, 2e-3, 2.6e-3, 3e-3, 3.6e-3, 4e-3)
    elif stage == "S9i":
        # settled plant outputs in the control stack's conventions: y = [VM1-VM2, VM2-VM3, ic1, ic2],
        # ic = ILA + ILB with ILB positive OUT of the midpoint = I(VsA) - I(VsB).
        # Saved data starts at 2.5 ms and is time-rebased to 0: the window 0.5..1.5 ms = 3..4 ms of the run.
        c.measure(".meas tran y1 AVG V(PV1P,PV2P)-V(PV2P,PV3P) FROM 0.5m TO 1.5m")
        c.measure(".meas tran y2 AVG V(PV2P,PV3P)-V(PV3P) FROM 0.5m TO 1.5m")
        c.measure(".meas tran y3 AVG I(VsA1)-I(VsB1) FROM 0.5m TO 1.5m")
        c.measure(".meas tran y4 AVG I(VsA2)-I(VsB2) FROM 0.5m TO 1.5m")
        c.measure(".meas tran ish1 AVG I(VsA1)+I(VsB1) FROM 0.5m TO 1.5m")
        c.measure(".meas tran ish2 AVG I(VsA2)+I(VsB2) FROM 0.5m TO 1.5m")
        c.measure(".meas tran pout AVG V(PV1P)*I(Bload) FROM 0.5m TO 1.5m")
    elif ctrl and not s10:
        ctrl_measurements(c, 2e-3, 2.9e-3, 4.5e-3, 6e-3)
    else:
        string_measurements(c, refstring=True, modules=True)
    for k in S["conv"]:
        Bn = ("PV3P" if k == 1 else "GND") if not S["paras"] else f"B{k}"
        if not ctrl:
            converter_measurements(c, k, S["drive"], S["paras"], Bn)
    if S["snub"]:
        for k in S["conv"]:
            s = str(k)
            c.measure(f".meas tran psnta{s} AVG P(RsnTA{s})")
            c.measure(f".meas tran psnba{s} AVG P(RsnBA{s})")
            c.measure(f".meas tran phfa{s} AVG P(ChfA{s})")
    c.sch.comment(-9000, 1800, "Shuffler PCB baseline - " + c.title, size=1.5)
    c.sch.comment(-9000, 1500, "Generated by gen_shuffler.py; node names match the netlist. GND = string bottom = SPICE node 0.")
    return c


# ----------------------------------------------------------------------------- verification
def parse_netlist(text):
    """element -> tuple of nodes (lowercase, ground = 0), ignoring dot commands."""
    els = {}
    for ln in text.splitlines():
        t = ln.strip()
        if not t or t.startswith("*") or t.startswith(".") or t.startswith("//"):
            continue
        toks = t.split()
        ref = toks[0].lower()
        first = ref[0]
        npins = {"r": 2, "c": 2, "l": 2, "v": 2, "i": 2, "b": 2, "d": 2, "m": 4}.get(first)
        if npins is None and first != "x":
            print(f"   (netlist parser: skipping unknown line: {t[:80]})")
            continue
        if first == "x":
            # nodes are everything between the ref and the subckt name (last token without '=')
            body = toks[1:]
            i = len(body) - 1
            while "=" in body[i]:
                i -= 1
            nodes = body[:i]
        else:
            nodes = toks[1:1 + npins]
        els[ref] = tuple(n.lower() for n in nodes)
    return els


def parse_check(base):
    """Run QSPICE64 on a copy of the netlist with the .step lines removed and the .tran cut to 20 ns:
    a few seconds, and it reports undefined parameters, bad values or missing models that a
    connectivity check cannot see."""
    src = open(base + ".cir", "rb").read().decode("cp1252").splitlines()
    notes, tmp = [], base + "_parsecheck.cir"
    for pick in (0, -1):                       # first, then last value of every stepped list
        picked = {}
        for line in src:
            tok = line.strip().split()
            if len(tok) > 4 and tok[0].lower() == ".step" and tok[1].lower() == "param" and tok[3].lower() == "list":
                picked[tok[2].upper()] = tok[4:][pick]
        lines, defined = [], set()
        for line in src:
            low = line.strip().lower()
            if low.startswith(".step"):
                continue
            if low.startswith(".tran"):
                line = ".tran 0 20n 0 10n"
            elif low.startswith(".param"):     # a stepped parameter keeps one definition: the picked value
                tok = line.strip().split()
                for i, t in enumerate(tok[1:], 1):
                    name = t.split("=")[0].upper()
                    if "=" in t and name in picked:
                        tok[i] = t.split("=")[0] + "=" + picked[name]
                        defined.add(name)
                line = " ".join(tok)
            lines.append(line)
        extra = [f".param {k}={v}" for k, v in picked.items() if k not in defined]
        end_i = next((i for i, l in enumerate(lines) if l.strip().lower() == ".end"), len(lines))
        lines[end_i:end_i] = extra
        with open(tmp, "wb") as f:
            f.write(chr(10).join(lines).encode("cp1252"))
        try:
            r = subprocess.run([os.path.join(QSPICE_DIR, "QSPICE64.exe"), os.path.basename(tmp)],
                               cwd=os.path.dirname(tmp), timeout=180, capture_output=True)
            text = (r.stdout + r.stderr).decode("cp1252", "replace")
        except subprocess.TimeoutExpired:
            text = "Error: QSPICE64 did not finish the 20 ns parse run within 180 s"
        finally:
            for ext in ("_parsecheck.cir", "_parsecheck.qraw"):
                if os.path.exists(base + ext):
                    os.remove(base + ext)
        # netlist problems fail the check; operating-point notes (Gmin / source stepping, skipbp) are reported only,
        # the full runs show the same lines and recover by skipping the bias point
        bad = [l.strip() for l in text.splitlines() if re.search(r"error|missing|unexpected|undefined|unknown", l, re.I)]
        if bad:
            return False, f"QSPICE parse ({'first' if pick == 0 else 'last'} step values): " + " | ".join(bad)
        notes += [l.strip() for l in text.splitlines() if re.search(r"warning", l, re.I)]
    return True, "QSPICE parses it" + (f" ({len(notes)} op-point notes: " + " | ".join(notes)[:160] + ")" if notes else "")


def verify(base):
    cir = open(base + ".cir", "rb").read().decode("cp1252")
    tmp = base + ".qux.cir"
    if os.path.exists(tmp):
        os.remove(tmp)
    # QUX writes <name>.cir next to the schematic: netlist a copy to avoid clobbering ours
    import shutil
    qcopy = base + "_quxcheck.qsch"
    shutil.copy(base + ".qsch", qcopy)
    r = subprocess.run([os.path.join(QSPICE_DIR, "QUX.exe"), "-Netlist", qcopy], timeout=60, capture_output=True)
    qcir = base + "_quxcheck.cir"
    if not os.path.exists(qcir):
        os.remove(qcopy)
        return False, "QUX produced no netlist: " + (r.stdout + r.stderr).decode("cp1252", "replace").strip()
    qux = parse_netlist(open(qcir, "rb").read().decode("cp1252"))
    mine = parse_netlist(cir)
    os.remove(qcopy)
    os.remove(qcir)
    # QUX names unlabeled nets N01, N02 ... ; accept any consistent one-to-one renaming
    problems, q2c, c2q = [], {}, {}
    for ref, nodes in mine.items():
        if ref not in qux:
            problems.append(f"{ref}: missing in QUX netlist")
            continue
        qn = qux[ref]
        if len(qn) != len(nodes):
            problems.append(f"{ref}: pin count cir {nodes} != qsch {qn}")
            continue
        for a, b in zip(qn, nodes):
            if q2c.setdefault(a, b) != b or c2q.setdefault(b, a) != a:
                problems.append(f"{ref}: node {b} in .cir is {a} in .qsch but mapping conflicts (cir {nodes} / qsch {qn})")
    for ref in qux:
        if ref not in mine:
            problems.append(f"{ref}: only in QUX netlist")
    if len(problems) > 12:
        problems = problems[:12] + [f"... {len(problems) - 12} more (later ones are usually a cascade of the first)"]
    if problems:
        return False, "\n".join(problems)
    ok, msg = parse_check(base)
    return ok, f"{len(mine)} elements match ({len(q2c)} nets); {msg}"


# ----------------------------------------------------------------------------- report layout (single file)
REPORT_DIR = os.path.normpath(os.path.join(HERE, ".."))          # Version 0/Qspice, next to the earlier sims
REPORT_NAME = "Shuffler_PCB_Baseline"

PARAM_GROUPS = [
    ("Switching and gate drive", ["Tsw", "Tdead", "Vlogic", "Vreg", "Vgdrive", "Ron", "Roff", "Rboot", "Rgate"]),
    ("Bench loads and irradiance case", ["Rmpp", "Icc", "CASE", "LOADSEL"]),
    ("Module and cable", ["Cpv", "Rcab", "Lcab"]),
    ("Board capacitors, package, sensor", ["ESR130", "ESL130", "Ld_pkg", "Ls_pkg", "Rtmcs", "Ltmcs"]),
    ("Placeholder footprints (1 pF / 4.7 R = not fitted)", ["Csn", "Rsn", "Chf"]),
]
# lumps in the converter block, in reading order for the parameter list
LUMP_ORDER = ["T1", "M1", "B1", "SWA1", "SWB1", "LA1", "LB1", "gTA1", "gBA1", "gTB1", "gBB1",
              "T2", "M2", "B2", "SWA2", "SWB2", "LA2", "LB2", "gTA2", "gBA2", "gTB2", "gBB2"]


def build_report():
    """One report-grade sheet with the complete model (= stage S7 electrically), every value a .param."""
    global PARAM_REG
    PARAM_REG = {}
    c = Circuit("REPORT", "Shuffler PCB (Version 0) - Qspice baseline, full model with parasitics")
    # loads and case selection first so they head the parameter block
    pval("Rmpp", RMPP, "", "resistor load near the 3-module MPP at 1000 W/m2 (ohm)", ".3f")
    pval("Icc", ICC, "", "constant-current bench load (A), ramped up over the first 200 us; keep below ~11 A with one converter")
    pval("CASE", 1, "", "irradiance pattern 1..3 (stepped by the .step line)")
    pval("LOADSEL", 0, "", "0 = resistor load, 1 = current sink (stepped)")
    pval("Csn", "1p", "", "RC snubber C across each FET (C73-C84 positions); 1p = footprint not fitted, sweep to size it")
    pval("Rsn", 4.7, "", "RC snubber R (R49-R52 positions); only matters once Csn is real")
    pval("Chf", "1p", "", "HF decoupling per capacitor, 3 in parallel per converter rail (C91-C96); 1p = not fitted")
    # ---- title block
    c.sch.comment(-7000, 3000, "SHUFFLER PCB (Version 0) - Qspice baseline: complete model with parasitics", size=2)
    c.sch.comment(-7000, 2650, "Three Aiko modules, two two-phase converters (STD45N10F7 + ERUC23-4R1K + TMCS1126), 1ED3140 gate drive with bootstrap, copper / package / capacitor / cable parasitics.")
    c.sch.comment(-7000, 2500, "Open loop: 50 % duty, 200 kHz, 200 ns dead time, legs 180 deg apart. Every parasitic and setting is a .param in the PARAMETERS block at the bottom left - edit values there.")
    c.sch.comment(-7000, 2350, "Node names: PV1P / PV2P / PV3P / GND = string nodes (KiCad PV1+, PV2+, PV3+, GND). T1 / M1 / B1 = converter-1 rails behind the copper lumps, SWA1 / SWB1 = switch nodes,")
    c.sch.comment(-7000, 2200, "gTA1 gBA1 gTB1 gBB1 = gates, BOOTA1 / BOOTB1 = bootstrap nodes, VREG1 = 12 V rail, PWM_AH1 .. = NUCLEO outputs. Same for converter 2 with suffix 2. Generated by PCB_Baseline/gen_shuffler.py --report.")
    # ---- strings and capacitors
    Xs, Ys = 0, 0
    c.sch.comment(-6900, 550, "REFERENCE STRING - same modules and load, never gets a converter (comparison only)", size=1.2)
    pv_string(c, -6000, Ys, "r", ["R1P", "R2P", "R3P", "GND"], "Bref", True, False, "r")
    c.sch.comment(-900, 550, "PV STRING - 3 x Aiko modules (Karmalkar-Haneefa model)", size=1.2)
    c.sch.comment(-900, 400, "bypass diode and Cpv per module, 1.5 m of cable per lead (Xcab lumps)")
    pv_string(c, Xs, Ys, "", ["PV1P", "PV2P", "PV3P", "GND"], "Bload", True, True, "")
    c.sch.comment(2900, 550, "BOARD CAPACITORS C1-C4 (130 uF hybrid polymer + ESL)", size=1.2)
    bulk_caps(c, 3200, Ys, True)
    c.sch.comment(-900, -9200, "IRRADIANCE per module in W/m2 (E1..E3), pattern chosen by CASE: 1 = all 1000, 2 = PV2 at 600, 3 = PV3 at 400", size=1.2)
    irradiance_sources(c, Xs, Ys - 9800)
    # ---- converters
    conv_nets = {1: ("PV1P", "PV2P", "PV3P"), 2: ("PV2P", "PV3P", "GND")}
    X0 = 8000
    for k in (1, 2):
        Y0 = Ys - 4600 * (k - 1)
        T, M, B = conv_nets[k]
        c.sch.comment(X0 - 3600, Y0 + 950, f"CONVERTER {k} - rails {T} (T{k}) / {M} (M{k} = inductor common node) / {B} (B{k}); 12 V gate-drive rail VREG{k} referenced to {B}", size=1.2)
        c.sch.comment(X0 - 3600, Y0 + 800, "left: 12 V rail, bootstrap, drivers for leg A | middle: leg A, coupled inductor + hall sensor paths, leg B (mirrored) | right: leg B drivers and bootstrap, HF-cap footprints")
        converter(c, k, X0, Y0, T, M, B, "driver", True, True)
    # ---- parameters block (netlist + sheet)
    xp, yp = -7000, -10600
    c.sch.comment(xp, yp + 250, "PARAMETERS - edit values here (units: m = milli, u = micro, n = nano, p = pico)", size=1.4)
    placed = set()
    y = yp
    lump_names = []
    for nm in LUMP_ORDER:
        lump_names += [f"R_{nm}", f"L_{nm}"]
    groups = list(PARAM_GROUPS) + [("Board copper lumps from pcb_parasitics.py: rails T/M/B, switch nodes SWA/SWB, inductor-to-sensor LA/LB, gates g.. (0.5 x free-space inductance)", lump_names)]
    for title, names in groups:
        c.sch.comment(xp, y, "* " + title)
        y -= 150
        for n in names:
            if n not in PARAM_REG or n in placed:
                continue
            val, cm = PARAM_REG[n]
            line = f".param {n}={val}"
            c.directive(line)
            c.sch.directive(xp, y, line)
            if cm:
                c.sch.comment(xp + 2600, y, cm)
            placed.add(n)
            y -= 150
        y -= 80
    for n in PARAM_REG:               # anything not grouped
        if n not in placed:
            val, cm = PARAM_REG[n]
            line = f".param {n}={val}"
            c.directive(line)
            c.sch.directive(xp, y, line)
            if cm:
                c.sch.comment(xp + 2600, y, cm)
            y -= 150
    # ---- simulation block
    xs, ys = 2200, yp
    c.sch.comment(xs, ys + 250, "SIMULATION", size=1.4)
    sim = [".option savepowers", ".tran 0 2.5m 2.45m 10n",
           ".step param CASE list 1 2 3", ".step param LOADSEL list 0 1"]
    notes = ["P(name) traces for every element (MOSFET losses)",
             "2.5 ms run, the last 50 us saved with <= 10 ns steps; the modules and 130 uF caps settle in ~1 ms",
             "irradiance patterns (see E1..E3 sources)", "resistor load, then current sink"]
    y = ys
    c.sch.comment(xs, y, "Models (PV module, coupled inductor, MOSFET estimate, driver, sensor, trace lump) come from shuffler_models.lib")
    y -= 150
    c.sch.comment(xs, y, "via the symbols' library attribute - keep that file next to this schematic; edit it to swap in the Qspice FET-modeller MOSFET.")
    y -= 200
    for line, note in zip(sim, notes):
        c.directive(line)
        c.sch.directive(xs, y, line)
        c.sch.comment(xs + 2600, y, note)
        y -= 150
    y -= 100
    for txt in ["Snubber / HF-cap design sweep: fix CASE and LOADSEL (delete the two .step lines above) and add e.g.",
                "   .step param Csn list 1p 220p 470p 1n 2.2n    and/or    .step param Chf list 1p 100n 470n 1u",
                "Waveforms worth plotting: V(SWA1,B1) switch node, V(gTA1,SWA1) gate, I(VsA1) I(VsB1) inductor currents,",
                "   I(Vi1) I(Vi2) I(Vi3) module currents, V(BOOTA1,SWA1) bootstrap, P(MTA1) FET loss, I(Bload)*V(PV1P) string power.",
                "Results of the .meas lines appear in the QPOST output after the run (or run PCB_Baseline/run_baseline.py)."]:
        c.sch.comment(xs, y, txt)
        y -= 150
    # ---- measurements (two columns)
    string_measurements(c, refstring=True, modules=True)
    for k in (1, 2):
        converter_measurements(c, k, "driver", True, f"B{k}")
        s = str(k)
        c.measure(f".meas tran psnta{s} AVG P(RsnTA{s})")
        c.measure(f".meas tran psnba{s} AVG P(RsnBA{s})")
        c.measure(f".meas tran phfa{s} AVG P(ChfA{s})")
    xm, ym = 9600, yp
    c.sch.comment(xm, ym + 250, "MEASUREMENTS - averages / extremes over the saved window, one value per step", size=1.4)
    half = (len(c.meas) + 1) // 2
    for i, m in enumerate(c.meas):
        col = 0 if i < half else 1
        c.sch.directive(xm + col * 5600, ym - 150 * (i - col * half), m)
    # ---- write
    os.makedirs(REPORT_DIR, exist_ok=True)
    base = os.path.join(REPORT_DIR, REPORT_NAME)
    c.write(base, place_directives=False)
    import shutil
    shutil.copy(os.path.join(HERE, LIB), os.path.join(REPORT_DIR, LIB))
    PARAM_REG = None
    return c, base


def main():
    os.makedirs(STAGES, exist_ok=True)
    write_lib()
    if "--report" in sys.argv:
        c, base = build_report()
        msg = f"wrote {base}.qsch / .cir ({len(c.lines)} elements, {len(c.meas)} .meas, {len(c.directives)} directives)"
        if "--verify" in sys.argv:
            ok, detail = verify(base)
            msg += " | verify: " + ("OK - " if ok else "MISMATCH\n") + detail
        print(msg)
        return
    import shutil
    shutil.copy(os.path.join(HERE, LIB), os.path.join(STAGES, LIB))
    stages = sys.argv[1:] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else \
        ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S8b"]
    do_verify = "--verify" in sys.argv
    stages = [s for s in stages if not s.startswith("--")]
    for st in stages:
        c = build(st)
        base = os.path.join(STAGES, st)
        c.write(base)
        msg = f"wrote {st}.qsch / {st}.cir ({len(c.lines)} elements, {len(c.meas)} .meas)"
        if do_verify:
            ok, detail = verify(base)
            msg += " | verify: " + ("OK - " if ok else "MISMATCH\n") + detail
        print(msg)


if __name__ == "__main__":
    main()
