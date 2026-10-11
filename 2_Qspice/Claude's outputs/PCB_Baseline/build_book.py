"""
build_book.py - assembles build_book.html (the Lego-style walkthrough) from the stage files,
parasitics.json and the simulation results in results/.  Pure Python, no packages.

  python build_book.py
"""

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
OUT = os.path.join(HERE, "build_book.html")

STEP_NAMES = ["1000/1000/1000, resistor", "1000/600/1000, resistor", "1000/1000/400, resistor",
              "1000/1000/1000, 10 A sink", "1000/600/1000, 10 A sink", "1000/1000/400, 10 A sink"]
MEAS_LABEL = {
    "vstr": "string voltage V", "istr": "string current A", "pout": "string power W (shuffled)",
    "pref": "reference string power W (no converters)", "v1": "V module 1", "v2": "V module 2", "v3": "V module 3",
    "i1": "I module 1", "i2": "I module 2", "i3": "I module 3", "p1": "P module 1 W", "p2": "P module 2 W", "p3": "P module 3 W",
    "vr1": "V ref module 1", "vr2": "V ref module 2", "vr3": "V ref module 3", "ir1": "I ref module 1", "ir2": "I ref module 2", "ir3": "I ref module 3",
    "ila1": "conv 1 leg A inductor current, avg A", "ilb1": "conv 1 leg B inductor current, avg A", "ilapp1": "conv 1 leg A ripple, pk-pk A",
    "ish1": "conv 1 current into PV2+ midpoint, A", "vswamax1": "conv 1 SWA peak above its bottom rail, V", "vswamin1": "conv 1 SWA minimum, V",
    "vswbmax1": "conv 1 SWB peak, V", "pmta1": "P Q top A W", "pmba1": "P Q bottom A W", "pmtb1": "P Q top B W", "pmbb1": "P Q bottom B W",
    "pconv1": "conv 1 MOSFET loss W", "vgta1": "conv 1 top-A gate peak Vgs", "vgtamin1": "conv 1 top-A gate min Vgs", "vboota1": "conv 1 bootstrap A minimum V",
    "tdead1": "conv 1 measured dead time s",
    "ila2": "conv 2 leg A inductor current, avg A", "ilb2": "conv 2 leg B inductor current, avg A", "ilapp2": "conv 2 leg A ripple, pk-pk A",
    "ish2": "conv 2 current into PV3+ midpoint, A", "vswamax2": "conv 2 SWA peak above its bottom rail, V", "vswamin2": "conv 2 SWA minimum, V",
    "vswbmax2": "conv 2 SWB peak, V", "pmta2": "P Q top A (conv 2) W", "pmba2": "P Q bottom A (conv 2) W", "pmtb2": "P Q top B (conv 2) W", "pmbb2": "P Q bottom B (conv 2) W",
    "pconv2": "conv 2 MOSFET loss W", "vgta2": "conv 2 top-A gate peak Vgs", "vgtamin2": "conv 2 top-A gate min Vgs", "vboota2": "conv 2 bootstrap A minimum V",
    "tdead2": "conv 2 measured dead time s",
    "psnta1": "snubber power, Q top A conv 1, W", "psnba1": "snubber power, Q bottom A conv 1, W", "phfa1": "HF cap power leg A conv 1, W",
    "psnta2": "snubber power, Q top A conv 2, W", "psnba2": "snubber power, Q bottom A conv 2, W", "phfa2": "HF cap power leg A conv 2, W",
}


def load_meas(stage):
    p = os.path.join(RES, stage + ".meas.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def load_svg(name):
    p = os.path.join(RES, name + ".svg")
    if not os.path.exists(p):
        return None
    s = open(p, encoding="utf-8").read()
    s = re.sub(r'<svg ', '<svg class="plot" role="img" ', s, count=1)
    s = re.sub(r'<rect x="0" y="0" width="\d+" height="\d+" fill="white"/>', '', s, count=1)
    return s


def fmt(v, digits=4):
    if v is None:
        return "–"
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    if abs(v) < 1e-3 and v != 0:
        return f"{v:.3g}"
    return f"{v:.{digits}g}"


def table(rows, head, cls="num"):
    h = "".join(f"<th>{c}</th>" for c in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="tablewrap"><table class="{cls}"><thead><tr>{h}</tr></thead><tbody>{body}</tbody></table></div>'


def meas_table(meas, keys, cols=range(6)):
    if not meas:
        return '<p class="notrun">Results not generated yet – run <code>python run_baseline.py</code>.</p>'
    head = ["measurement"] + [STEP_NAMES[i] for i in cols]
    rows = []
    for k in keys:
        if k not in meas:
            continue
        vals = list(meas[k])
        if k.startswith("tdead"):
            # measured between consecutive edges; a negative value means the window's first top-gate rise
            # preceded the first bottom-gate fall, i.e. one switching period has to be added back
            vals = [(v + 5e-6 if v < 0 else v) for v in vals]
            rows.append([MEAS_LABEL.get(k, k).replace(" s", " ns")] + [f"{vals[i] * 1e9:.0f}" if i < len(vals) else "–" for i in cols])
            continue
        rows.append([MEAS_LABEL.get(k, k)] + [fmt(vals[i]) if i < len(vals) else "–" for i in cols])
    return table(rows, head)


def compare_table(a, b, keys, names=("single sheet", "stage S7"), cols=range(6)):
    """Two result sets side by side, one pair of rows per measurement."""
    if not a or not b:
        return '<p class="notrun">Not simulated yet: run <code>python run_baseline.py REPORT</code>.</p>'
    head = ["measurement", "file"] + [STEP_NAMES[i] for i in cols]
    rows = []
    for k in keys:
        if k not in a or k not in b:
            continue
        for nm, m in zip(names, (a, b)):
            label = MEAS_LABEL.get(k, k) if nm == names[0] else ""
            rows.append([label, nm] + [fmt(m[k][i]) if i < len(m[k]) else "–" for i in cols])
    return table(rows, head)


def plots(*names):
    out = []
    for n in names:
        s = load_svg(n)
        if s:
            out.append(f'<figure class="fig">{s}<figcaption>{n.replace("_", " ")}</figcaption></figure>')
    return "".join(out)


def parasitics_table():
    p = os.path.join(HERE, "parasitics.json")
    if not os.path.exists(p):
        return ""
    d = json.load(open(p, encoding="utf-8"))
    rows = []
    for name, l in d["lumps"].items():
        rows.append([f"<code>{name}</code>", l["from"], fmt(l["R_mOhm"], 3), fmt(l["L_nH"], 3)])
    comp = d["components"]
    crow = [[k.replace("_", " "), fmt(v, 3)] for k, v in comp.items()]
    return (table(rows, ["lump", "KiCad net", "R (mΩ)", "L (nH)"]) +
            "<p class='muted'>Component and cable ballparks used alongside the copper lumps:</p>" +
            table(crow, ["item", "value"]))


def s8_tables():
    m = load_meas("S8")
    mb = load_meas("S8b")
    out = []
    if m and "vswamax1" in m:
        csn = ["1 pF (none)", "220 pF", "470 pF", "1 nF", "2.2 nF"]
        rsn = ["2.2 Ω", "4.7 Ω", "10 Ω"]
        rows = []
        for j, r in enumerate(rsn):
            for i, c in enumerate(csn):
                idx = j * len(csn) + i
                if idx < len(m["vswamax1"]):
                    rows.append([c, r, fmt(m["vswamax1"][idx]), fmt(m["vswamin1"][idx]), fmt(m["psnta1"][idx], 3),
                                 fmt(m["pconv1"][idx], 3)])
        out.append("<h4>Snubber sweep (converter 1, 1000/600/1000 W/m², resistor load)</h4>")
        out.append(table(rows, ["Csn", "Rsn", "SWA peak above rail V", "SWA min V", "snubber power per FET W", "MOSFET loss conv 1 W"]))
    if mb and "vswamax1" in mb:
        chf = ["none (1 pF)", "3 × 100 nF", "3 × 470 nF", "3 × 1 µF"]
        rows = [[chf[i], fmt(mb["vswamax1"][i]), fmt(mb["vswamin1"][i]), fmt(mb["phfa1"][i], 3), fmt(mb["pconv1"][i], 3)]
                for i in range(min(len(chf), len(mb["vswamax1"])))]
        out.append("<h4>HF decoupling sweep (rail-to-rail per leg, snubber 470 pF / 4.7 Ω)</h4>")
        out.append(table(rows, ["Chf per leg", "SWA peak above rail V", "SWA min V", "HF cap power W", "MOSFET loss conv 1 W"]))
    if not out:
        return '<p class="notrun">Sweep results not generated yet.</p>'
    return "".join(out)


def stage_counts():
    counts = {}
    for f in os.listdir(os.path.join(HERE, "stages")):
        if f.endswith(".cir") and "quxcheck" not in f:
            txt = open(os.path.join(HERE, "stages", f), "rb").read().decode("cp1252")
            n = sum(1 for l in txt.splitlines() if l and l[0] not in ".*" and not l.startswith("//"))
            counts[f[:-4]] = n
    return counts


# ----------------------------------------------------------------------------- schematic figures
# Each figure is a crop of the real stage file drawn by qsch_render.py (sheet units, y up):
# (stage, (x0, y0, x1, y1), scale px/unit, previous stage for "added parts" highlighting or an explicit
#  list of refs, hide_texts, caption)
REPORT_QSCH = os.path.normpath(os.path.join(HERE, "..", "Shuffler_PCB_Baseline.qsch"))

FIGS = {
    "FILE": [("REPORT", (-7400, -10400, 23600, 3300), 0.026, [], True,
              "The circuit part of the sheet, labels hidden: reference string, PV string with cable lumps, board capacitors and irradiance sources on the left, converter 1 above converter 2 on the right (drivers and bootstrap on their outer sides, HF-cap footprints far right). The title block sits above this, the PARAMETERS, SIMULATION and MEASUREMENTS text blocks below it."),
             ("REPORT", (3400, -3300, 13600, 1100), 0.11, [], False,
              "Converter 1, left two thirds: 12 V rail, bootstrap and drivers for leg A; leg A with package inductances, snubber positions and the switch-node copper lump; the coupled inductor with the two sensor paths. Leg B mirrors it on the right."),
             ("REPORT", (-7200, -14400, 2000, -10100), 0.105, [], False,
              "Top of the PARAMETERS block: one .param per line with a comment; the copper lumps continue below it, one R/L pair per KiCad net."),
             ("REPORT", (2000, -12500, 9560, -10100), 0.105, [], False,
              "SIMULATION block: options, .tran, the two .step lines, and notes on the snubber sweep and which waveforms to plot. The MEASUREMENTS block to its right lists the 57 .meas lines whose results fill the tables on this page.")],
    "BOARD": [("S4", (-6200, -10600, 18800, 1300), 0.032, [], True,
               "The complete stage-4 sheet: reference string (left), main string with C1–C4, converter 1 (top right) and converter 2 (below it). Labels hidden at this scale.")],
    "S1": [("S1", (-700, -8700, 2700, 400), 0.12, None, False,
            "Main string: three modules, sense sources, bypass diodes, bench load. The reference string is an identical copy on nets R1P, R2P, R3P.")],
    "S2": [("S2", (-700, -8700, 3900, 400), 0.105, "S1", False,
            "Board capacitors C1–C4 beside the string; Cpv across each module.")],
    "S3": [("S3", (8800, -3000, 16600, 900), 0.1, "S2", False, "Converter 1 power stage between PV1P and PV3P, common node into PV2P."),
           ("S3", (6800, -3000, 9300, 100), 0.16, "S2", False, "Ideal gate pulse sources for leg A (leg B has the mirror image on the right of the block).")],
    "S4": [("S4", (8800, -7600, 16600, -3700), 0.1, "S3", False, "Converter 2, one module lower: PV2P / PV3P / GND.")],
    "S5": [("S5", (4100, -3600, 10000, 400), 0.125, "S4", False, "Leg A: the two 1ED3140 drivers with 10 R / 4R7 paths, bootstrap diode and capacitors, the 12 V rail and the PWM sources."),
           ("S5", (14600, -2800, 21800, 400), 0.1, "S4", False, "Leg B side (mirrored).")],
    "S6": [("S6", (-700, -3000, 2600, 400), 0.15, "S5", False, "One module with its two cable lumps between the board net and the module terminals."),
           ("S6", (7000, -3200, 11900, 900), 0.125, "S5", False, "Leg A with rail, package, gate, switch-node and sensor-path lumps.")],
    "S8": [("S8", (9900, -2700, 11600, -150), 0.22, ["RsnTA1", "CsnTA1", "RsnBA1", "CsnBA1"], False, "Leg A snubber positions."),
           ("S8", (21400, -1800, 23600, 400), 0.2, ["ChfA1", "LhfA1", "ChfB1", "LhfB1"], False, "HF capacitor positions.")],
}


def figures(key):
    import qsch_render as qr
    out = []
    for stage, crop, scale, prev, hide, caption in FIGS[key]:
        qsch = REPORT_QSCH if stage == "REPORT" else os.path.join(HERE, "stages", stage + ".qsch")
        if not os.path.exists(qsch):
            continue
        if isinstance(prev, list):
            hl = prev
        elif prev is None:
            hl = qr.added_refs(os.path.join(HERE, "stages", stage + ".cir"), None)
        else:
            hl = qr.added_refs(os.path.join(HERE, "stages", stage + ".cir"), os.path.join(HERE, "stages", prev + ".cir"))
        svg = qr.render(qsch, crop, scale, highlight=hl, hide_texts=hide)
        os.makedirs(os.path.join(RES, "fig"), exist_ok=True)
        with open(os.path.join(RES, "fig", f"{key}_{len(out) + 1}.svg"), "w", encoding="utf-8") as f:
            f.write(svg)
        out.append(f'<figure class="schem">{svg}<figcaption>{caption}</figcaption></figure>')
    return "".join(out)


def build():
    S1, S3, S4, S5, S6, S7 = (load_meas(s) for s in ("S1", "S3", "S4", "S5", "S6", "S7"))
    REPORT = load_meas("REPORT")
    counts = stage_counts()

    def delta(m, i):
        if not m or "pout" not in m or "pref" not in m:
            return "–"
        return f"{m['pout'][i] - m['pref'][i]:+.0f} W"

    html = TEMPLATE
    subs = {
        "S1_TABLE": meas_table(S1, ["vstr", "istr", "pout", "v1", "v2", "v3", "i1", "i2", "i3"]),
        "S1_PLOTS": plots("S1_module_currents"),
        "S3_TABLE": meas_table(S3, ["pout", "pref", "ish1", "ila1", "ilapp1", "v1", "v2", "v3", "i1", "i2", "i3", "vswamax1", "vswamin1", "pconv1"]),
        "S3_PLOTS": plots("S3_inductor_currents", "S3_switch_node", "S3_module_currents"),
        "S3_DELTA_R": delta(S3, 1), "S3_DELTA_CC": delta(S3, 4),
        "S4_TABLE": meas_table(S4, ["pout", "pref", "ish1", "ish2", "v1", "v2", "v3", "i1", "i2", "i3", "pconv1", "pconv2"]),
        "S4_PLOTS": plots("S4_inductor_currents", "S4_module_currents"),
        "S4_DELTA_R2": delta(S4, 1), "S4_DELTA_R3": delta(S4, 2), "S4_DELTA_CC2": delta(S4, 4), "S4_DELTA_CC3": delta(S4, 5),
        "S5_TABLE": meas_table(S5, ["tdead1", "vgta1", "vgtamin1", "vboota1", "pout", "pref", "ish1", "ish2", "pconv1", "pconv2"], cols=[1, 4]),
        "S5_PLOTS": plots("S5_gate_drive", "S5_bootstrap", "S5_switch_node"),
        "S6_TABLE": meas_table(S6, ["vswamax1", "vswamin1", "vswamax2", "pconv1", "pconv2", "pout", "pref"], cols=[0, 1, 2]),
        "S6_PLOTS": plots("S6_switch_node", "S6_gate_drive", "S6_fet_power"),
        "S6_LUMPS": parasitics_table(),
        "S7_TABLE": meas_table(S7, list(S7.keys()) if S7 else []),
        "S7_PLOTS": plots("S7_switch_node", "S7_switch_node_2", "S7_inductor_currents", "S7_module_currents", "S7_fet_power"),
        "S8_TABLES": s8_tables(),
        "S8_PLOTS": plots("S8_switch_node"),
        "FILE_TABLE": compare_table(REPORT, S7, ["pout", "pref", "ish1", "ish2", "vswamax1", "vswamin1", "vgta1", "pconv1", "pconv2"]),
    }
    for k in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"):
        subs[f"N_{k}"] = str(counts.get(k, "?"))
    for k in FIGS:
        subs[f"FIG_{k}"] = figures(k)
    for k, v in subs.items():
        html = html.replace("{{" + k + "}}", v)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("wrote", OUT, len(html), "bytes")


TEMPLATE = r"""<title>Shuffler Build Book</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700;12..96,800&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{
  --ground:#f2f5f3; --surface:#ffffff; --surface2:#e9efec; --ink:#15201b; --muted:#5b6b63; --line:#d3dcd7;
  --copper:#b5652a; --copper-soft:#f3e3d6; --mask:#1f6b46; --mask-soft:#dcefe4; --cell:#1b2d55; --cell-soft:#e1e7f4;
  --warn:#b4420f; --warn-soft:#fbe6dc; --ok:#2d7a4a; --plotbg:#ffffff;
  --display:"Bricolage Grotesque","IBM Plex Sans",system-ui,sans-serif;
  --body:"IBM Plex Sans",system-ui,sans-serif; --mono:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;
  color-scheme:light;
}
@media (prefers-color-scheme:dark){ :root:not([data-theme="light"]){
  --ground:#0f1613; --surface:#161f1b; --surface2:#1d2823; --ink:#e7ede9; --muted:#9fb0a7; --line:#2b3933;
  --copper:#e0894a; --copper-soft:#3a2617; --mask:#4fb783; --mask-soft:#173226; --cell:#9fb4e6; --cell-soft:#1c2740;
  --warn:#f0925f; --warn-soft:#3b2116; --ok:#63c48a; --plotbg:#f5f7f6; color-scheme:dark; } }
:root[data-theme="dark"]{
  --ground:#0f1613; --surface:#161f1b; --surface2:#1d2823; --ink:#e7ede9; --muted:#9fb0a7; --line:#2b3933;
  --copper:#e0894a; --copper-soft:#3a2617; --mask:#4fb783; --mask-soft:#173226; --cell:#9fb4e6; --cell-soft:#1c2740;
  --warn:#f0925f; --warn-soft:#3b2116; --ok:#63c48a; --plotbg:#f5f7f6; color-scheme:dark; }

*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font-family:var(--body);font-size:16px;line-height:1.55;
  padding-block:0 64px;padding-inline:clamp(16px,4vw,40px)}
a{color:var(--mask)} a:focus-visible,button:focus-visible{outline:2px solid var(--copper);outline-offset:2px}
h1,h2,h3,h4{font-family:var(--display);text-wrap:balance;line-height:1.1;margin:0}
h1{font-size:clamp(34px,6vw,58px);font-weight:800;letter-spacing:-.01em}
h2{font-size:clamp(24px,3.2vw,32px);font-weight:700}
h3{font-size:19px;font-weight:700;margin-top:28px}
h4{font-size:16px;font-weight:600;margin-top:18px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;font-family:var(--body)}
p{max-width:68ch} li{max-width:68ch}
code,kbd{font-family:var(--mono);font-size:.92em;background:var(--surface2);padding:1px 5px;border-radius:3px}
pre{font-family:var(--mono);font-size:14px;background:var(--surface2);padding:14px 16px;border-radius:6px;overflow-x:auto;max-width:100%}
.muted{color:var(--muted)}
.eyebrow{font-family:var(--mono);font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--copper);margin-bottom:10px}

.top{display:grid;grid-template-columns:1fr;gap:20px;padding-block:44px 28px;border-bottom:1px solid var(--line);margin-bottom:8px}
.top p.lede{font-size:18px;max-width:60ch;color:var(--ink)}
.facts{display:flex;flex-wrap:wrap;gap:10px 28px;font-family:var(--mono);font-size:13px;color:var(--muted)}
.facts b{color:var(--ink);font-weight:500}

.frame{display:grid;grid-template-columns:200px minmax(0,1fr);gap:40px;align-items:start}
@media (max-width:860px){.frame{grid-template-columns:1fr}.rail{position:static !important}}
.rail{position:sticky;top:env(safe-area-inset-top,0px);padding-top:28px;font-size:14px}
.rail ol{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:2px}
.rail a{display:flex;gap:10px;align-items:baseline;padding:6px 8px;border-radius:4px;color:var(--ink);text-decoration:none}
.rail a:hover{background:var(--surface2)}
.rail .n{font-family:var(--mono);font-size:12px;color:var(--copper);min-width:22px}
.rail .aux{margin-top:14px;padding-top:12px;border-top:1px solid var(--line)}

section.stage{padding-block:44px 30px;border-bottom:1px solid var(--line)}
.stagehead{display:grid;grid-template-columns:auto 1fr;gap:20px;align-items:start}
.brick{width:64px;height:64px;border-radius:6px;background:var(--copper);color:#fff;display:grid;place-items:center;
  font-family:var(--display);font-weight:800;font-size:30px;position:relative;box-shadow:inset 0 -6px 0 rgba(0,0,0,.18)}
.brick::before{content:"";position:absolute;top:-8px;left:18px;width:28px;height:10px;border-radius:3px 3px 0 0;background:var(--copper);filter:brightness(1.12)}
.stagehead .adds{color:var(--muted);margin-top:6px;max-width:66ch}
.stagehead .elements{font-family:var(--mono);font-size:12px;color:var(--muted);margin-top:8px}

.duo{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:28px;margin-top:22px;align-items:start}
@media (max-width:760px){.duo{grid-template-columns:1fr}}
.parts table{width:100%;border-collapse:collapse;font-size:14px}
.parts th,.parts td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);vertical-align:top}
.parts th{font-family:var(--body);font-weight:600;color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.06em}
.parts td:first-child{font-family:var(--mono);font-size:13px;white-space:nowrap}
.parts td:last-child{font-family:var(--mono);font-size:13px}

/* schematic figures are drawn from the stage files on a fixed light "paper" so they read the same in both themes */
figure.schem{margin:0 0 14px;background:#fbfcfb;border:1px solid var(--line);border-radius:6px;padding:10px 10px 4px}
figure.schem svg{width:100%;height:auto;display:block;max-height:900px}
figure.schem figcaption{font-family:var(--mono);font-size:12px;color:#555;padding:6px 2px 4px;line-height:1.4}
.legend{display:flex;gap:16px;font-size:12px;color:var(--muted);margin-top:2px;font-family:var(--mono)}
.legend i{display:inline-block;width:18px;height:0;border-top:2.2px solid var(--copper);vertical-align:middle;margin-right:6px}
.legend i.o{border-color:var(--muted);border-top-width:1.5px}

ol.steps{padding-left:22px;display:flex;flex-direction:column;gap:8px;margin:12px 0 0}
ol.steps li::marker{font-family:var(--mono);color:var(--copper)}

.expect{margin-top:26px;padding:18px 20px;border-radius:6px;background:var(--surface);border:1px solid var(--line);border-left:4px solid var(--mask)}
.expect h4{margin-top:0;color:var(--mask)}
.tablewrap{overflow-x:auto;max-width:100%;margin-top:10px}
table.num{border-collapse:collapse;font-size:13px;font-family:var(--mono);font-variant-numeric:tabular-nums;min-width:100%}
table.num th,table.num td{padding:6px 10px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
table.num th:first-child,table.num td:first-child{text-align:left;font-family:var(--body);white-space:normal;min-width:180px}
table.num th{font-weight:600;color:var(--muted);font-size:12px;vertical-align:bottom}
.figs{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px;margin-top:14px}
figure.fig{margin:0;background:var(--plotbg);border:1px solid var(--line);border-radius:6px;padding:6px 6px 2px}
figure.fig svg{width:100%;height:auto;display:block}
figure.fig figcaption{font-family:var(--mono);font-size:12px;color:#555;padding:4px 6px 6px}
.notrun{color:var(--muted);font-style:italic}

.callout{margin-top:16px;padding:14px 16px;border-radius:6px;background:var(--cell-soft);border:1px solid var(--line);max-width:72ch}
.callout.warn{background:var(--warn-soft)}
.callout b{font-weight:600}
.chip{display:inline-block;font-family:var(--mono);font-size:11px;letter-spacing:.06em;text-transform:uppercase;padding:2px 8px;border-radius:999px;margin-right:8px;vertical-align:middle}
.chip.warn{background:var(--warn-soft);color:var(--warn)} .chip.note{background:var(--cell-soft);color:var(--cell)} .chip.ok{background:var(--mask-soft);color:var(--mask)}
.findings{display:flex;flex-direction:column;gap:14px;margin-top:18px}
.finding{padding:14px 16px;border:1px solid var(--line);border-radius:6px;background:var(--surface)}
.finding p{margin:6px 0 0}
.map table.num th,.map table.num td{text-align:left;white-space:normal;font-family:var(--body)}
.map table.num td:first-child{font-family:var(--mono)}
</style>

<header class="top">
  <div>
    <div class="eyebrow">Version 0 shuffler PCB · Qspice baseline</div>
    <h1>Shuffler Build Book</h1>
  </div>
  <p class="lede">Eight bricks, one model. Each stage adds a physical part of the board to the Qspice schematic and
  tells you what the simulation should show before you move on. Every stage is also a runnable file in
  <code>stages/</code>, so you can open any of them in Qspice and compare.</p>
  <div class="facts">
    <span><b>3</b> Aiko modules</span><span><b>2</b> two-phase converters</span><span><b>200 kHz</b> · 50 % · 200 ns dead time</span>
    <span><b>loads</b> 8.15 Ω resistor or 10 A sink</span><span><b>irradiance</b> ≥ 400 W/m²</span>
  </div>
</header>

<div class="frame">
<nav class="rail" aria-label="Stages">
  <ol>
    <li><a href="#board"><span class="n">→</span>What you are building</a></li>
    <li><a href="#file"><span class="n">1</span>The single-sheet file</a></li>
    <li><a href="#s1"><span class="n">S1</span>PV string and loads</a></li>
    <li><a href="#s2"><span class="n">S2</span>Capacitors</a></li>
    <li><a href="#s3"><span class="n">S3</span>Converter 1</a></li>
    <li><a href="#s4"><span class="n">S4</span>Converter 2</a></li>
    <li><a href="#s5"><span class="n">S5</span>Gate drivers</a></li>
    <li><a href="#s6"><span class="n">S6</span>Parasitics</a></li>
    <li><a href="#s7"><span class="n">S7</span>Baseline table</a></li>
    <li><a href="#s8"><span class="n">S8</span>Snubber sweep</a></li>
  </ol>
  <div class="aux"><ol>
    <li><a href="#findings"><span class="n">!</span>Findings</a></li>
    <li><a href="#run"><span class="n">$</span>Run it</a></li>
  </ol></div>
</nav>

<main>
<section class="stage" id="board">
  <h2>What you are building</h2>
  <p>The board sits across a three-module string. Converter 1 spans modules 1 and 2 and pushes current into
  the PV1/PV2 junction (KiCad net <code>PV2+</code>); converter 2 spans modules 2 and 3 and feeds the PV2/PV3
  junction (<code>PV3+</code>). Each converter is two half-bridges 180° apart sharing an inverse-coupled
  inductor, so at 50 % duty it behaves as a low-impedance voltage equaliser between its two modules.</p>
  {{FIG_BOARD}}
  <h3>How the model names things</h3>
  <p>Node names are the same in the schematic and the netlist, so <code>V(SWA1)</code> means the same thing everywhere.
  The string bottom is the SPICE ground (label <code>GND</code>).</p>
  <div class="map tablewrap"><table class="num">
    <thead><tr><th>model node</th><th>KiCad net</th><th>board</th></tr></thead><tbody>
    <tr><td>PV1P / PV2P / PV3P / GND</td><td>PV1+ / PV2+ / PV3+ / GND</td><td>XT60 string terminals; C1–C4 across the modules</td></tr>
    <tr><td>SWA1, SWB1 (SWA2, SWB2)</td><td>/Shuffle Converter 1/M_T_Aph_S, M_T_Bph_S</td><td>half-bridge switch nodes, inductor pins 4 and 3</td></tr>
    <tr><td>LA2_1, LB2_1</td><td>/Shuffle Converter 1/L_Aph2, L_Bph2</td><td>inductor pins 1 and 2 into the TMCS1126 sensors</td></tr>
    <tr><td>gTA1, gBA1, gTB1, gBB1</td><td>M_T_Aph_G, M_B_Aph_G, M_T_Bph_G, M_B_Bph_G</td><td>MOSFET gates (Q1–Q4 on converter 1, Q5–Q8 on converter 2)</td></tr>
    <tr><td>PWM_AH1, PWM_AL1, PWM_BH1, PWM_BL1</td><td>S1_A_H, S1_A_L, S1_B_H, S1_B_L</td><td>NUCLEO timer outputs into the 1ED3140 IN+/IN− pairs</td></tr>
    <tr><td>VREG1, BOOTA1, BOOTB1</td><td>Vreg_Output, Net-(D8-K) …</td><td>12 V from the Würth module; bootstrap nodes above each switch node</td></tr>
    <tr><td>MTA1, MBA1, MTB1, MBB1</td><td>Q1, Q2, Q3, Q4</td><td>top/bottom of leg A and leg B (STD45N10F7)</td></tr>
  </tbody></table></div>
</section>

<section class="stage" id="file">
  <h2>The single-sheet file</h2>
  <p>Everything the stages build up to is also one Qspice sheet: <code>Version 0/Qspice/Shuffler_PCB_Baseline.qsch</code>,
  with <code>shuffler_models.lib</code> next to it. It is electrically identical to stage 7 (same 177 netlist elements, same
  57 measurements) but laid out by block, the way a hand-drawn schematic reads: title block, reference string, PV string,
  board capacitors and irradiance sources on the left; converter 1 and converter 2 on the right; PARAMETERS, SIMULATION and
  MEASUREMENTS along the bottom. Every parasitic and every setting is a <code>.param</code> in the PARAMETERS block, so the
  symbols on the sheet carry names such as <code>{Ld_pkg}</code> or <code>{Rsn}</code> and the sheet is edited in one place.</p>
  {{FIG_FILE}}
  <h3>Editing it</h3>
  <div class="tablewrap"><table class="num">
    <thead><tr><th>to change</th><th>where</th></tr></thead><tbody>
    <tr><td>switching period, dead time, logic level, 12 V rail, gate and bootstrap resistors</td><td>PARAMETERS, first group: Tsw, Tdead, Vlogic, Vreg, Ron, Roff, Rboot</td></tr>
    <tr><td>bench load and irradiance pattern</td><td>Rmpp, Icc, CASE, LOADSEL; the two <code>.step</code> lines in SIMULATION sweep CASE 1–3 and LOADSEL 0–1, delete them to run a single case</td></tr>
    <tr><td>module capacitance, cable, capacitor ESR / ESL, package leads, sensor conductor</td><td>Cpv, Rcab, Lcab, ESR130, ESL130, Ld_pkg, Ls_pkg, Rtmcs, Ltmcs</td></tr>
    <tr><td>snubber and HF-capacitor footprints</td><td>Csn, Rsn, Chf (1 pF = not fitted); sweep them with <code>.step param Csn list …</code> as the SIMULATION notes show</td></tr>
    <tr><td>board copper</td><td>R_T1 … L_gBB2, one R / L pair per KiCad net; or rerun <code>pcb_parasitics.py</code> and regenerate</td></tr>
    <tr><td>MOSFET model</td><td>the <code>.model STD45N10F7</code> line in <code>shuffler_models.lib</code>: paste the FET-modeller line in its place, the symbols keep working</td></tr>
    <tr><td>driver, PV module, inductor, sensor, trace models</td><td>the <code>.subckt</code> blocks in the same library (pvmi, ERUC23-4R1K, ED3140, TMCS1126, trace)</td></tr>
  </tbody></table></div>
  <p>Hand edits and the generator do not mix: <code>python gen_shuffler.py --report --verify</code> rewrites the sheet from
  <code>gen_shuffler.py</code> and <code>parasitics.json</code>. Either edit the sheet and keep it under a new name, or change
  the generator and regenerate. <code>--verify</code> netlists the schematic with QUX, compares it with the generated netlist
  and has QSPICE64 parse it, so a broken edit of the generator is caught before a run. After a run the measurements are in
  QPOST's output, or in <code>results/REPORT.meas.json</code> from <code>python run_baseline.py REPORT</code>.</p>
  <h3>Check against stage 7</h3>
  <p>The sheet simulated on its own, next to the stage-7 numbers it must reproduce.</p>
  {{FILE_TABLE}}
</section>

<section class="stage" id="s1">
  <div class="stagehead"><div class="brick">1</div><div>
    <h2>PV string and the two bench loads</h2>
    <p class="adds">Three Aiko modules in series with one lumped bypass diode each, a current sense source per module,
    the behavioural bench load, and an identical <em>reference string</em> that never gets a converter. Everything
    later is compared with that reference.</p>
    <div class="elements">{{N_S1}} netlist elements · stages/S1.qsch</div></div></div>
  <div class="duo">
    <div class="parts"><table><thead><tr><th>ref</th><th>part</th><th>Qspice value / attributes</th></tr></thead><tbody>
      <tr><td>Xpv1..3</td><td>PV module, Karmalkar–Haneefa explicit model</td><td>pvmi_aiko (E pin = irradiance in W/m²)</td></tr>
      <tr><td>BE1..3</td><td>irradiance sources</td><td>V=table(CASE, 1,1000, 2,1000, 3,1000) …</td></tr>
      <tr><td>Dbp1..3</td><td>bypass diode (one per module)</td><td>dbypass</td></tr>
      <tr><td>Vi1..3</td><td>0 V current sense, + on the module side</td><td>0</td></tr>
      <tr><td>Bload</td><td>bench load</td><td>I=if(LOADSEL&lt;0.5, V(PV1P)/Rmpp, Icc)</td></tr>
      <tr><td>Xpvr1..3, Bref</td><td>reference string (no converters)</td><td>same as above, nets R1P R2P R3P</td></tr>
    </tbody></table></div>
    <div>{{FIG_S1}}
    <div class="legend"><span><i></i>added in this stage</span><span><i class="o"></i>already placed</span></div></div>
  </div>
  <h3>Place it in Qspice</h3>
  <ol class="steps">
    <li>Add <code>.lib shuffler_models.lib</code> as a directive; the library holds every model used in this book.</li>
    <li>Place three <code>pvmi_aiko</code> boxes in series between labels <code>PV1P</code>, <code>PV2P</code>, <code>PV3P</code> and ground <code>GND</code>. Each E pin gets its own label <code>E1</code>…<code>E3</code>.</li>
    <li>Drive E1–E3 from behavioural sources with <code>V=table(CASE, …)</code> so one <code>.step param CASE list 1 2 3</code> sweeps the irradiance patterns.</li>
    <li>Put a 0 V source in series with every module anode, + towards the module: <code>I(Vi1)</code> is then the module current.</li>
    <li>Load: one behavioural current source <code>I=if(LOADSEL&lt;0.5, V(PV1P)/Rmpp, Icc)</code> with <code>.param Rmpp=8.148 Icc=10</code> and <code>.step param LOADSEL list 0 1</code>.</li>
    <li>Copy the string to nets <code>R1P R2P R3P</code> with its own load <code>Bref</code>: the unshuffled reference.</li>
    <li><code>.tran 0 2m 1.9m 1u</code>, <code>.option savepowers</code>, and the <code>.meas</code> lines listed in <code>stages/S1.cir</code>.</li>
  </ol>
  <div class="expect"><h4>What you should see</h4>
    <p>At 1000 W/m² and the 8.15 Ω load the string sits on the maximum power point: about 115 V, 14.2 A, 1633 W
    (three times 38.4 V × 14.2 A). Shade the middle module to 600 W/m² and the plain string bypasses it: its
    voltage goes to −0.4 V (the diode) and the string drops to about 900 W. With the 10 A sink the same
    thing happens at 10 A. Shuffled and reference strings are identical here, which is the point.</p>
    {{S1_TABLE}}
    <div class="figs">{{S1_PLOTS}}</div>
  </div>
</section>

<section class="stage" id="s2">
  <div class="stagehead"><div class="brick">2</div><div>
    <h2>Capacitors that are actually on the board</h2>
    <p class="adds">The four 130 µF hybrid-polymer capacitors (C1 across module 1, C2 and C3 across module 2, C4 across
    module 3) and a 10 nF terminal capacitance per PV module. Nothing else: the RC snubber and HF-cap footprints are
    placeholders until stage 8.</p>
    <div class="elements">{{N_S2}} netlist elements · stages/S2.qsch</div></div></div>
  <div class="duo">
    <div class="parts"><table><thead><tr><th>ref</th><th>part</th><th>Qspice value / attributes</th></tr></thead><tbody>
      <tr><td>C1..C4</td><td>TDK B40910A0137M000, 130 µF hybrid polymer</td><td>130u RSER=28m</td></tr>
      <tr><td>Cpv1..3</td><td>module terminal capacitance (ballpark)</td><td>10n RSER=0.1</td></tr>
    </tbody></table></div>
    <div>{{FIG_S2}}
    <div class="legend"><span><i></i>added in this stage</span><span><i class="o"></i>already placed</span></div></div>
  </div>
  <h3>Place it in Qspice</h3>
  <ol class="steps">
    <li>C1 between <code>PV1P</code> and <code>PV2P</code>; C2 and C3 both between <code>PV2P</code> and <code>PV3P</code>; C4 between <code>PV3P</code> and <code>GND</code>. Give each the <code>RSER=28m</code> attribute (second text line of the symbol).</li>
    <li>Cpv across each module's own terminals.</li>
  </ol>
  <div class="expect"><h4>What you should see</h4>
    <p>The same DC numbers as S1. The capacitors only add a settling time of a few hundred microseconds, which is why
    every later stage waits 2.4 ms before measuring.</p>
  </div>
</section>

<section class="stage" id="s3">
  <div class="stagehead"><div class="brick">3</div><div>
    <h2>Converter 1 power stage, ideal gate pulses</h2>
    <p class="adds">Two half-bridges of STD45N10F7 between <code>PV1P</code> and <code>PV3P</code>, the ERUC23-4R1K coupled
    inductor from the two switch nodes, the TMCS1126 conductor paths, and the common node into <code>PV2P</code>.
    Gates are driven by ideal 12 V pulses through 4.7 Ω so that only the power stage is on trial.</p>
    <div class="elements">{{N_S3}} netlist elements · stages/S3.qsch</div></div></div>
  <div class="duo">
    <div class="parts"><table><thead><tr><th>ref</th><th>part</th><th>Qspice value / attributes</th></tr></thead><tbody>
      <tr><td>MTA1 MBA1 MTB1 MBB1</td><td>STD45N10F7 (Q1–Q4 in KiCad)</td><td>STD45N10F7 (VDMOS estimate in the lib)</td></tr>
      <tr><td>XL1</td><td>TDK ERUC23-4R1K coupled inductor</td><td>ERUC23-4R1K — pins 1,2 = sensor side, 3,4 = switch nodes</td></tr>
      <tr><td>XsA1 XsB1</td><td>TMCS1126B4 conductor path</td><td>TMCS1126 RSH=0.7m LSH=0.5n</td></tr>
      <tr><td>VsA1 VsB1</td><td>0 V sense, + on the inductor side</td><td>0</td></tr>
      <tr><td>RgTA1 …</td><td>gate resistor (stand-in)</td><td>4.7</td></tr>
      <tr><td>VgTA1 …</td><td>ideal gate pulse, referenced to the FET source</td><td>PULSE(0 12 t0 5n 5n 2.3u 5u)</td></tr>
    </tbody></table></div>
    <div>{{FIG_S3}}
    <div class="legend"><span><i></i>added in this stage</span><span><i class="o"></i>already placed</span></div></div>
  </div>
  <h3>Place it in Qspice</h3>
  <ol class="steps">
    <li>Leg A: NMOS <code>MTA1</code> drain on <code>PV1P</code>, source on <code>SWA1</code>; <code>MBA1</code> drain on <code>SWA1</code>, source on <code>PV3P</code>. Leg B the same with <code>SWB1</code>. The bulk (4th) pin of a VDMOS is tied to the source.</li>
    <li>Inductor box: pin 4 to <code>SWA1</code>, pin 3 to <code>SWB1</code>, pin 1 to <code>LA2_1</code>, pin 2 to <code>LB2_1</code>. This is the KiCad pin numbering; the model is inverse-coupled (Turns 1, −1).</li>
    <li>From LA2_1 and LB2_1 through a 0 V sense source and a <code>TMCS1126</code> box into <code>PV2P</code>.</li>
    <li>Gate pulses: top-A high from 0 to 2.3 µs, bottom-A high from 2.5 to 4.8 µs; leg B shifted by 2.5 µs. That is 50 % minus the 200 ns dead time at each edge. Reference each pulse source to its own FET source node.</li>
    <li><code>.tran 0 2.5m 2.4m 20n</code> so the last 20 cycles are saved with enough points.</li>
  </ol>
  <div class="expect"><h4>What you should see</h4>
    <p>Two triangular inductor currents 180° apart with a large ripple (about 7 A pk-pk per phase at 200 kHz with this
    inductor). With all three modules at 1000 W/m² the average currents are zero: the converter idles and costs about
    1 W. Shade module 2 to 600 W/m² and converter 1 pushes about 6 A into <code>PV2P</code>; with the resistor load the
    string makes <b>{{S3_DELTA_R}}</b> more than the reference string, with the 10 A sink <b>{{S3_DELTA_CC}}</b>.
    Do not push the sink much higher in this single-converter test: one equaliser can only hold
    (14.9 + 8.9)/2 ≈ 11.9 A of string current with module 2 at 600 W/m², and at 12 A the model runs away (see
    Findings). Module 3 shading is untouched by converter 1.</p>
    <p>Read the switch node: it swings between the converter's rails, i.e. the sum of two module voltages
    (about 77 V at full sun), and dips to −0.9 V during the dead time while the body diode carries the current.
    V1 and V2 differ by a few volts at 6 A: that is the dead-time droop of an open-loop 50 % bridge, not a fault.</p>
    {{S3_TABLE}}
    <div class="figs">{{S3_PLOTS}}</div>
  </div>
</section>

<section class="stage" id="s4">
  <div class="stagehead"><div class="brick">4</div><div>
    <h2>Converter 2</h2>
    <p class="adds">The identical block one module lower: half-bridges between <code>PV2P</code> and <code>GND</code>, common
    node into <code>PV3P</code>. Same timing as converter 1.</p>
    <div class="elements">{{N_S4}} netlist elements · stages/S4.qsch</div></div></div>
  <div class="duo">
    <div class="parts"><table><thead><tr><th>ref</th><th>part</th><th>Qspice value / attributes</th></tr></thead><tbody>
      <tr><td>MTA2 … XL2 XsA2 XsB2 VsA2 VsB2</td><td>as converter 1 (Q5–Q8, L2, U8, U9 in KiCad)</td><td>nets SWA2, SWB2, LA2_2, LB2_2</td></tr>
    </tbody></table></div>
    <div>{{FIG_S4}}
    <div class="legend"><span><i></i>added in this stage</span><span><i class="o"></i>already placed</span></div></div>
  </div>
  <div class="expect"><h4>What you should see</h4>
    <p>Now both midpoints are held. With module 2 shaded the string makes {{S4_DELTA_R2}} (resistor) / {{S4_DELTA_CC2}}
    (10 A sink) relative to the reference; with module 3 at 400 W/m² it is {{S4_DELTA_R3}} / {{S4_DELTA_CC3}}.
    With two converters the 10 A case turns positive again: the shaded module's shortfall is now shared by both
    neighbours instead of dragging one of them to short circuit. The converters share the shuffle current: watch
    <code>ish1</code> and <code>ish2</code> (opposite signs when the middle module is the weak one).</p>
    {{S4_TABLE}}
    <div class="figs">{{S4_PLOTS}}</div>
  </div>
</section>

<section class="stage" id="s5">
  <div class="stagehead"><div class="brick">5</div><div>
    <h2>Real gate drive: 1ED3140, 10 R / 4R7, bootstrap, 12 V rails</h2>
    <p class="adds">The ideal pulse sources are replaced by the Gate_Drivers sheet: one isolated 1ED3140 per FET with a
    10 Ω source path (OUTH) and 4.7 Ω sink path (OUTL), the IN+/IN− cross-conduction interlock, a 12 V rail per
    converter (the Würth module, modelled as an ideal 12 V referenced to the converter's bottom rail), VSSA210
    bootstrap diodes behind 10 Ω, and 100 nF ∥ 10 µF bootstrap capacitors. PWM comes from 3.3 V logic sources.</p>
    <div class="elements">{{N_S5}} netlist elements · stages/S5.qsch</div></div></div>
  <div class="duo">
    <div class="parts"><table><thead><tr><th>ref</th><th>part</th><th>Qspice value / attributes</th></tr></thead><tbody>
      <tr><td>XdTA1 XdBA1 XdTB1 XdBB1</td><td>Infineon 1ED3140MU12F (behavioural)</td><td>1ED3140 — TPD 70 n, RH 1.4, RL 1.0, UVLO 8</td></tr>
      <tr><td>RonTA1 / RoffTA1</td><td>KOA SG73S 10R (OUTH) / SG73P 4R7 (OUTL)</td><td>10 / 4.7</td></tr>
      <tr><td>DbA1 DbB1, RbA1 RbB1</td><td>Vishay VSSA210 bootstrap diode, 10 Ω series</td><td>VSSA210 / 10</td></tr>
      <tr><td>CbA1, Cb2A1</td><td>bootstrap 100 nF ∥ 10 µF</td><td>100n RSER=20m / 10u RSER=5m</td></tr>
      <tr><td>Vreg1, CvL1, Cv2L1</td><td>12 V rail (Würth 173951275) + its decoupling</td><td>12 / 100n / 10u</td></tr>
      <tr><td>VpTA1 VpBA1 VpTB1 VpBB1</td><td>NUCLEO PWM (S1_A_H, S1_A_L, S1_B_H, S1_B_L)</td><td>PULSE(0 3.3 t0 5n 5n 2.3u 5u)</td></tr>
    </tbody></table></div>
    <div>{{FIG_S5}}
    <div class="legend"><span><i></i>added in this stage</span><span><i class="o"></i>already placed</span></div></div>
  </div>
  <h3>Place it in Qspice</h3>
  <ol class="steps">
    <li>Each driver box: IN+ on its own PWM net, IN− on the complementary PWM of the same leg (top driver: IN+ = A_H, IN− = A_L; bottom driver the other way round). That reproduces the wiring on the sheet and the hardware interlock.</li>
    <li>Top drivers: VCC2 on <code>BOOTA1</code>/<code>BOOTB1</code>, VEE2 on the switch node. Bottom drivers: VCC2 on <code>VREG1</code>, VEE2 on the converter's bottom rail.</li>
    <li>OUTH → 10 Ω → gate, OUTL → 4.7 Ω → gate. Turn-on is the slow edge, turn-off the fast one.</li>
    <li>Bootstrap: <code>VREG1</code> → 10 Ω → VSSA210 → <code>BOOTA1</code>; 100 nF and 10 µF from BOOTA1 to SWA1.</li>
  </ol>
  <div class="expect"><h4>What you should see</h4>
    <p>Gate-source pulses of 12 V with a visible 200 ns gap between the bottom FET turning off and the top FET turning
    on (the <code>tdead1</code> measurement), the bootstrap voltage sagging by a fraction of a volt each cycle and
    recovering while the bottom FET is on, and the same power numbers as stage 4 within a few watts.</p>
    {{S5_TABLE}}
    <div class="figs">{{S5_PLOTS}}</div>
  </div>
</section>

<section class="stage" id="s6">
  <div class="stagehead"><div class="brick">6</div><div>
    <h2>Copper, package, ESL and cable parasitics</h2>
    <p class="adds">Lumped R + L in the rails, switch nodes, sensor paths and gate loops (from the board file), TO-252 lead
    inductances, 15 nH behind each 130 µF, and 1.5 m of 4 mm² cable per module lead. All numbers live in
    <code>parasitics.json</code>; regenerate it with <code>python pcb_parasitics.py</code> or edit it by hand.
    Every inductance carries a parallel damping resistance (5 Ω on the board, 50 Ω on the cables): without it the
    nanohenry loops ring against the MOSFET capacitances with a Q above 100 and the solver stalls. From this stage on
    the snubber and HF-capacitor footprints are also in the netlist at 1 pF, i.e. present but not fitted.</p>
    <div class="elements">{{N_S6}} netlist elements · stages/S6.qsch</div></div></div>
  <div class="duo">
    <div class="parts"><table><thead><tr><th>ref</th><th>part</th><th>Qspice value / attributes</th></tr></thead><tbody>
      <tr><td>XtT1 XtB1 XtM1 …</td><td>rail copper (PV1+, PV3+, PV2+ shares)</td><td>trace R=… L=…</td></tr>
      <tr><td>XtSWA1 XtSWB1</td><td>switch-node copper, FET pads to inductor pad (M_T_Aph_S, M_T_Bph_S)</td><td>trace</td></tr>
      <tr><td>XtLA1 XtLB1</td><td>inductor-to-sensor pours</td><td>trace</td></tr>
      <tr><td>XtgTA1 …</td><td>gate tracks</td><td>trace</td></tr>
      <tr><td>LdTA1 LsTA1 …</td><td>DPAK drain / source leads</td><td>1.5n / 3n</td></tr>
      <tr><td>Lc1..Lc4</td><td>130 µF ESL</td><td>15n</td></tr>
      <tr><td>Xcab1p Xcab1n …</td><td>module cable + XT60 per lead</td><td>trace R=6.95m L=750n RP=50</td></tr>
      <tr><td>RsnTA1 CsnTA1 … ChfA1 LhfA1 …</td><td>snubber / HF footprints, not fitted</td><td>.param Csn=1p Rsn=4.7 Chf=1p</td></tr>
    </tbody></table></div>
    <div>{{FIG_S6}}
    <div class="legend"><span><i></i>added in this stage</span><span><i class="o"></i>already placed</span></div></div>
  </div>
  <h3>The numbers used</h3>
  {{S6_LUMPS}}
  <div class="expect"><h4>What you should see</h4>
    <p>The switch node now overshoots and rings after each edge instead of stepping cleanly, and the gate waveform
    shows the gate-loop resonance. The DC numbers barely move: the copper is a few hundred micro-ohms.</p>
    {{S6_TABLE}}
    <div class="figs">{{S6_PLOTS}}</div>
  </div>
</section>

<section class="stage" id="s7">
  <div class="stagehead"><div class="brick">7</div><div>
    <h2>The baseline table</h2>
    <p class="adds">Same circuit as stage 6 with every measurement switched on: this is the sheet to bring to the bench.
    Columns are the six step combinations (three irradiance patterns × two loads).</p>
    <div class="elements">{{N_S7}} netlist elements · stages/S7.qsch</div></div></div>
  <div class="expect"><h4>Numbers to compare against on the bench</h4>
    {{S7_TABLE}}
    <div class="figs">{{S7_PLOTS}}</div>
  </div>
</section>

<section class="stage" id="s8">
  <div class="stagehead"><div class="brick">8</div><div>
    <h2>Filling the placeholders: snubber and HF-cap sweep</h2>
    <p class="adds">The RC snubber footprints across each FET (R49–R52 with C73–C84) and the rail-to-rail HF capacitor
    positions (C91–C96) are populated and stepped. This stage is for choosing values, not part of the baseline.</p>
    <div class="elements">{{N_S8}} netlist elements · stages/S8.qsch, S8b.qsch</div></div></div>
  <div class="duo">
    <div class="parts"><table><thead><tr><th>ref</th><th>part</th><th>Qspice value / attributes</th></tr></thead><tbody>
      <tr><td>RsnTA1 + CsnTA1 …</td><td>RC snubber across each FET</td><td>{Rsn} / {Csn}, stepped</td></tr>
      <tr><td>ChfA1 + LhfA1 …</td><td>three HF caps per leg, rail to rail</td><td>{3*Chf} with ESL/3</td></tr>
    </tbody></table></div>
    <div>{{FIG_S8}}
    <div class="legend"><span><i></i>added in this stage</span><span><i class="o"></i>already placed</span></div></div>
  </div>
  <div class="expect"><h4>What the sweep says</h4>
    <p>With the copper and package numbers from stage 6 the switch node overshoots by only a volt or two, so the
    snubbers are not needed for voltage stress; what they do is soften the −3 to −4 V dip during the dead time.
    The resistor dissipation is well below the textbook C·V²·f because the 7 A inductor ripple swings the node
    during the dead time (near zero-voltage switching), so a few hundred pF costs tens of milliwatts. That trick
    stops working for large capacitors: the dead time can only move about 7 A × 200 ns = 1.4 µC, i.e. 14 V on
    100 nF, so the 100 nF parts currently on the BOM would be hard-switched at up to C·V²·f ≈ 100 W each.
    Every position here sees the full two-module voltage, so rate the parts for that.</p>
    {{S8_TABLES}}
    <div class="figs">{{S8_PLOTS}}</div>
  </div>
</section>

<section class="stage" id="findings">
  <h2>Findings while building the model</h2>
  <div class="findings">
    <div class="finding"><span class="chip warn">check before testing</span><b>Converter 2 schematic: Q6 source not wired to the bottom rail.</b>
      <p>In <code>Shuffle_Converter.kicad_sch</code> the local net <code>M_B_Aph_S</code> (Q6 source, C82–C84, driver VEE2) is not joined to
      <code>Input_B</code>; converter 1's sheet is wired correctly and the PCB has Q6 pad 3 on GND. The board is fine, but the schematic
      and board are out of sync. Updating the PCB from the schematic would disconnect that source.</p></div>
    <div class="finding"><span class="chip warn">voltage margin</span><b>Each FET blocks the sum of two module voltages, plus the ringing.</b>
      <p>The switch node swings between the converter's rails (stage 3 plot): about 77 V at MPP with the Aiko parameters, 87 V with
      the 10 A sink (modules near 43 V each), and up to 93 V at open circuit. With the copper and package parasitics of stage 6
      the edges overshoot by 10–14 V, so the simulated peak drain voltage reaches 100 V in the sink case — the rating of the
      STD45N10F7. A lower-Voc test module gives margin; the snubber sweep in stage 8 shows how much the overshoot can be trimmed.</p></div>
    <div class="finding"><span class="chip note">physics</span><b>Open-loop 50 % is an equaliser, not an optimiser.</b>
      <p>With the resistor load it recovers most of the shaded module's power. With a stiff current sink it pulls both modules of
      a pair toward their short-circuit currents; compare the stage 3 and 4 tables before reading a bench result as good or bad.</p></div>
    <div class="finding"><span class="chip warn">bench limit</span><b>Do not run the current-sink test above about 11 A with one converter.</b>
      <p>One equalising converter can hold at most (Isc<sub>full</sub> + Isc<sub>shaded</sub>)/2 ≈ 11.9 A of string current when the middle
      module is at 600 W/m². At 12 A the model has no steady state: module 1 collapses into its bypass diode and the inductor
      current ramps without limit (150 A within 50 µs in the simulation). On the bench that is the electronic load hitting its
      compliance limit or the converter fuse. The baseline therefore uses a 10 A sink.</p></div>
    <div class="finding"><span class="chip note">physics</span><b>Dead time causes a few volts of V1–V2 droop at 6 A.</b>
      <p>With 200 ns of body-diode conduction per edge at 5 µs period the effective output resistance of the bridge is set by the
      ripple polarity at each edge; that is what keeps the two modules a few volts apart.</p></div>
    <div class="finding"><span class="chip warn">rating</span><b>C91–C96 sit across Input_T–Input_B.</b>
      <p>The rail-to-rail HF positions see the two-module voltage (77–93 V), not one module; the 50 V KGM21NR71H104KM part in the BOM
      is under-rated there (already noted for rectification).</p></div>
    <div class="finding"><span class="chip ok">approximation</span><b>MOSFET, driver and copper models are ballpark by design.</b>
      <p>STD45N10F7 is a VDMOS estimated from datasheet headline numbers; swap in the Qspice MOSFET-generator model when ready.
      The 1ED3140 is behavioural (70 ns, 1.4 Ω / 1.0 Ω, UVLO 8 V). Copper lumps come from pour bounding boxes with a 0.5
      proximity factor on inductance.</p></div>
    <div class="finding"><span class="chip ok">model note</span><b>The PV model is clamped at zero volts.</b>
      <p>The Karmalkar–Haneefa power law <code>(V/Voc)^m</code> is undefined for a reverse-biased (bypassed) module, and the
      original expression made the simulator crawl at picosecond steps whenever a bypass diode was conducting. The library
      keeps the original as <code>pvmi_orig</code> and uses <code>max(V,0)</code> in <code>pvmi</code>; above 0 V the two are identical.
      The reference string also carries the 10 nF module capacitance for the same reason.</p></div>
  </div>
</section>

<section class="stage" id="run">
  <h2>Run it</h2>
  <pre>cd "Version 0/Qspice/PCB_Baseline"
python pcb_parasitics.py          # optional: refresh parasitics.json from the board file
python gen_shuffler.py --verify   # regenerate stages/S*.qsch + S*.cir, check each schematic with QUX and QSPICE64
python gen_shuffler.py --report --verify   # regenerate ../Shuffler_PCB_Baseline.qsch (the single-sheet file)
python run_baseline.py            # QSPICE64 + QPOST on every stage -> results/   (add REPORT to include the single sheet)
python build_book.py              # rebuild this page with the new numbers</pre>
  <p>The single report-grade file is <code>Version 0/Qspice/Shuffler_PCB_Baseline.qsch</code> (with <code>shuffler_models.lib</code>
  next to it): the complete model of stage 7 on one sheet, laid out by block, with every parasitic and setting as a
  <code>.param</code> in its PARAMETERS block. <code>stages/S7.qsch</code> is the same circuit in the stage layout. The
  <code>.step</code> directives sweep irradiance and load, so one run produces all six columns of the baseline table.</p>
</section>
</main>
</div>

"""

if __name__ == "__main__":
    build()
