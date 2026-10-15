#!/usr/bin/env python3
"""Read-only audit of a Simulink .slx (zip of XML) without MATLAB.

Dumps, for the MIL/SIL power-shuffler models:
  * the subsystem tree with block types and the parameters that matter for
    control (sample times, gains, filter constants, variant conditions),
  * every MATLAB Function body (stateflow/chart_*.xml),
  * the signal wiring of each subsystem (src block:port -> dst block:port),
  * solver settings from configSet0.xml.

Usage:
    python3 audit_mil.py <model.slx> [--out DIR]

Writes <DIR>/<model>_tree.txt, <DIR>/<model>_wiring.txt and
<DIR>/<model>_fn_<name>.m (one per MATLAB Function block). Nothing in the
.slx is modified.
"""
import argparse
import html
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

# Block parameters worth reporting (everything else is layout noise).
KEEP = {
    "SampleTime", "Gain", "Value", "Numerator", "Denominator", "InitialCondition",
    "VariantControl", "VariantControls", "LabelModeActiveChoice", "Inputs",
    "OutDataTypeStr", "VariableName", "MaskValueString", "SourceType",
    "UpperLimit", "LowerLimit", "DelayLength", "SampleTimeCheck", "Operator",
    "ComponentPath", "ComponentVariants", "FunctionName", "SourceFile",
    "CodeString", "OutputFunction", "Expression", "Port", "Element",
    "Function", "ShowPortLabels",
}


def text_of(p):
    return html.unescape(p.text or "")


def load(zf, name):
    with zf.open(name) as f:
        return ET.parse(f).getroot()


def block_params(blk):
    out = {}
    for p in blk.findall("P"):
        n = p.get("Name")
        if n in KEEP:
            out[n] = text_of(p).replace("\n", " ")
    # Simscape / masked blocks keep their values in InstanceData
    inst = blk.find("InstanceData")
    if inst is not None:
        for p in inst.findall("P"):
            v = text_of(p).replace("\n", " ")
            if len(v) < 80:
                out[p.get("Name")] = v
    return out


def walk(zf, sysname, path, depth, tree, wiring, max_depth):
    try:
        root = load(zf, f"simulink/systems/{sysname}.xml")
    except KeyError:
        tree.append("  " * depth + f"[missing {sysname}]")
        return
    sid2name = {}
    for blk in root.findall("Block"):
        name = blk.get("Name", "").replace("\n", " ")
        sid2name[blk.get("SID")] = name
        btype = blk.get("BlockType")
        ports = blk.find("PortCounts")
        pc = ""
        if ports is not None:
            pc = " ".join(f"{k}={v}" for k, v in ports.attrib.items())
        params = block_params(blk)
        ps = "; ".join(f"{k}={v}" for k, v in params.items())
        tree.append("  " * depth + f"- {name} <{btype}> {pc} {('{' + ps + '}') if ps else ''}")
        sub = blk.find("System")
        if sub is not None and depth < max_depth:
            walk(zf, sub.get("Ref"), f"{path}/{name}", depth + 1, tree, wiring, max_depth)
    lines = []
    for ln in root.iter("Line"):
        src = ln.find("P[@Name='Src']")
        dsts = [p for p in ln.iter("P") if p.get("Name") == "Dst"]
        if src is None:
            continue
        s = text_of(src)
        lab = ln.find("P[@Name='Name']")
        lab = f" \"{text_of(lab)}\"" if lab is not None else ""
        for d in dsts:
            lines.append((s, text_of(d), lab))

    def fmt(ep):
        m = re.match(r"(\d+)#(\w+):?(\w*)", ep)
        if not m:
            return ep
        return f"{sid2name.get(m.group(1), m.group(1))}.{m.group(2)}{m.group(3)}"

    if lines:
        wiring.append(f"\n## {path or '/'}")
        for s, d, lab in lines:
            wiring.append(f"  {fmt(s)} -> {fmt(d)}{lab}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("slx")
    ap.add_argument("--out", default="audit_out")
    ap.add_argument("--depth", type=int, default=4)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    stem = os.path.splitext(os.path.basename(a.slx))[0]
    zf = zipfile.ZipFile(a.slx)

    tree, wiring = [], []
    cfg = load(zf, "simulink/configSet0.xml")
    solver = {}
    for p in cfg.iter("P"):
        if p.get("Name") in ("Solver", "SolverType", "MaxStep", "FixedStep",
                             "RelTol", "AbsTol", "StopTime", "StartTime"):
            solver[p.get("Name")] = text_of(p)
    tree.append(f"# {stem}\nsolver: {solver}\n")
    walk(zf, "system_root", "", 0, tree, wiring, a.depth)

    with open(os.path.join(a.out, f"{stem}_tree.txt"), "w") as f:
        f.write("\n".join(tree) + "\n")
    with open(os.path.join(a.out, f"{stem}_wiring.txt"), "w") as f:
        f.write("\n".join(wiring) + "\n")

    nfn = 0
    for name in zf.namelist():
        if not re.match(r"simulink/stateflow/chart_\d+\.xml", name):
            continue
        root = load(zf, name)
        chart = root.find(".//P[@Name='name']")
        for sc in root.iter("P"):
            if sc.get("Name") == "script" and sc.text:
                body = text_of(sc)
                m = re.search(r"function\s+.*?=\s*(\w+)\s*\(", body)
                fn = m.group(1) if m else os.path.basename(name)
                with open(os.path.join(a.out, f"{stem}_fn_{fn}.m"), "w") as f:
                    f.write(f"% extracted from {name} ({text_of(chart) if chart is not None else ''})\n")
                    f.write(body)
                nfn += 1
    print(f"{stem}: {len(tree)} tree lines, {len(wiring)} wiring lines, {nfn} MATLAB Function bodies -> {a.out}/")


if __name__ == "__main__":
    sys.exit(main())
