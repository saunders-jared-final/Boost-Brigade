"""
run_baseline.py - batch-run the stage netlists with QSPICE64, collect the .meas results with
QPOST, and export waveform plots (SVG, no external Python packages needed).

  python run_baseline.py               run every stage found in stages/
  python run_baseline.py S3 S4         run selected stages
  python run_baseline.py --plots-only  re-make the plots/tables from existing .qraw files

Outputs (results/):
  <stage>.meas.txt        raw QPOST console output
  <stage>.meas.json       parsed: {measurement: [value per step, ...]}
  <stage>_<trace>.svg     waveform plots of the last saved window (step selected below)
  baseline_table.md       all measurements, one table per stage
"""

import array
import json
import math
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STAGES = os.path.join(HERE, "stages")
RESULTS = os.path.join(HERE, "results")
QSPICE_DIR = r"C:\Program Files\QSPICE"
SIM_TIMEOUT = 7200     # s per stage (all steps; S9 is a 12 ms switching run)
REPORT_CIR = os.path.abspath(os.path.join(HERE, "..", "Shuffler_PCB_Baseline.cir"))   # the single-sheet file
USAGE = """usage: python run_baseline.py [STAGE ...] [--plots-only] [--remeasure]
  STAGE   S1 .. S8b, S9 (files in stages/), or REPORT for ../Shuffler_PCB_Baseline.cir; none = every stage
  --plots-only   redraw the SVG plots from existing .qraw files, no simulation
  --remeasure    re-evaluate the .meas lines from existing .qraw files, no simulation
"""


def stage_paths(stage):
    """(netlist, .qraw, working directory) of a stage; REPORT is the single-sheet file one level up."""
    if stage.upper() == "REPORT":
        return REPORT_CIR, REPORT_CIR[:-4] + ".qraw", os.path.dirname(REPORT_CIR)
    return os.path.join(STAGES, stage + ".cir"), os.path.join(STAGES, stage + ".qraw"), STAGES

# which step's waveforms to plot per stage: (CASE, LOADSEL) or None for stages without those steps
PLOT_STEP = {"CASE": 2, "LOADSEL": 0}

# traces to plot per stage (label, expression-style variable names as they appear in the .qraw)
# (name, traces, optional window in seconds shown from the end of the saved data)
SW = 15e-6      # three switching periods for the fast waveforms
PLOTS = {
    "S1": [("string", ["V(pv1p)", "V(r1p)"]), ("module_currents", ["I(vi1)", "I(vi2)", "I(vi3)"])],
    "S2": [("string", ["V(pv1p)", "V(r1p)"]), ("midpoints", ["V(pv2p)", "V(pv3p)"])],
    "S3": [("switch_node", ["V(swa1)", "V(swb1)"], SW), ("inductor_currents", ["I(vsa1)", "I(vsb1)"], SW),
           ("module_currents", ["I(vi1)", "I(vi2)", "I(vi3)"]), ("midpoints", ["V(pv2p)", "V(pv3p)"])],
    "S4": [("switch_nodes", ["V(swa1)", "V(swa2)"], SW), ("inductor_currents", ["I(vsa1)", "I(vsb1)", "I(vsa2)", "I(vsb2)"], SW),
           ("module_currents", ["I(vi1)", "I(vi2)", "I(vi3)"]), ("fet_power", ["P(mta1)", "P(mba1)"], SW)],
    "S5": [("gate_drive", ["V(gta1)-V(swa1)", "V(gba1)-V(pv3p)"], SW), ("bootstrap", ["V(boota1)-V(swa1)"], SW),
           ("switch_node", ["V(swa1)"], SW), ("inductor_currents", ["I(vsa1)", "I(vsb1)"], SW)],
    "S6": [("switch_node", ["V(swa1)-V(b1)"], SW), ("gate_drive", ["V(gta1)-V(swa1)"], SW),
           ("inductor_currents", ["I(vsa1)", "I(vsb1)"], SW), ("fet_power", ["P(mta1)", "P(mba1)"], SW)],
    "S7": [("switch_node", ["V(swa1)-V(b1)"], SW), ("switch_node_2", ["V(swa2)-V(b2)"], SW), ("gate_drive", ["V(gta1)-V(swa1)"], SW),
           ("inductor_currents", ["I(vsa1)", "I(vsb1)", "I(vsa2)", "I(vsb2)"], SW), ("module_currents", ["I(vi1)", "I(vi2)", "I(vi3)"]),
           ("fet_power", ["P(mta1)", "P(mba1)", "P(mtb1)", "P(mbb1)"], SW)],
    "S8": [("switch_node", ["V(swa1)-V(b1)"], SW)],
    "S8b": [("switch_node", ["V(swa1)-V(b1)"], SW)],
    "S9": [("module_voltages", ["V(pv1p)-V(pv2p)", "V(pv2p)-V(pv3p)", "V(pv3p)"]),
           ("duties", ["V(da1)", "V(db1)", "V(da2)", "V(db2)"]),
           ("shuffled_currents", ["I(vsa1)+I(vsb1)", "I(vsa2)+I(vsb2)"]),
           ("supervisor", ["V(beta)", "V(stress)", "V(rv1)"]),
           ("module_currents", ["I(vi1)", "I(vi2)", "I(vi3)", "V(im1r)", "V(im2r)"]),
           ("inductor_currents", ["I(vsa1)", "I(vsb1)", "I(vsa2)", "I(vsb2)"], 30e-6)],
}


# ----------------------------------------------------------------------------- qraw reader
def read_qraw(path):
    """Return (names, columns) where columns[i] is an array('d') for variable names[i].
    Qspice .qraw: text header up to 'Binary:\\n', then all points as consecutive 8-byte doubles,
    point-major (time, var1, var2, ...)."""
    with open(path, "rb") as f:
        data = f.read()
    i = data.find(b"Binary:")
    header = data[:i].decode("cp1252", "replace") if i > 0 else ""
    mv, mp = re.search(r"No\. Variables:\s*(\d+)", header), re.search(r"No\. Points:\s*(\d+)", header)
    if not (mv and mp):
        raise ValueError(f"{os.path.basename(path)} has no waveform data (simulation failed? see the .sim.txt log)")
    nvars, npts = int(mv.group(1)), int(mp.group(1))
    if npts == 0 or nvars == 0:
        raise ValueError(f"{os.path.basename(path)} holds no points (simulation aborted? see the .sim.txt log)")
    names = []
    for m in re.finditer(r"^\t(\d+)\t(\S+)\t(\S+)", header, re.M):
        names.append(m.group(2))
    start = i + len(b"Binary:\n")
    vals = array.array("d")
    vals.frombytes(data[start:start + nvars * npts * 8])
    cols = [vals[j::nvars] for j in range(nvars)]
    return names, cols, header


def split_steps(names, cols):
    """Split point-major data into steps using the stored step parameters (or time resets)."""
    n = len(cols[0])
    params = [k for k, nm in enumerate(names) if nm.upper() in ("CASE", "LOADSEL", "CSN", "RSN", "CHF")]
    if params:
        key = lambda i: tuple(round(cols[k][i], 12) for k in params)
    else:
        key = lambda i: 0
    steps, cur, cur_key, start = [], None, None, 0
    t = cols[0]
    for i in range(n):
        k = key(i)
        if i > 0 and (k != cur_key or t[i] < t[i - 1]):
            steps.append((cur_key, start, i))
            start = i
        cur_key = k
    steps.append((cur_key, start, n))
    labels = []
    for k, a, b in steps:
        lab = {names[p]: k[j] for j, p in enumerate(params)} if params else {}
        labels.append((lab, a, b))
    return labels


# ----------------------------------------------------------------------------- plotting (SVG)
def fmt_si(v, unit=""):
    if v == 0:
        return "0" + unit
    exp = int(math.floor(math.log10(abs(v)) / 3) * 3)
    exp = max(-12, min(9, exp))
    pre = {-12: "p", -9: "n", -6: "u", -3: "m", 0: "", 3: "k", 6: "M", 9: "G"}[exp]
    return f"{v / 10 ** exp:.3g}{pre}{unit}"


def svg_plot(path, title, t, series, xlabel="time (s)", width=760, height=320, ylabel=""):
    """Simple multi-trace line plot. series: list of (label, values). Legend sits below the axes."""
    palette = ["#1f6feb", "#d1242f", "#1a7f37", "#9a6700", "#8250df", "#0969da"]
    ml, mr, mt, mb = 70, 20, 34, 64
    pw, ph = width - ml - mr, height - mt - mb
    t0, t1 = t[0], t[-1]
    ymin = min(min(v) for _, v in series)
    ymax = max(max(v) for _, v in series)
    if ymax == ymin:
        ymax, ymin = ymax + 1, ymin - 1
    pad = (ymax - ymin) * 0.06
    ymin, ymax = ymin - pad, ymax + pad
    sx = lambda x: ml + (x - t0) / (t1 - t0) * pw if t1 > t0 else ml
    sy = lambda y: mt + (ymax - y) / (ymax - ymin) * ph
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" font-family="system-ui, sans-serif" font-size="11">',
           f'<rect x="0" y="0" width="{width}" height="{height}" fill="white"/>',
           f'<text x="{ml}" y="18" font-size="13" font-weight="600">{title}</text>']
    # grid + axes
    for k in range(6):
        yv = ymin + (ymax - ymin) * k / 5
        y = sy(yv)
        out.append(f'<line x1="{ml}" y1="{y:.1f}" x2="{ml + pw}" y2="{y:.1f}" stroke="#e5e7eb"/>')
        out.append(f'<text x="{ml - 6}" y="{y + 4:.1f}" text-anchor="end" fill="#555">{fmt_si(yv)}</text>')
    for k in range(6):
        xv = t0 + (t1 - t0) * k / 5
        x = sx(xv)
        out.append(f'<line x1="{x:.1f}" y1="{mt}" x2="{x:.1f}" y2="{mt + ph}" stroke="#e5e7eb"/>')
        out.append(f'<text x="{x:.1f}" y="{mt + ph + 14}" text-anchor="middle" fill="#555">{fmt_si(xv, "s")}</text>')
    out.append(f'<rect x="{ml}" y="{mt}" width="{pw}" height="{ph}" fill="none" stroke="#888"/>')
    if ylabel:
        out.append(f'<text x="14" y="{mt + ph / 2:.1f}" fill="#555" transform="rotate(-90 14 {mt + ph / 2:.1f})" text-anchor="middle">{ylabel}</text>')
    out.append(f'<text x="{ml + pw / 2:.1f}" y="{mt + ph + 28}" fill="#555" text-anchor="middle">{xlabel}</text>')
    # decimate to at most ~1500 points per trace (keeps the inline SVGs small)
    n = len(t)
    stride = max(1, n // 1500)
    lx = ml
    for i, (label, v) in enumerate(series):
        pts = " ".join(f"{sx(t[j]):.1f},{sy(v[j]):.1f}" for j in range(0, n, stride))
        col = palette[i % len(palette)]
        out.append(f'<polyline points="{pts}" fill="none" stroke="{col}" stroke-width="1.2"/>')
        # legend row under the x-axis label, left to right
        out.append(f'<rect x="{lx}" y="{mt + ph + 44}" width="14" height="3" fill="{col}"/>')
        out.append(f'<text x="{lx + 18}" y="{mt + ph + 48}" fill="#333">{label}</text>')
        lx += 18 + 7 * len(label) + 22
    out.append("</svg>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))


def eval_expr(expr, names, cols, a, b):
    """Evaluate 'V(x)', 'I(x)', 'P(x)' or 'V(x)-V(y)' over a step slice."""
    lower = {nm.lower(): nm for nm in names}
    def col(term):
        term = term.strip().lower()
        if term not in lower:
            raise KeyError(term)
        return cols[names.index(lower[term])]
    if "-" in expr and not expr.startswith("-"):
        p, q = expr.split("-", 1)
        cp, cq = col(p), col(q)
        return [cp[i] - cq[i] for i in range(a, b)]
    c = col(expr)
    return list(c[a:b])


def make_plots(stage, qraw):
    names, cols, header = read_qraw(qraw)
    steps = split_steps(names, cols)
    chosen = None
    for lab, a, b in steps:
        if all(abs(lab.get(k, v) - v) < 1e-9 for k, v in PLOT_STEP.items() if k in lab):
            chosen = (lab, a, b)
            break
    if chosen is None:
        chosen = steps[0]
    lab, a, b = chosen
    made = []
    for spec in PLOTS.get(stage, []):
        name, exprs = spec[0], spec[1]
        window = spec[2] if len(spec) > 2 else None          # seconds of the saved window to show (from the end)
        a2 = a
        if window:
            t_end = cols[0][b - 1]
            while a2 < b - 1 and cols[0][a2] < t_end - window:
                a2 += 1
        t0 = cols[0][a2]
        t = [x - t0 for x in cols[0][a2:b]]                  # time axis restarts at 0 for the shown window
        series = []
        for e in exprs:
            try:
                series.append((e, eval_expr(e, names, cols, a2, b)))
            except KeyError:
                pass
        if not series:
            continue
        unit = {"V": "V", "I": "A", "P": "W"}.get(exprs[0][0].upper(), "")
        case = int(lab.get("CASE", 0)) if lab else 0
        load = "resistor load" if lab and lab.get("LOADSEL", 0) < 0.5 else "10 A sink"
        casetxt = {1: "1000/1000/1000", 2: "1000/600/1000", 3: "1000/1000/400"}.get(case, "")
        title = f"{stage} {name.replace('_', ' ')}" + (f"  ({casetxt} W/m², {load})" if lab else "")
        out = os.path.join(RESULTS, f"{stage}_{name}.svg")
        svg_plot(out, title, t, series, ylabel=unit)
        made.append(out)
    return made, [l for l, _, _ in steps]


# ----------------------------------------------------------------------------- .meas evaluated from the .qraw
# QPOST.exe crashes (access violation) on .qraw files above roughly 300 MB, so the runner can evaluate the
# measurement statements itself: AVG / MAX / MIN / PP / RMS over the saved window, FIND ... AT, and
# TRIG ... TARG with RISE/FALL counts.  Expressions may contain V(a), V(a,b), I(x), P(x), + - * / and ().
_TOKEN = re.compile(r"([VIP])\(([^)]+)\)", re.I)


def _compile_expr(expr, names):
    lower = {nm.lower(): idx for idx, nm in enumerate(names)}
    refs = []

    def repl(m):
        kind, arg = m.group(1).upper(), m.group(2).strip()
        if kind == "V":
            parts = [p.strip().lower() for p in arg.split(",")]
            keys = [f"v({p})" for p in parts]
            if parts[-1] in ("0", "gnd"):
                keys = keys[:1]
            for k in keys:
                if k not in lower:
                    raise KeyError(k)
            refs.extend(lower[k] for k in keys)
            if len(keys) == 2:
                return f"(c[{lower[keys[0]]}][i]-c[{lower[keys[1]]}][i])"
            return f"c[{lower[keys[0]]}][i]"
        key = f"{kind.lower()}({arg.lower()})"
        if key not in lower:
            raise KeyError(key)
        refs.append(lower[key])
        return f"c[{lower[key]}][i]"

    py = _TOKEN.sub(repl, expr)
    return eval(f"lambda c, i: {py}")


def _crossing(t, f, level, direction, count, a, b):
    """time of the count-th crossing of level in `direction` ('rise'/'fall'/'cross') inside [a, b)."""
    n = 0
    for i in range(a, b - 1):
        y0, y1 = f(i), f(i + 1)
        rise, fall = y0 < level <= y1, y0 >= level > y1
        if (direction == "rise" and rise) or (direction == "fall" and fall) or (direction == "cross" and (rise or fall)):
            n += 1
            if n == count:
                frac = (level - y0) / (y1 - y0) if y1 != y0 else 0.0
                return t[i] + frac * (t[i + 1] - t[i])
    return None


def meas_from_qraw(cir_path, qraw_path):
    """Evaluate the .meas lines of a netlist over every step of its .qraw. Returns {name: [per step]}."""
    names, cols, _ = read_qraw(qraw_path)
    steps = split_steps(names, cols)
    t = cols[0]
    out = {}
    text = open(cir_path, "rb").read().decode("cp1252", "replace")
    for ln in text.splitlines():
        m = re.match(r"\.meas\s+tran\s+(\w+)\s+(.*)", ln.strip(), re.I)
        if not m:
            continue
        name, body = m.group(1).lower(), m.group(2).strip()
        vals = []
        for (_lab, a, b) in steps:
            try:
                vals.append(_eval_meas(body, names, cols, t, a, b))
            except (KeyError, ZeroDivisionError, ValueError, SyntaxError):
                vals.append(float("nan"))
        out[name] = vals
    return out


def _eval_meas(body, names, cols, t, a, b):
    up = body.upper()
    mt = re.match(r"TRIG\s+(.+?)=(\S+)\s+(RISE|FALL|CROSS)=(\d+)\s+TARG\s+(.+?)=(\S+)\s+(RISE|FALL|CROSS)=(\d+)", body, re.I)
    if mt:
        e1, v1, d1, n1, e2, v2, d2, n2 = mt.groups()
        f1, f2 = _compile_expr(e1, names), _compile_expr(e2, names)
        t1 = _crossing(t, lambda i: f1(cols, i), float(v1), d1.lower(), int(n1), a, b)
        t2 = _crossing(t, lambda i: f2(cols, i), float(v2), d2.lower(), int(n2), a, b)
        if t1 is None or t2 is None:
            return float("nan")
        return t2 - t1
    mf = re.match(r"FIND\s+(.+?)\s+AT\s+(\S+)", body, re.I)
    if mf:
        f = _compile_expr(mf.group(1), names)
        tt = float(mf.group(2).replace("u", "e-6").replace("m", "e-3").replace("n", "e-9"))
        for i in range(a, b - 1):
            if t[i] <= tt <= t[i + 1]:
                return f(cols, i)
        return float("nan")
    mk = re.match(r"(AVG|MAX|MIN|PP|RMS)\s+(.+)", body, re.I)
    if not mk:
        return float("nan")
    kind, expr = mk.group(1).upper(), mk.group(2)
    f = _compile_expr(expr, names)
    if kind in ("AVG", "RMS"):
        acc, T = 0.0, t[b - 1] - t[a]
        if T <= 0:
            return f(cols, a)
        prev = f(cols, a)
        for i in range(a + 1, b):
            cur = f(cols, i)
            dt = t[i] - t[i - 1]
            if kind == "AVG":
                acc += 0.5 * (prev + cur) * dt
            else:
                acc += 0.5 * (prev * prev + cur * cur) * dt
            prev = cur
        return acc / T if kind == "AVG" else math.sqrt(acc / T)
    vals = [f(cols, i) for i in range(a, b)]
    if kind == "MAX":
        return max(vals)
    if kind == "MIN":
        return min(vals)
    return max(vals) - min(vals)


# ----------------------------------------------------------------------------- QPOST parsing
def parse_qpost(text):
    """'.meas tran name ...:' followed by lines '   step value [time]' (or one line without step)."""
    res, cur = {}, None
    for ln in text.splitlines():
        m = re.match(r"\.meas\s+\w+\s+(\w+)\s", ln.strip(), re.I)
        if m:
            cur = m.group(1).lower()
            res[cur] = []
            continue
        if cur and ln.strip():
            toks = ln.split()
            try:
                if len(toks) >= 2 and toks[0].isdigit():
                    res[cur].append(float(toks[1]))
                else:
                    res[cur].append(float(toks[0]))
            except ValueError:
                pass
    return res


def run_stage(stage):
    cir, qraw, cwd = stage_paths(stage)
    print(f"[{stage}] simulating {os.path.basename(cir)} ...", flush=True)
    try:
        r = subprocess.run([os.path.join(QSPICE_DIR, "QSPICE64.exe"), os.path.basename(cir)], cwd=cwd,
                           capture_output=True, timeout=SIM_TIMEOUT)
    except subprocess.TimeoutExpired:
        print(f"[{stage}] TIMEOUT after {SIM_TIMEOUT}s")
        return None
    log = (r.stdout + r.stderr).decode("cp1252", "replace")
    with open(os.path.join(RESULTS, stage + ".sim.txt"), "w", encoding="utf-8") as f:
        f.write(log)
    tail = [l for l in log.splitlines() if l.strip()][-3:]
    print("   " + " | ".join(tail))
    qtext = ""
    for attempt in range(3):            # QPOST occasionally returns nothing right after the .qraw is closed
        q = subprocess.run([os.path.join(QSPICE_DIR, "QPOST.exe"), os.path.basename(cir)], cwd=cwd, capture_output=True, timeout=600)
        qtext = (q.stdout + q.stderr).decode("cp1252", "replace")
        if ".meas" in qtext:
            break
        import time
        time.sleep(3)
    with open(os.path.join(RESULTS, stage + ".meas.txt"), "w", encoding="utf-8") as f:
        f.write(qtext)
    meas = parse_qpost(qtext)
    if not meas:
        print("   QPOST gave no results; evaluating .meas from the .qraw instead")
        meas = meas_from_qraw(cir, qraw)
    with open(os.path.join(RESULTS, stage + ".meas.json"), "w", encoding="utf-8") as f:
        json.dump(meas, f, indent=1)
    return meas


def remeasure(stage):
    """Recompute the .meas results of an already simulated stage from its .qraw (no QPOST)."""
    cir, qraw, _ = stage_paths(stage)
    meas = meas_from_qraw(cir, qraw)
    with open(os.path.join(RESULTS, stage + ".meas.json"), "w", encoding="utf-8") as f:
        json.dump(meas, f, indent=1)
    return meas


def table_md(stage, meas, step_labels):
    if not meas:
        return f"## {stage}\n\n(no measurements)\n"
    nsteps = max(len(v) for v in meas.values())
    heads = []
    for i in range(nsteps):
        lab = step_labels[i] if i < len(step_labels) else {}
        heads.append(" ".join(f"{k}={v:g}" for k, v in lab.items()) or f"step {i + 1}")
    lines = [f"## {stage}", "", "| measurement | " + " | ".join(heads) + " |", "|---|" + "---|" * nsteps]
    for k, vals in meas.items():
        cells = [f"{v:.4g}" if isinstance(v, float) else str(v) for v in vals] + [""] * (nsteps - len(vals))
        lines.append(f"| {k} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print(USAGE)
        return
    os.makedirs(RESULTS, exist_ok=True)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    plots_only = "--plots-only" in sys.argv
    do_remeasure = "--remeasure" in sys.argv
    stages = args or sorted(f[:-4] for f in os.listdir(STAGES) if f.endswith(".cir") and not f.endswith("_quxcheck.cir"))
    md = ["# Baseline results (generated by run_baseline.py)", ""]
    for st in stages:
        if do_remeasure:
            print(f"[{st}] re-evaluating .meas from the .qraw", flush=True)
            meas = remeasure(st)
        elif plots_only:
            meas = json.load(open(os.path.join(RESULTS, st + ".meas.json"), encoding="utf-8")) \
                if os.path.exists(os.path.join(RESULTS, st + ".meas.json")) else {}
        else:
            meas = run_stage(st)
            if meas is None:
                continue
        qraw = stage_paths(st)[1]
        labels = []
        if os.path.exists(qraw):
            try:
                plots, labels = make_plots(st, qraw)
                print(f"   plots: {len(plots)}  steps: {len(labels)}")
            except Exception as e:
                print(f"   no plots: {e}")
        md.append(table_md(st, meas, labels))
    with open(os.path.join(RESULTS, "baseline_table.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print("wrote results/baseline_table.md")


if __name__ == "__main__":
    main()
