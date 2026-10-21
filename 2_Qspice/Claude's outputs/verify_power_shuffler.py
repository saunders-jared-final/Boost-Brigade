#!/usr/bin/env python3
"""
verify_power_shuffler.py - checks for the hierarchical sheets written by build_power_shuffler_integrated.py.

    python verify_power_shuffler.py [--no-sim] [--no-render] [--open-loop]

  --open-loop keeps the controller disabled (TEN = 2 ms) and skips the reference step: the two netlists then differ
  only by solver stepping, so the measurements must agree closely.

  1. QUX.exe -Netlist of ../Power_Shuffler_Integrated.qsch (kept as ../Power_Shuffler_Integrated.cir) and of a
     _quxcheck copy of the flat "../Buck Boost Full Bridge - v3 - control.qsch" (the copy is deleted afterwards).
  2. The hierarchical netlist is flattened (sub-sheet instances expanded, inner nodes and elements suffixed with
     QSPICE's bullet) and compared with the flat netlist: same elements, same connectivity up to a renaming of
     the unlabelled nodes, same values except the expressions that now go through .func.
  3. Both netlists are run for 1.5 ms (TEN = 0.3 ms, VREF2 step 1 V at 0.8 ms) in a scratch folder with QSPICE64 and
     the .meas results compared with QPOST (the DLL and ctrl_M2.txt are copied from the sheet folder, MyLibrary.lib
     from the QSPICE library folder). A third run, the flat netlist with its element lines in reverse order, shows
     how far solver noise alone moves each measurement: the circulating / shuffled inductor currents, the module
     voltage differences and the hall outputs are set by milliohm resistances and nanosecond switching edges and
     move by the same amount under a mere reordering as under the hierarchy, so they are reported but not judged.
     Pass / fail rests on the well-conditioned measurements (duties, PWM averages, string power / voltage /
     current, supervisor stress), which must agree to 0.5 %.
  4. Every sheet is rendered to figures/<sheet>.svg and .png (ImageMagick convert).
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "PCB_Baseline"))
from build_power_shuffler_integrated import TOP, SHEETS, QDIR, BUL                                # noqa: E402
import qsch_render                                                                                 # noqa: E402

QSPICE = "/mnt/c/Program Files/QSPICE"
FLAT = os.path.join(QDIR, "Buck Boost Full Bridge - v3 - control.qsch")
FIG = os.path.join(HERE, "figures")
SEP = "\u2022"                   # QSPICE's hierarchical separator (cp1252 0x95) as decoded text
VALUE_EXEMPT = ("bhs", "bdd", "bpt", "bpb")     # expressions rewritten through .func
WELL = ("da1", "db1", "da2", "db2", "pout", "vout", "iout", "stressmax", "pwmah1", "pwmah2")   # judged measurements


def wpath(p):
    return subprocess.run(["wslpath", "-w", p], capture_output=True, text=True, check=True).stdout.strip()


def run(exe, args, cwd, timeout):
    return subprocess.run([os.path.join(QSPICE, exe)] + list(args), cwd=cwd, capture_output=True, timeout=timeout)


# ----------------------------------------------------------------------------- netlisting
def qux(qsch):
    """QUX netlist of a sheet (written next to it); returns the .cir text (cp1252)."""
    cir = qsch[:-5] + ".cir"
    if os.path.exists(cir):
        os.remove(cir)
    r = run("QUX.exe", ["-Netlist", wpath(qsch)], cwd=os.path.dirname(qsch), timeout=120)
    if not os.path.exists(cir):
        raise RuntimeError("QUX produced no netlist for " + qsch + ": " + (r.stdout + r.stderr).decode("cp1252", "replace"))
    return open(cir, "rb").read().decode("cp1252")


def netlist_flat():
    base = FLAT[:-5] + "_quxcheck"
    shutil.copyfile(FLAT, base + ".qsch")
    try:
        return qux(base + ".qsch")
    finally:
        for ext in (".qsch", ".cir"):
            if os.path.exists(base + ext):
                os.remove(base + ext)


# ----------------------------------------------------------------------------- parsing
def parse_element(line):
    """(name, nodes, value) of one netlist element line. Handles the DLL form Ø´ref «in´d ...» «out´d ...» «gnd» dll params
    and ordinary 'ref n1 n2 ... value/model params'."""
    t = line.strip()
    if t.startswith("Ø´"):
        groups = re.findall(r"«([^»]*)»", t)
        nodes = [tok.replace("´d", "") for g in groups for tok in g.split()]
        ref = t.split()[0][2:]
        value = t.split("»")[-1].strip()
        return ref, nodes, value
    toks = t.split()
    ref = toks[0]
    kind = ref[0].upper()
    npins = {"R": 2, "C": 2, "L": 2, "V": 2, "I": 2, "B": 1, "D": 2, "M": 4}.get(kind)
    if kind == "X":
        # nodes up to the model name: the last token without '=' that is followed only by param tokens
        i = len(toks) - 1
        while "=" in toks[i]:
            i -= 1
        return ref, toks[1:i], " ".join(toks[i:])
    if npins is None:
        return ref, toks[1:], ""
    if kind == "B":
        m = re.match(r"(\S+)\s+(\S+)\s+(\S+)\s+(.*)$", t)
        return ref, [m.group(2), m.group(3)], m.group(4)
    return ref, toks[1:1 + npins], " ".join(toks[1 + npins:])


def parse_cir(text):
    """top-level elements, {subckt name: (ports, elements)} (nested definitions hoisted), directives."""
    elements, subckts, directives = [], {}, []
    stack = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("*"):
            continue
        low = line.lower()
        if low.startswith(".subckt"):
            toks = line.split()
            stack.append((toks[1], toks[2:], []))
            continue
        if low.startswith(".ends"):
            name, ports, els = stack.pop()
            subckts[name] = (ports, els)
            continue
        if line.startswith("."):
            directives.append(line)
            continue
        if low.startswith("¥") or low.startswith("×"):      # Schmitt / coupling records inside library subckts
            # QUX numbers the Schmitt instances through the whole file: not a circuit difference
            (stack[-1][2] if stack else elements).append(("opaque", [], re.sub(r"\u00a5\d+", "\u00a5#", line)))
            continue
        (stack[-1][2] if stack else elements).append(parse_element(line))
    return elements, subckts, directives


def flatten(elements, subckts, sheets):
    """Expand the instances of the sheet subcircuits; library subcircuits (ERUC23, HalfBridge_Driver) stay opaque."""
    out = []

    def expand(els, suffix, portmap):
        for ref, nodes, value in els:
            if ref == "opaque":
                continue
            model = value.split()[0] if value else ""
            if ref[0].upper() == "X" and model in sheets:
                ports, inner = subckts[model]
                assert len(ports) == len(nodes), (ref, ports, nodes)
                expand(inner, SEP + ref + suffix, dict(zip(ports, nodes)))
                continue
            mapped = [portmap[n] if n in portmap else ("0" if n == "0" else n + suffix) for n in nodes]
            out.append((ref + suffix, mapped, value))

    expand(elements, "", {})
    return out


def canonical(ref):
    """Element name as in the flat sheet: hall elements get the converter number, the rest drop the instance path."""
    parts = ref.split(SEP)
    base, path = parts[0], parts[1:]
    low = base.lower()
    if path and path[0] in ("XS1", "XS2") and low.startswith(("bhs", "rhs", "chs")):
        return base + path[0][-1]
    if path and path[0] in ("XP1", "XP2") and low.startswith(("bpt", "bpb")):
        return base + path[0][-1]
    return base


def canon_value(v):
    """Model names carry the instance: X4•ERUC23-4R1K -> ERUC23-4R1K."""
    return " ".join(tok.split(SEP)[-1] for tok in v.split())


def compare(flat_text, hier_text):
    fe, fs, _fd = parse_cir(flat_text)
    he, hs, _hd = parse_cir(hier_text)
    problems = []
    for name, ports in SHEETS.items():
        if name not in hs:
            problems.append(f"no .subckt {name} in the hierarchical netlist")
        elif hs[name][0] != ports:
            problems.append(f".subckt {name} ports {hs[name][0]} != generator {ports}")
    flat = {ref: (nodes, value) for ref, nodes, value in fe if ref != "opaque"}
    hier = {}
    for ref, nodes, value in flatten(he, hs, set(SHEETS)):
        c = canonical(ref)
        assert c not in hier, f"duplicate element {c} after flattening ({ref})"
        hier[c] = (nodes, value)
    for ref in sorted(set(flat) - set(hier)):
        problems.append(f"{ref}: only in the flat netlist")
    for ref in sorted(set(hier) - set(flat)):
        problems.append(f"{ref}: only in the hierarchical netlist")
    f2h, h2f = {}, {}
    for ref in sorted(set(flat) & set(hier)):
        (fn, fv), (hn, hv) = flat[ref], hier[ref]
        if len(fn) != len(hn):
            problems.append(f"{ref}: {len(fn)} vs {len(hn)} nodes")
            continue
        for a, b in zip(fn, hn):
            if f2h.setdefault(a, b) != b or h2f.setdefault(b, a) != a:
                problems.append(f"{ref}: node {a} <-> {b} conflicts with {f2h.get(a)} / {h2f.get(b)}")
        if not ref.lower().startswith(VALUE_EXEMPT) and canon_value(fv) != canon_value(hv):
            problems.append(f"{ref}: value '{fv}' vs '{hv}'")
    if f2h.get("0", "0") != "0":
        problems.append("ground maps to " + f2h["0"])
    # library subcircuits: identical text
    for name in sorted(set(fs) | set(hs)):
        if name in SHEETS:
            continue
        a, b = fs.get(name), hs.get(name)
        if a is None or b is None:
            problems.append(f"library subckt {name} missing on one side")
        elif a != b:
            problems.append(f"library subckt {name} differs")
    return problems, len(flat), len(f2h)


# ----------------------------------------------------------------------------- simulation
def short_netlist(text):
    closed = "--open-loop" not in sys.argv
    for a, b in ((".tran 20m", ".tran 1.5m"), ("TEN=1m", "TEN=0.3m" if closed else "TEN=2m"), ("VSTEP2=0", "VSTEP2=1" if closed else "VSTEP2=0"),
                 ("TSTEP=10m", "TSTEP=0.8m"), ("FROM 18m TO 20m", "FROM 1.3m TO 1.5m")):
        assert a in text, a
        text = text.replace(a, b)
    return text


def parse_qpost(text):
    out, name = {}, None
    for line in text.splitlines():
        m = re.match(r"\.meas tran (\w+) ", line.strip())
        if m:
            name = m.group(1)
        elif name and line.strip():
            try:
                out[name] = float(line.split()[0])
            except ValueError:
                pass
            name = None
    return out


def reordered(text):
    """The same netlist with the top-level element lines in reverse order (a solver-noise control)."""
    ls = text.splitlines()
    first = next(i for i, l in enumerate(ls) if l.startswith("."))
    els = [l for l in ls[1:first] if l.strip()]
    return "\n".join([ls[0]] + list(reversed(els)) + ls[first:] + [""])


def short_run(label, text, workdir):
    cir = os.path.join(workdir, label + "_check.cir")
    open(cir, "wb").write(short_netlist(text).encode("cp1252"))
    r = run("QSPICE64.exe", [wpath(cir)], cwd=workdir, timeout=900)
    log = (r.stdout + r.stderr).decode("cp1252", "replace")
    if "error" in log.lower():
        raise RuntimeError(label + " run failed:\n" + log)
    q = run("QPOST.exe", [wpath(cir)], cwd=workdir, timeout=300)
    return parse_qpost((q.stdout + q.stderr).decode("cp1252", "replace")), log


def simulate(flat_text, hier_text):
    work = tempfile.mkdtemp(prefix="pwr_shuffler_")
    try:
        for f in ("shuffler_ctrl_dll2.dll", "ctrl_M2.txt"):
            shutil.copyfile(os.path.join(QDIR, f), os.path.join(work, f))
        lib = find_library()
        if lib:
            shutil.copyfile(lib, os.path.join(work, "MyLibrary.lib"))
        h, hlog = short_run("hier", hier_text, work)
        f, flog = short_run("flat", flat_text, work)
        r, _rlog = short_run("flat_reordered", reordered(flat_text), work) if "--no-reorder" not in sys.argv else ({}, "")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return f, h, r, flog, hlog


def find_library():
    for root in (os.path.expanduser("~"), "/mnt/c/Users"):
        for dirpath, dirs, files in os.walk(root):
            if dirpath.count(os.sep) - root.count(os.sep) > 5:
                dirs[:] = []
            if "MyLibrary.lib" in files and "QSPICE" in dirpath:
                return os.path.join(dirpath, "MyLibrary.lib")
    return None


# ----------------------------------------------------------------------------- figures
def render_all():
    os.makedirs(FIG, exist_ok=True)
    scales = {TOP: 0.07, "Shuffler_1": 0.1, "Shuffler_2": 0.1, "Controller": 0.09, "PWM_Modulator": 0.14}
    for name, scale in scales.items():
        path = os.path.join(QDIR, name + ".qsch")
        comps, wires, nets, juncs, texts = qsch_render.parse_schematic(path, want_texts=True)
        xs = [c["x"] for c in comps] + [w[0][0] for w in wires] + [w[0][2] for w in wires] + [t["x"] for t in texts] + [n["x"] for n in nets]
        ys = [c["y"] for c in comps] + [w[0][1] for w in wires] + [w[0][3] for w in wires] + [t["y"] for t in texts] + [n["y"] for n in nets]
        crop = (min(xs) - 600, min(ys) - 600, max(xs) + 8000, max(ys) + 600)
        svg = os.path.join(FIG, name + ".svg")
        open(svg, "w", encoding="utf-8").write(qsch_render.render(path, crop, scale))
        subprocess.run(["convert", "-density", "96", "-background", "white", svg, os.path.join(FIG, name + ".png")], check=False)
    return sorted(os.listdir(FIG))


# ----------------------------------------------------------------------------- main
def main():
    hier_text = qux(os.path.join(QDIR, TOP + ".qsch"))
    flat_text = netlist_flat()
    print(f"netlists: hierarchical {len(hier_text.splitlines())} lines, flat {len(flat_text.splitlines())} lines")
    problems, n_el, n_nodes = compare(flat_text, hier_text)
    print(f"compare: {n_el} elements, {n_nodes} nodes matched, {len(problems)} problems")
    for p in problems[:30]:
        print("   ", p)
    ok = not problems
    if "--no-sim" not in sys.argv:
        f, h, r, flog, hlog = simulate(flat_text, hier_text)
        print(f"{'meas':10s} {'flat':>12s} {'hier':>12s} {'flat reord.':>12s}   judged")
        for k in sorted(set(f) | set(h)):
            a, b, c = f.get(k), h.get(k), r.get(k)
            flag = ""
            if a is None or b is None:
                flag = "only in the hierarchical sheet" if a is None else "MISSING"
                ok = ok and a is None
            elif k in WELL:
                same = abs(a - b) <= max(5e-3 * max(abs(a), abs(b)), 1e-3)
                flag = "yes - agree" if same else "yes - DIFFER"
                ok = ok and same
            else:
                flag = "no (solver-noise group)"
            fmt = lambda v: f"{v:12.5g}" if v is not None else f"{'-':>12s}"
            print(f"{k:10s} {fmt(a)} {fmt(b)} {fmt(c)}   {flag}")
        for name, log in (("flat", flog), ("hier", hlog)):
            m = re.search(r"Total elapsed time: ([\d.]+)", log)
            print(f"{name} run: {m.group(1) if m else '?'} s")
            for l in log.splitlines():
                if "shuffler_ctrl_dll2" in l:
                    print("    ", l.strip())
    if "--no-render" not in sys.argv:
        print("figures:", ", ".join(render_all()))
    print("RESULT:", "OK" if ok else "PROBLEMS")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
