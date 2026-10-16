#!/usr/bin/env python3
"""Switching-edge metrics for the S11 calibration stages, against the scope captures in 8_Results.

    python edge_metrics.py S11a [--svg]      -> table vs targets + results/S11a.edges.json (+ overlay SVGs)

Per switching edge (taken from the leg-A switch node of the converter that switches), on each probed node:
  burst   : peak |v - level| in the first 150 ns and its dominant frequency (FFT, > 20 MHz)
  ring    : the slower ring after the burst (v smoothed over 30 ns): frequency from extremum spacing,
            first positive / negative peak, Q from the log decrement of successive same-sign peaks,
            time for the envelope to fall below 10 % of its first peak
  overshoot (switch node only): max in the first 300 ns after a rising edge minus the settled high level
Medians over all edges in the saved window. Steps (.step fits) are reported side by side.
"""
import json
import os
import re
import sys

import numpy as np

import s10_metrics as sm

HERE = os.path.dirname(os.path.abspath(__file__))

# targets read from the captures (see ch.3 / plan): (node, metric, value, tolerance as a fraction)
TARGETS = {
    "S11a": [("v(pv3p)", "ring_f_MHz", 3.5, 0.15), ("v(pv3p)", "ring_pos", 1.6, 0.25), ("v(pv3p)", "ring_neg", -1.0, 0.3),
             ("v(pv3p)", "decay_us", 1.75, 0.3), ("v(pv3p)", "burst_pk", 1.5, 0.4), ("v(pv3p)", "burst_f_MHz", 55, 0.4)],
    "S11b": [("v(pv2p)", "ring_f_MHz", 4.0, 0.15), ("v(pv2p)", "ring_pos", 1.0, 0.3), ("v(pv2p)", "decay_us", 1.5, 0.3),
             ("v(pv2p)", "burst_pk", 1.3, 0.4), ("v(pv1p)", "ring_f_MHz", 4.5, 0.2), ("v(pv1p)", "decay_us", 1.0, 0.3)],
    "S11c": [("v(swa1)", "overshoot", 5.7, 0.25), ("v(swa1)", "ring_f_MHz", 4.5, 0.2)],
}
TARGETS["S11a_est"] = TARGETS["S11a"]
PROBES = {"S11a": ["v(pv3p)", "v(pv2p)"], "S11b": ["v(pv2p)", "v(pv1p)"], "S11c": ["v(swa1)", "v(pv1p)"]}
PROBES["S11a_est"] = PROBES["S11a"]
EDGE_REF = {"S11a": "v(swa2)", "S11b": "v(swa2)", "S11c": "v(swa1)", "S11a_est": "v(swa2)"}


def smooth(t, y, w):
    """moving average over w seconds on a non-uniform grid (resampled to 1 ns)"""
    tu = np.arange(t[0], t[-1], 1e-9)
    yu = np.interp(tu, t, y)
    n = max(1, int(round(w / 1e-9)))
    k = np.ones(n) / n
    return tu, np.convolve(yu, k, mode="same")


def edge_times(t, sw):
    mid = 0.5 * (np.max(sw) + np.min(sw))
    above = sw > mid
    idx = np.nonzero(above[1:] != above[:-1])[0]
    out = []
    for i in idx:
        out.append((t[i], bool(above[i + 1])))      # (time, rising)
    # drop chatter: keep edges at least 1 us apart
    clean = []
    for e in out:
        if not clean or e[0] - clean[-1][0] > 1e-6:
            clean.append(e)
    return clean


def metrics_window(t, v, te, t_next, is_sw=False, rising=True):
    m = (t >= te - 1.5e-6) & (t < t_next)
    tt, vv = t[m], v[m]
    if len(tt) < 50:
        return None
    tu, vu = smooth(tt, vv, 1e-9)                        # 1 ns uniform grid
    # settled level: a straight line fitted to the quiet tail (te + 2 us .. next edge), so the slow string
    # drift between edges is not mistaken for the ring
    q = (tu > te + 2.0e-6) & (tu < t_next - 0.2e-6)
    if q.sum() < 50:
        return None
    cf = np.polyfit(tu[q] - te, vu[q], 1)
    trend = np.polyval(cf, tu - te)
    lvl = float(np.polyval(cf, (t_next - te) - 0.5e-6))
    x = vu - trend
    r = {}
    b = (tu >= te) & (tu < te + 150e-9)
    if is_sw:
        r["overshoot"] = float(np.max(vu[(tu >= te) & (tu < te + 300e-9)]) - lvl) if rising else \
            float(np.min(vu[(tu >= te) & (tu < te + 300e-9)]) - lvl)
        r["level"] = float(lvl)
    # burst: HF part = x minus its 30 ns average
    xs = np.convolve(x, np.ones(30) / 30, mode="same")      # 30 ns moving average on the 1 ns grid
    hf = (x - xs)[b]
    r["burst_pk"] = float(np.max(np.abs(x[b]))) if b.any() else float("nan")
    if len(hf) > 16:
        w = np.hanning(len(hf))
        F = np.abs(np.fft.rfft(hf * w, n=4096))
        f = np.fft.rfftfreq(4096, 1e-9)
        sel = f > 20e6
        r["burst_f_MHz"] = float(f[sel][np.argmax(F[sel])] / 1e6)
    else:
        r["burst_f_MHz"] = float("nan")
    # ring: the 30 ns-smoothed deviation from the trend, from 60 ns (end of the fast edge) to 3 us
    rm = (tu >= te + 60e-9) & (tu < min(te + 3e-6, t_next - 0.2e-6))
    rt, ry = tu[rm], xs[rm]
    if len(ry) < 100:
        return r
    early = rt < te + 1.2e-6
    r["ring_pos"] = float(np.max(ry[early]))
    r["ring_neg"] = float(np.min(ry[early]))
    pk = max(abs(r["ring_pos"]), abs(r["ring_neg"]), 1e-9)
    d = np.diff(ry)
    ext = np.nonzero((d[:-1] > 0) != (d[1:] > 0))[0] + 1
    ext = [i for i in ext if abs(ry[i]) > 0.1 * pk]
    clean = []
    for i in ext:   # alternate signs only, keep the larger of same-sign neighbours
        if clean and np.sign(ry[i]) == np.sign(ry[clean[-1]]):
            if abs(ry[i]) > abs(ry[clean[-1]]):
                clean[-1] = i
            continue
        clean.append(i)
    if len(clean) >= 3:
        half = np.diff(rt[clean])
        r["ring_f_MHz"] = float(1 / (2 * np.median(half[:6])) / 1e6)
        amps = np.abs(ry[clean])
        same = amps[0::2]
        if len(same) >= 2:
            dec = np.log(same[:-1] / np.maximum(same[1:], 1e-12))
            dec = dec[np.isfinite(dec) & (dec > 0)]
            r["ring_Q"] = float(np.pi / np.median(dec)) if len(dec) else float("nan")
    env = np.abs(ry)
    late = np.nonzero(env > 0.1 * np.max(env))[0]
    r["decay_us"] = float((rt[late[-1]] - te) * 1e6) if len(late) else float("nan")
    return r


def analyse(stage):
    names, D = sm.read(os.path.join(HERE, "stages", stage + ".qraw"))
    col = {n.lower(): k for k, n in enumerate(names)}
    t_all = np.asarray(D[:, 0])
    starts = [0] + list(np.nonzero(np.diff(t_all) < 0)[0] + 1) + [len(t_all)]
    log = open(os.path.join(HERE, "results", stage + ".sim.txt"), encoding="utf-8", errors="replace").read()
    labels = [m.group(1).strip() for m in re.finditer(r"\d+ of \d+ steps:\s*\.step\s*(.*)", log)] or ["v3 values"]
    base = stage.split("_")[0] if stage.startswith("S11a") else stage
    out = []
    for s in range(len(starts) - 1):
        a, b = starts[s], starts[s + 1]
        t = t_all[a:b]
        ref = np.asarray(D[a:b, col[EDGE_REF[stage]]])
        edges = edge_times(t, ref)
        res = {"step": labels[s] if s < len(labels) else f"step {s + 1}", "n_edges": len(edges)}
        for node in PROBES[stage]:
            v = np.asarray(D[a:b, col[node]])
            rows = []
            for j in range(len(edges) - 1):
                te, rising = edges[j]
                if te - t[0] < 1.6e-6:
                    continue
                mtr = metrics_window(t, v, te, edges[j + 1][0], is_sw=node.startswith("v(sw"), rising=rising)
                if mtr:
                    mtr["rising"] = rising
                    rows.append(mtr)
            keys = sorted({k for r in rows for k in r if k != "rising"})
            med = {}
            for k in keys:
                if k == "overshoot":
                    vals = [r[k] for r in rows if r.get("rising") and k in r]
                else:
                    vals = [r[k] for r in rows if k in r and r[k] == r[k]]
                med[k] = float(np.median(vals)) if vals else float("nan")
            res[node] = med
        out.append(res)
    return out, labels


def main():
    stage = sys.argv[1]
    out, labels = analyse(stage)
    json.dump(out, open(os.path.join(HERE, "results", stage + ".edges.json"), "w"), indent=1)
    tg = TARGETS.get(stage, [])
    print(f"{stage}: {len(out)} step(s)")
    hdr = f"{'node':10s} {'metric':12s} {'target':>8s}" + "".join(f"{o['step'][:22]:>24s}" for o in out)
    print(hdr)
    for node, met, val, tol in tg:
        cells = []
        for o in out:
            v = o.get(node, {}).get(met, float("nan"))
            ok = abs(v - val) <= tol * abs(val) if v == v else False
            cells.append(f"{v:>20.3g} {'ok' if ok else '--'}")
        print(f"{node:10s} {met:12s} {val:>8.3g}" + "".join(f"{c:>24s}" for c in cells))
    print("\nall metrics per node (median over edges):")
    for o in out:
        print(" ", o["step"], {n: {k: round(v, 3) for k, v in o[n].items()} for n in PROBES[stage]})


if __name__ == "__main__":
    main()
