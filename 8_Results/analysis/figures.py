#!/usr/bin/env python3
"""Figure families of the results synthesis (all through figstyle: PDF + PNG under out/figures/<family>/).

    python3 figures.py --hardware [--only B06]      # per-case overview figures of the presentation test cases
"""
import argparse
import os

import numpy as np
import pandas as pd

import config
import figstyle as fs
import tidy
from phases import hardware as hw


def _gap_nan(df, tcol="t_utc", gap_s=1.0):
    """Insert a NaN row wherever consecutive samples are more than gap_s apart so lines break instead of bridging."""
    t = df[tcol]
    gaps = np.where(t.diff().dt.total_seconds().to_numpy() > gap_s)[0]
    if len(gaps) == 0:
        return df
    parts, last = [], 0
    for g in gaps:
        parts.append(df.iloc[last:g])
        nan = pd.DataFrame({c: [np.nan] for c in df.columns})
        nan[tcol] = [t.iloc[g - 1] + (t.iloc[g] - t.iloc[g - 1]) / 2]
        parts.append(nan)
        last = g
    parts.append(df.iloc[last:])
    out = pd.concat(parts, ignore_index=True)
    out[tcol] = pd.to_datetime(out[tcol], utc=True)
    return out


def case_title(spec, cid):
    loop = "open loop (duties fixed)" if spec["loop"] == "OL" else f"closed loop, kscale {spec['kscale']:g}"
    setup = "Bench" if spec["setup"] == "BENCH" else "Carpark PV"
    day = pd.Timestamp(spec["day"]).strftime("%d %b %Y")
    slide = f"slide {spec['slide']}" if spec["slide"] else "not on a slide"
    return f"{cid}: {setup}, {day}, {spec['f_khz']} kHz, {loop} ({slide})  —  {spec['start'][11:]} to {spec['stop'][11:]} local, RUN rows only"


EVENT_SHORT = {"close": "loop closed", "ol_start": "open loop", "kscale_apply": "kscale applied", "duty_step": "duty step",
               "load_step": "load step", "shade_on": "shade on", "shade_off": "shade off", "transient_on": "transient", "transient_off": "transient end",
               "mismatch_on": "mismatch on", "mismatch_off": "mismatch off", "irradiance_up": "irradiance up", "irradiance_down": "irradiance down",
               "fault": "FAULT", "vref": "reference step"}
MARK_KINDS = tuple(EVENT_SHORT)


def headroom(ax, frac=0.32):
    lo, hi = ax.get_ylim()
    ax.set_ylim(lo, hi + frac * (hi - lo))


def robust_ylim(ax, arrays, lo_q=0.5, hi_q=99.5, pad_frac=0.12, min_pad=0.0):
    vals = np.concatenate([np.asarray(a, float).ravel() for a in arrays if a is not None])
    vals = vals[np.isfinite(vals)]
    if len(vals) == 0:
        return
    lo, hi = np.percentile(vals, lo_q), np.percentile(vals, hi_q)
    pad = max(min_pad, pad_frac * (hi - lo))
    ax.set_ylim(lo - pad, hi + pad)


def mark_numbered(axes, label_ax, ev):
    """Numbered dashed event lines (e1, e2 ...) on every axis, numbers at the bottom of label_ax; returns the legend lines."""
    notes = []
    for n, (_, e) in enumerate(ev.iterrows(), 1):
        col = fs.EVENT_COL.get(e["kind"], "#000000")
        t = pd.Timestamp(e["time_utc"])
        for ax in axes:
            ax.axvline(t, color=col, lw=0.8, ls="--", alpha=0.75, zorder=1)
        label_ax.annotate(f"e{n}", (t, 0.01), xycoords=("data", "axes fraction"), fontsize=7.5, va="bottom", ha="left", color=col,
                          xytext=(2, 0), textcoords="offset points")
        detail = str(e.get("detail", ""))
        notes.append(f"e{n} {t.tz_convert(config.LOCAL_TZ):%H:%M:%S} {EVENT_SHORT.get(e['kind'], e['kind'])}" + (f" ({detail[:60]})" if detail and e["kind"] not in ("close", "fault") else ""))
    return notes


def hardware_overview(cid):
    w = hw.case(cid)
    spec = w["spec"]
    run = hw.run_frame(cid)
    info = w["run_info"]
    ev = w["events"]
    g = _gap_nan(run)
    t = g["t_utc"].to_numpy()
    long = len(run) > 9000
    fig, ax = fs.figure(rows=3, cols=2, width=12.5, height=8.6)
    (a_il, a_vm), (a_mode, a_vd), (a_d, a_el) = ax

    def tr(axis, col, key=None, **kw):
        if col not in g:
            return
        key = key or col
        y = g[col].to_numpy(float)
        if long:
            fs.trace(axis, t, y, fs.COL[key], fs.LABEL.get(key, key), raw_max=9000, **kw)
        else:                      # raw samples faint, 1 s rolling mean on top
            axis.plot(t, y, color=fs.COL[key], lw=0.6, alpha=0.3, **kw)
            mu = pd.Series(y, index=pd.DatetimeIndex(t)).rolling("1s", center=True).mean().to_numpy()
            axis.plot(t, mu, color=fs.COL[key], lw=1.2, label=fs.LABEL.get(key, key), **kw)

    for c in ("ILA1", "ILB1", "ILA2", "ILB2"):
        tr(a_il, c)
    a_il.set_title("Winding currents" + (" (1 s mean, min–max band)" if long else " (raw samples, 1 s mean)"))
    fs.ylabel(a_il, "Current", "A")
    robust_ylim(a_il, [run[c] for c in ("ILA1", "ILB1", "ILA2", "ILB2")], lo_q=0.1, hi_q=99.9, min_pad=0.05)
    fs.legend(a_il, ncol=4, loc="upper right")

    for c in ("id1", "id2"):
        tr(a_mode, c)
    for c in ("ic1", "ic2"):
        tr(a_mode, c, ls="--")
    a_mode.set_title("Shuffled i_sh (solid) and circulating i_c (dashed) currents")
    fs.ylabel(a_mode, "Current", "A")
    robust_ylim(a_mode, [run[c] for c in ("id1", "id2", "ic1", "ic2")], lo_q=0.1, hi_q=99.9, min_pad=0.05)
    fs.legend(a_mode, ncol=2, loc="upper right")

    for c in ("dA1", "dB1", "dA2", "dB2"):
        tr(a_d, c)
    a_d.set_title("Duty cycles")
    fs.ylabel(a_d, "Duty", "d")
    robust_ylim(a_d, [run[c] for c in ("dA1", "dB1", "dA2", "dB2")], min_pad=0.004)
    fs.legend(a_d, ncol=4, loc="upper right")

    vm1_lab = "V_M1 (e-load − V_M2 − V_M3)" if "invalid" in info.get("vm1_source", "") else "V_M1"
    tr(a_vm, "VM1")
    for h in a_vm.get_lines()[-1:]:
        h.set_label(vm1_lab)
    for c in ("VM2", "VM3"):
        tr(a_vm, c)
    a_vm.set_title("Module voltages")
    fs.ylabel(a_vm, "Voltage", "V")
    robust_ylim(a_vm, [run[c] for c in ("VM1", "VM2", "VM3")], min_pad=0.05)
    fs.legend(a_vm, ncol=3, loc="upper right")

    for c in ("vd1", "vd2"):
        tr(a_vd, c)
    a_vd.axhline(0, color="k", lw=0.6, alpha=0.5)
    a_vd.set_title("Voltage differences" + ("  (controlled, reference 0 V)" if spec["loop"] == "CL" else ""))
    fs.ylabel(a_vd, "Voltage", "V")
    robust_ylim(a_vd, [run[c] for c in ("vd1", "vd2")], min_pad=0.02)
    fs.legend(a_vd, ncol=2, loc="upper right")

    el = w["eload"]
    if len(el) and "p" in el:
        e = el.dropna(subset=["p"])
        e = e[(e["t_utc"] >= run["t_utc"].iat[0] - pd.Timedelta(seconds=1)) & (e["t_utc"] <= run["t_utc"].iat[-1] + pd.Timedelta(seconds=1))]
        a_el.plot(e["t_utc"], e["v"], color=fs.COL["Vel"], lw=1.0, label="V_string")
        a_el2 = a_el.twinx()
        a_el2.spines["right"].set_visible(True)
        a_el2.grid(False)
        a_el2.plot(e["t_utc"], e["i"], color=fs.COL["Istr"], lw=0.9, alpha=0.9, label="I_string")
        if "setpoint" in el:
            sp = el.dropna(subset=["setpoint"])
            sp = sp[(sp["t_utc"] >= e["t_utc"].iat[0]) & (sp["t_utc"] <= e["t_utc"].iat[-1])]
            mode = str(sp["mode"].mode().iat[0]) if "mode" in sp and len(sp) else ""
            if len(sp) and mode.upper().startswith("CV"):
                a_el.plot(sp["t_utc"], sp["setpoint"], color=fs.COL["setpoint"], lw=0.8, ls=":", label=f"set-point ({mode})")
            elif len(sp):
                a_el2.plot(sp["t_utc"], sp["setpoint"], color=fs.COL["setpoint"], lw=0.8, ls=":", label=f"set-point ({mode})")
        fs.ylabel(a_el, "Voltage", "V")
        a_el.yaxis.label.set_color(fs.COL["Vel"])
        a_el2.set_ylabel("Current [A]", color=fs.COL["Istr"])
        pmean = float(run["Pstr_i"].mean()) if "Pstr_i" in run else float(e["p"].mean())
        a_el.set_title(f"Electronic load (DL3021): string voltage, current; mean power {pmean:.1f} W")
        h1, l1 = a_el.get_legend_handles_labels()
        h2, l2 = a_el2.get_legend_handles_labels()
        a_el.legend(h1 + h2, l1 + l2, ncol=3, loc="upper right")
    else:
        a_el.set_title("Electronic load: no log in this window")

    segs = w["segments"]
    for axis in ax.ravel():
        fs.state_bands(axis, segs[segs["state"].isin(("RUN_OL", "RUN_CL"))], alpha=0.35)
        fs.time_axis(axis)
        headroom(axis)
    evr = ev[(ev["time_utc"] >= run["t_utc"].iat[0] - pd.Timedelta(seconds=0.5)) & (ev["time_utc"] <= run["t_utc"].iat[-1] + pd.Timedelta(seconds=2.0))]
    evr = evr[evr["kind"].isin(MARK_KINDS)]
    evr = evr[~((evr["kind"] == "load_step") & (evr["source"] == "detector") & (evr["detail"].str.contains("VM1 ", na=False) & ~evr["detail"].str.contains("VM2|VM3|Pstr|id2", na=False)))]
    notes = mark_numbered(ax.ravel(), a_il, evr)
    for axis in ax[-1]:
        axis.set_xlabel(f"Local time (AEST), {pd.Timestamp(spec['day']).strftime('%d %b %Y')}")
    fig.suptitle(case_title(spec, cid))
    foot = (f"{info['n_run_rows']} RUN frames at {info['rate_hz']:.0f} Hz; dropped {info['n_frozen_rows']} frozen and {info['n_collapse_rows']} start-up/shutdown frames; "
            f"VM1: {info['vm1_source']}; gain set {', '.join(p.replace('sps-params-2.', '') for p in info['pver_seen'])}")
    lines = [foot]
    for i in range(0, len(notes), 3):
        lines.append("   ".join(notes[i:i + 3]))
    fig.supxlabel("\n".join(lines[:4]), fontsize=7.3, color="#444444", ha="left", x=0.006, linespacing=1.3)
    return fs.save(fig, "hardware", f"{cid}_{spec['label']}_overview")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hardware", action="store_true")
    ap.add_argument("--events", action="store_true")
    ap.add_argument("--sims", help="comma list of analytical,qspice,simulink,validate")
    ap.add_argument("--only")
    a = ap.parse_args()
    if a.hardware:
        for cid in config.TEST_CASES:
            if a.only and a.only not in cid:
                continue
            print(cid, hardware_overview(cid))
    if a.events:
        for p in all_event_zooms(a.only):
            print(p)
    if a.sims:
        for p in all_sim_cases(tuple(a.sims.split(","))):
            print(p)



# ----------------------------------------------------------------------------- hardware event zooms
ZOOM = {"close": (-0.6, 3.0), "duty_step": (-2.0, 6.0), "load_step": (-3.0, 10.0), "mismatch_on": (-5.0, 20.0), "mismatch_off": (-5.0, 20.0),
        "irradiance_up": (-5.0, 20.0), "irradiance_down": (-5.0, 20.0), "kscale_apply": (-2.0, 5.0)}


def event_zoom(cid, e, n=0, metrics=None):
    """Three stacked panels (v_d, currents, load / duties) around one event of a test case; the grey part before a
    loop close is the SOFTSTART ramp (not RUN). metrics: rows of T3 for this event (annotated: y0, y_final, abs band)."""
    import figstyle as fs_
    w = hw.case(cid)
    spec = w["spec"]
    run = hw.run_frame(cid)
    tel = w["tel"]
    kind = e["kind"]
    pre, post = ZOOM.get(kind, (-3.0, 10.0))
    t_ev = pd.Timestamp(e["time_utc"])
    g = run[(run["t_utc"] >= t_ev + pd.Timedelta(seconds=pre)) & (run["t_utc"] <= t_ev + pd.Timedelta(seconds=post))]
    if len(g) < 4:
        return None
    tg = (g["t_utc"] - t_ev).dt.total_seconds().to_numpy()
    fig, ax = fs_.figure(rows=3, cols=1, width=10, height=8.2)
    a_vd, a_i, a_x = ax
    if kind == "close":                                       # show the soft-start ramp greyed for context
        ramp = tel[(tel["t_utc"] >= t_ev + pd.Timedelta(seconds=pre)) & (tel["t_utc"] < t_ev) & (tel["state"].isin(("SOFTSTART", "IDLE", "RUN_OL")))]
        if len(ramp):
            tr_ = (ramp["t_utc"] - t_ev).dt.total_seconds().to_numpy()
            for c in ("vd1", "vd2"):
                a_vd.plot(tr_, ramp[c], color="#999999", lw=0.8, alpha=0.7, label=None)
            for c in ("id1", "id2"):
                a_i.plot(tr_, ramp[c], color="#999999", lw=0.8, alpha=0.7)
            for axis in ax:
                axis.axvspan(tr_[0], 0, color=fs_.STATE_COL["SOFTSTART"], alpha=0.5, lw=0, zorder=0)
            a_vd.text(tr_[0], 0.98, " SOFTSTART ramp (not RUN)", transform=a_vd.get_xaxis_transform(), fontsize=8, va="top", color="#7a5a00")
    for c in ("vd1", "vd2"):
        a_vd.plot(tg, g[c], color=fs_.COL[c], lw=0.9, alpha=0.5)
        mu = pd.Series(g[c].to_numpy(float), index=pd.DatetimeIndex(g["t_utc"])).rolling("500ms", center=True).mean().to_numpy()
        a_vd.plot(tg, mu, color=fs_.COL[c], lw=1.4, label=fs_.LABEL[c] + " (0.5 s mean)")
    a_vd.axhline(0, color="k", lw=0.6, alpha=0.5)
    if metrics is not None and len(metrics):
        for sig, col in (("vd2", fs_.COL["vd2"]), ("vd1", fs_.COL["vd1"])):
            m = metrics[metrics["signal"] == sig]
            if m.empty:
                continue
            m = m.iloc[0]
            if np.isfinite(m.get("y_final", np.nan)):
                a_vd.axhline(m["y_final"], color=col, lw=0.7, ls=":", alpha=0.8)
            if np.isfinite(m.get("band_abs", np.nan)) and np.isfinite(m.get("y_final", np.nan)):
                a_vd.axhspan(m["y_final"] - m["band_abs"], m["y_final"] + m["band_abs"], color=col, alpha=0.06, lw=0)
            if np.isfinite(m.get("t_settle_abs", np.nan)):
                a_vd.axvline(m["t_settle_abs"], color=col, lw=0.7, ls="-.", alpha=0.7)
    fs_.ylabel(a_vd, "Voltage difference", "V")
    a_vd.set_title("Voltage differences v_d1, v_d2" + ("  (reference 0 V; dotted = final level, band = ±abs band, dash-dot = time into band)" if spec["loop"] == "CL" else ""))
    fs_.legend(a_vd, ncol=2)
    for c in ("id1", "id2"):
        a_i.plot(tg, g[c], color=fs_.COL[c], lw=0.8, alpha=0.4)
        mu = pd.Series(g[c].to_numpy(float), index=pd.DatetimeIndex(g["t_utc"])).rolling("500ms", center=True).mean().to_numpy()
        a_i.plot(tg, mu, color=fs_.COL[c], lw=1.4, label=fs_.LABEL[c])
    for c in ("ic1", "ic2"):
        mu = pd.Series(g[c].to_numpy(float), index=pd.DatetimeIndex(g["t_utc"])).rolling("500ms", center=True).mean().to_numpy()
        a_i.plot(tg, mu, color=fs_.COL[c], lw=1.1, ls="--", label=fs_.LABEL[c])
    fs_.ylabel(a_i, "Current", "A")
    a_i.set_title("Shuffled i_sh (solid) and circulating i_c (dashed), 0.5 s means over raw samples")
    fs_.legend(a_i, ncol=2)
    if kind in ("duty_step", "kscale_apply", "close"):
        for c in ("dA1", "dB1", "dA2", "dB2"):
            a_x.plot(tg, g[c], color=fs_.COL[c], lw=1.0, label=fs_.LABEL[c])
        fs_.ylabel(a_x, "Duty", "d")
        a_x.set_title("Duty cycles")
        robust_ylim(a_x, [g[c] for c in ("dA1", "dB1", "dA2", "dB2")], min_pad=0.003)
    else:
        if "Istr_i" in g and g["Istr_i"].notna().any():
            a_x.plot(tg, g["Istr_i"], color=fs_.COL["Istr"], lw=1.2, label="I_string (e-load)")
            a_x2 = a_x.twinx()
            a_x2.spines["right"].set_visible(True)
            a_x2.grid(False)
            a_x2.plot(tg, g["Pstr_i"], color=fs_.COL["Pstr"], lw=1.2, label="P_string (e-load)")
            a_x2.set_ylabel("Power [W]", color=fs_.COL["Pstr"])
            for k in (1, 2, 3):
                mu = pd.Series(g[f"IM{k}"].to_numpy(float), index=pd.DatetimeIndex(g["t_utc"])).rolling("1s", center=True).mean().to_numpy()
                a_x.plot(tg, mu, color=fs_.COL[f"IM{k}"], lw=1.0, ls="--", label=f"I_M{k} (KCL, 1 s mean)")
            fs_.ylabel(a_x, "Current", "A")
            a_x.yaxis.label.set_color(fs_.COL["Istr"])
            a_x.set_title("String current and power (e-load), module currents rebuilt by KCL")
            h1, l1 = a_x.get_legend_handles_labels()
            h2, l2 = a_x2.get_legend_handles_labels()
            a_x.legend(h1 + h2, l1 + l2, ncol=3, loc="upper right")
            headroom(a_x2)
    for axis in ax:
        axis.axvline(0, color="k", lw=0.9, ls="--")
        headroom(axis, 0.25)
    a_x.set_xlabel("Time from event [s]")
    detail = str(e.get("detail", ""))[:90]
    fig.suptitle(f"{cid} e{n}: {EVENT_SHORT.get(kind, kind)} at {t_ev.tz_convert(config.LOCAL_TZ):%H:%M:%S} — {case_title(spec, cid).split('  —  ')[0].split(': ', 1)[1]}")
    fig.supxlabel(f"{detail}   |   telemetry {w['run_info']['rate_hz']:.0f} Hz: times shorter than one sample ({1e3 / w['run_info']['rate_hz']:.0f} ms) are not resolved",
                  fontsize=8, color="#444444", ha="left", x=0.006)
    return fs_.save(fig, "events", f"{cid}_e{n}_{kind}")


def all_event_zooms(only=None):
    import hwmetrics
    T3 = pd.read_csv(os.path.join(config.OUT, "tables", "T3_hw_events.csv")) if os.path.exists(os.path.join(config.OUT, "tables", "T3_hw_events.csv")) else pd.DataFrame()
    out = []
    for cid in config.TEST_CASES:
        if only and only not in cid:
            continue
        w = hw.case(cid)
        run = hw.run_frame(cid)
        ev = w["events"]
        ev = ev[(ev["time_utc"] >= run["t_utc"].iat[0] - pd.Timedelta(seconds=0.5)) & (ev["time_utc"] <= run["t_utc"].iat[-1] + pd.Timedelta(seconds=2.0))]
        ev = ev[ev["kind"].isin(MARK_KINDS)]
        ev = ev[~((ev["kind"] == "load_step") & (ev["source"] == "detector") & (ev["detail"].str.contains("VM1 ", na=False) & ~ev["detail"].str.contains("VM2|VM3|Pstr|id2", na=False)))]
        cmd_times = [pd.Timestamp(t) for t in ev.loc[ev["kind"].isin(("duty_step", "kscale_apply")), "time_utc"]]
        for n, (_, e) in enumerate(ev.iterrows(), 1):
            if e["kind"] not in ZOOM:
                continue
            if e["kind"] == "load_step" and e.get("source") == "detector" and any(abs((pd.Timestamp(e["time_utc"]) - tc).total_seconds()) < 4 for tc in cmd_times):
                continue
            m = T3[(T3["cid"] == cid) & (T3["event"] == e["kind"]) & (T3["time_local"] == pd.Timestamp(e["time_utc"]).tz_convert(config.LOCAL_TZ).strftime("%H:%M:%S"))] if len(T3) else None
            p = event_zoom(cid, e, n, m)
            if p:
                out.append(p)
    return out



# ----------------------------------------------------------------------------- simulation cases (one figure per run)
def _zoom_window(f, sig="vd2", tau_hint=None):
    """x-range of the zoom panel: about six closed-loop time constants after the event, or the first 12 ms."""
    t = f["t"].to_numpy()
    k = f.attrs.get("kscale") or 1.0
    tau = tau_hint or 1.0 / (max(k, 1e-3) * config.KI_V)
    t1 = min(t[-1], max(6 * tau, 0.012))
    t0 = max(t[0], -0.1 * t1) if t[0] < 0 else t[0]
    return t0, t1


def sim_case(f, family, name, title=None, refs=None):
    """Simulation / analytical run: v_d (+ refs), i_sh & i_c, duties, module voltages & string power; full view (left)
    and zoom (right) on a ms axis. refs = {sig: value} draws dotted reference lines."""
    import figstyle as fs_
    a = f.attrs
    t = f["t"].to_numpy() * 1e3
    z0, z1 = _zoom_window(f)
    z0, z1 = z0 * 1e3, z1 * 1e3
    nmod = int(a.get("n_mod") or 3)
    ns = nmod - 1
    fig, ax = fs_.figure(rows=4, cols=2, width=12.5, height=10.5, sharex=False)
    for col, (lo, hi, lab) in enumerate(((t[0], t[-1], "full run"), (z0, z1, "zoom"))):
        m = (t >= lo) & (t <= hi)
        a_vd, a_i, a_d, a_vm = ax[:, col]
        for j in range(1, ns + 1):
            c = f"vd{j}"
            if c in f and f[c].notna().any():
                a_vd.plot(t[m], f[c].to_numpy(float)[m], color=fs_.COL.get(c, "k"), lw=1.2, label=fs_.LABEL.get(c, c))
                if refs and c in refs and refs[c] is not None:
                    a_vd.axhline(refs[c], color=fs_.COL.get(c, "k"), lw=0.8, ls=":", alpha=0.8)
        a_vd.axhline(0, color="k", lw=0.5, alpha=0.4)
        a_vd.set_title(f"Voltage differences v_d ({lab})" + ("; dotted = reference" if refs else ""))
        fs_.ylabel(a_vd, "Voltage", "V")
        fs_.legend(a_vd, ncol=3)
        for j in range(1, ns + 1):
            c = f"id{j}"
            if c in f and f[c].notna().any():
                a_i.plot(t[m], f[c].to_numpy(float)[m], color=fs_.COL.get(c, "k"), lw=1.2, label=fs_.LABEL.get(c, c))
            c = f"ic{j}"
            if c in f and f[c].notna().any():
                a_i.plot(t[m], f[c].to_numpy(float)[m], color=fs_.COL.get(c, "k"), lw=1.0, ls="--", label=fs_.LABEL.get(c, c))
        a_i.set_title(f"Shuffled i_sh (solid) and circulating i_c (dashed) ({lab})")
        fs_.ylabel(a_i, "Current", "A")
        fs_.legend(a_i, ncol=3)
        for j in range(1, ns + 1):
            for leg in ("A", "B"):
                c = f"d{leg}{j}"
                if c in f and f[c].notna().any():
                    a_d.plot(t[m], f[c].to_numpy(float)[m], color=fs_.COL.get(c, "k"), lw=1.0, label=fs_.LABEL.get(c, c))
        a_d.set_title(f"Duty cycles ({lab})")
        fs_.ylabel(a_d, "Duty", "d")
        robust_ylim(a_d, [f[c] for c in f.columns if c[:2] in ("dA", "dB") and f[c].notna().any()], lo_q=0, hi_q=100, min_pad=0.003)
        fs_.legend(a_d, ncol=3)
        has_vm = any(f"VM{k}" in f and f[f"VM{k}"].notna().any() for k in range(1, nmod + 1))
        if has_vm:
            for k in range(1, nmod + 1):
                c = f"VM{k}"
                if c in f and f[c].notna().any():
                    a_vm.plot(t[m], f[c].to_numpy(float)[m], color=fs_.COL.get(c, "k"), lw=1.1, label=fs_.LABEL.get(c, c))
            fs_.ylabel(a_vm, "Module voltage", "V")
            robust_ylim(a_vm, [f[f"VM{k}"] for k in range(1, nmod + 1) if f"VM{k}" in f], lo_q=0.2, hi_q=99.8, min_pad=0.2)
            ttl = "Module voltages"
            if "Pstr" in f and f["Pstr"].notna().any():
                a2 = a_vm.twinx()
                a2.spines["right"].set_visible(True)
                a2.grid(False)
                a2.plot(t[m], f["Pstr"].to_numpy(float)[m], color=fs_.COL["Pstr"], lw=1.0, label="P_string")
                a2.set_ylabel("String power [W]", color=fs_.COL["Pstr"])
                robust_ylim(a2, [f["Pstr"]], lo_q=0.5, hi_q=99.5, min_pad=1.0)
                headroom(a2, 0.3)
                ttl += " and string power"
                h1, l1 = a_vm.get_legend_handles_labels()
                h2, l2 = a2.get_legend_handles_labels()
                a_vm.legend(h1 + h2, l1 + l2, ncol=4, loc="upper right")
            else:
                fs_.legend(a_vm, ncol=4)
            a_vm.set_title(f"{ttl} ({lab})")
        else:
            a_vm.set_title("Module voltages: not in this run")
        a_vm.set_xlabel("Time from event [ms]" if t[0] < 0 else "Time [ms]")
        for axis in ax[:, col]:
            axis.axvline(0, color="k", lw=0.8, ls="--", alpha=0.7)
            axis.set_xlim(lo, hi)
            headroom(axis, 0.3)
    ps = fs_.phase_style(a.get("phase"))
    fig.suptitle(title or f"{ps['label']}: {a.get('scenario', '')} {a.get('event', '')} — {a.get('setup', '')}, kscale {a.get('kscale')}")
    return fs_.save(fig, family, name)


def _refs_of(f):
    a = f.attrs
    if a.get("scenario") == "S4":
        return {"vd1": 0.0, "vd2": 1.0}
    if a.get("scenario") in ("S1", "S3"):
        return {"vd1": 0.0, "vd2": 0.0}
    if "rv" in a:
        return {f"vd{j + 1}": v for j, v in enumerate(a["rv"])}
    return None


def all_sim_cases(which=("analytical", "qspice", "simulink", "validate")):
    import importlib
    out = []
    if "analytical" in which:
        an = importlib.import_module("phases.analytical")
        for scen in ("S1", "S3", "S4", "S5"):
            for f in an.cases(scen, f_khz=(200, 300, 400) if scen != "S5" else (200,)):
                a = f.attrs
                if scen != "S5" and a["kscale"] not in (0.1, 0.3, 1.0):
                    continue
                if scen != "S5" and a.get("f_khz") != 200 and a["kscale"] != 0.3:
                    continue
                nm = f"{scen}_{a['setup']}_f{a.get('f_khz')}k_k{a['kscale']:g}" + (f"_{a.get('event','').split(': ')[-1].replace(' ', '').replace('=', '')}" if scen == "S5" else "")
                out.append(sim_case(f, "analytical", nm, refs=_refs_of(f),
                                    title=f"Analytical N=3 ({a.get('f_khz')} kHz gain set, R = {a.get('R_ohm')} Ω): {config.SCENARIOS.get(scen, {}).get('name', scen)} — {a['setup']}, kscale {a['kscale']:g}: {a.get('event','')}"))
    if "qspice" in which:
        qs = importlib.import_module("phases.qspice")
        for scen in ("S1", "S3", "S4"):
            for f in qs.cases(scen):
                a = f.attrs
                out.append(sim_case(f, "qspice", f"{scen}_{a['setup']}_k{a['kscale']:g}", refs=_refs_of(f),
                                    title=f"QSPICE switching plant + firmware DLL (200 kHz): {config.SCENARIOS[scen]['name']} — {a['setup']}, kscale {a['kscale']:g} ({a.get('source')}, {a.get('event')})"))
    if "simulink" in which:
        sl = importlib.import_module("phases.simulink")
        for scen in ("S1", "S3", "S4"):
            for f in sl.cases(scen):
                a = f.attrs
                out.append(sim_case(f, "carpark", f"{scen}_{a['setup']}_k{a['kscale']:g}", refs=_refs_of(f),
                                    title=f"Simulink carpark twin (3 modules, averaged, 61 mΩ): {config.SCENARIOS[scen]['name']} — {a['setup']}, kscale {a['kscale']:g} ({a.get('source')})"))
    if "validate" in which:
        va = importlib.import_module("phases.validate")
        for wh, fam, lab in (("carpark", "carpark_validate", "Carpark validate suite (3 modules)"), ("mil", "mil_validate", "MIL validate suite (4 modules)")):
            for f in va.tests(wh):
                a = f.attrs
                out.append(sim_case(f, fam, a["source"], refs=_refs_of(f),
                                    title=f"{lab}: {a['test']} — last module {a['irrN']} W/m², refs {a['rv']}, {a['mode']}, {'PASS' if a['passed'] else 'CHECK'}; cold start, kscale 1"))
    return out



# ----------------------------------------------------------------------------- cross-phase comparison figures
def _hw_cases_for(scen, setup, kscale, signal):
    """Hardware samples around the events that match a simulated scenario (T3 rows -> cut from the cleaned frames)."""
    import hwmetrics
    inv = {"S1": "close", "S3": "mismatch_on", "S5": "duty_step"}
    kind = inv.get(scen)
    if kind is None:
        return []
    out = []
    for cid, spec in config.TEST_CASES.items():
        if spec["setup"] != setup:
            continue
        if scen != "S5" and (spec["kscale"] is None or abs(spec["kscale"] - kscale) > 1e-6):
            continue
        if scen == "S5" and spec["loop"] != "OL":
            continue
        w = hw.case(cid)
        run = hw.run_frame(cid)
        for _, e in w["events"][w["events"]["kind"] == kind].iterrows():
            t_ev = pd.Timestamp(e["time_utc"])
            pre, post = hwmetrics.EVENT_SPEC[kind][1][0] - 0.5, hwmetrics.EVENT_SPEC[kind][2]
            g = run[(run["t_utc"] >= t_ev + pd.Timedelta(seconds=pre)) & (run["t_utc"] <= t_ev + pd.Timedelta(seconds=post))]
            if len(g) < 4 or signal not in g:
                continue
            out.append(((g["t_utc"] - t_ev).dt.total_seconds().to_numpy(), g[signal].to_numpy(float), f"{cid} {t_ev.tz_convert(config.LOCAL_TZ):%H:%M:%S}", spec))
    return out


def compare_step(frames, scen, setup, kscale, sig, T5=None):
    """Simulations of one (scenario, setup, kscale) overlaid on a ms axis, with a zoom; hardware samples (if any) on a
    separate seconds axis underneath, because 45 Hz telemetry cannot be drawn on the simulation's millisecond scale."""
    import figstyle as fs_
    sel = [f for f in frames if f.attrs.get("scenario") == scen and f.attrs.get("setup") == setup
           and abs((f.attrs.get("kscale") or 0.0) - kscale) < 1e-6 and sig in f and f[sig].notna().sum() > 3
           and (f.attrs.get("f_khz", 200) == 200 or f.attrs.get("phase") != "analytical")]
    hwc = _hw_cases_for(scen, setup, kscale, sig)
    if not sel and not hwc:
        return None
    rows = 2 if hwc else 1
    fig, ax = fs_.figure(rows=rows, cols=2, width=12.5, height=4.2 * rows + 0.8, sharex=False)
    ax = np.atleast_2d(ax)
    a_full, a_zoom = ax[0]
    tau = 1.0 / (max(kscale, 0.05) * config.KI_V)
    for f in sel:
        a = f.attrs
        ps = fs_.phase_style(a["phase"])
        t = f["t"].to_numpy() * 1e3
        y = f[sig].to_numpy(float)
        lab = ps["label"] + (f" ({a.get('f_khz')} kHz R {a.get('R_ohm')} Ω)" if a["phase"] == "analytical" else "")
        for axis in (a_full, a_zoom):
            axis.plot(t, y, color=ps["color"], lw=1.4, label=lab)
    ref = {"S4": 1.0, "S1": 0.0}.get(scen) if sig in ("vd1", "vd2", "ic1", "ic2") else None
    if scen == "S4" and sig != "vd2":
        ref = 0.0
    for axis in (a_full, a_zoom):
        if ref is not None:
            axis.axhline(ref, color="k", lw=0.8, ls=":", label="reference" if axis is a_full else None)
        axis.axvline(0, color="k", lw=0.8, ls="--", alpha=0.7)
        fs_.ylabel(axis, tidy.SIGNAL_LABELS.get(sig, sig).split(" [")[0], "V" if sig.startswith(("vd", "VM")) else ("W" if sig == "Pstr" else "A"))
        axis.set_xlabel("Time from event [ms]")
        headroom(axis, 0.3)
    tmax = max((f["t"].iat[-1] for f in sel), default=0.05) * 1e3
    a_full.set_xlim(-2, tmax)
    a_zoom.set_xlim(-0.5, min(tmax, max(6 * tau * 1e3, 5)))
    a_full.set_title("Simulations and analysis (full run)")
    a_zoom.set_title(f"Zoom: 6 closed-loop time constants (design tau = {tau * 1e3:.2f} ms at kscale {kscale:g})")
    fs_.legend(a_full, ncol=1, loc="best")
    if hwc:
        a_hw, a_hwz = ax[1]
        cmap = plt_cmap()
        for i, (t, y, lab, spec) in enumerate(hwc[:8]):
            col = cmap(i % 10)
            for axis in (a_hw, a_hwz):
                axis.plot(t, y, ".", ms=4, color=col, alpha=0.8, label=f"{lab} (f_sw {spec['f_khz']} kHz)")
        for axis in (a_hw, a_hwz):
            if ref is not None:
                axis.axhline(ref, color="k", lw=0.8, ls=":")
            axis.axvline(0, color="k", lw=0.8, ls="--", alpha=0.7)
            fs_.ylabel(axis, tidy.SIGNAL_LABELS.get(sig, sig).split(" [")[0], "V" if sig.startswith(("vd", "VM")) else ("W" if sig == "Pstr" else "A"))
            axis.set_xlabel("Time from event [s]")
            headroom(axis, 0.3)
        a_hw.set_title(f"Hardware, same scenario ({config.SETUP_STYLE[setup]['label']}): telemetry samples at ~45 Hz")
        a_hwz.set_title("Hardware zoom: the loop's own transient is shorter than one sample")
        a_hwz.set_xlim(-0.3, max(1.0, 6 * tau * 4))
        fs_.legend(a_hw, ncol=1, loc="best")
    scen_name = config.SCENARIOS.get(scen, {}).get("name", scen)
    fig.suptitle(f"{scen} {scen_name}: {tidy.SIGNAL_LABELS.get(sig, sig)} — {setup}, kscale {kscale:g}")
    return fs_.save(fig, "compare", f"step_{scen}_{setup}_k{kscale:g}_{sig}")


def plt_cmap():
    import matplotlib.pyplot as plt
    return plt.get_cmap("tab10")


def compare_duty_step(frames):
    """S5: the open-loop common-duty steps on the bench (16 Oct 15:09-15:16) against the analytical model."""
    import figstyle as fs_
    import hwmetrics
    an = [f for f in frames if f.attrs.get("scenario") == "S5"]
    if not an:
        return None
    w = hw.case("B01s")
    run = hw.run_frame("B01s")
    ev = w["events"][w["events"]["kind"] == "duty_step"]
    fig, ax = fs_.figure(rows=2, cols=3, width=13, height=7.2, sharex=False)
    names = ["uc2 +0.04", "uc1 = uc2 = -0.02", "uc1 +0.04"]
    hw_ev = []
    for _, e in ev.iterrows():
        line = str(e["detail"])
        if "0.5,0.5,0.51,0.51" in line:
            hw_ev.append(("uc2 +0.04", e))
        elif "0.49,0.49,0.50,0.50" in line and not any(n == "uc1 = uc2 = -0.02" for n, _ in hw_ev):
            hw_ev.append(("uc1 = uc2 = -0.02", e))
        elif "0.51,0.51,0.50,0.50" in line:
            hw_ev.append(("uc1 +0.04", e))
    for col, name in enumerate(names):
        a_an, a_hw = ax[0, col], ax[1, col]
        f = next((f for f in an if name in f.attrs.get("event", "")), None)
        if f is not None:
            t = f["t"].to_numpy() * 1e3
            for i, sig in enumerate(("vd1", "vd2")):
                a_an.plot(t, f[sig], color=fs_.COL[sig], lw=1.4, label=fs_.LABEL[sig])
                a_an.annotate(f"Δ{fs_.LABEL[sig].split(' =')[0]} = {float(f[sig].iloc[-1] - f[sig].iloc[0]):+.2f} V (predicted)", (0.02, 0.95 - 0.09 * i), xycoords="axes fraction",
                              ha="left", va="top", fontsize=8.5, color=fs_.COL[sig])
            a_an.set_xlim(-0.5, 3)
        a_an.set_title(f"Analytical, open loop: {name}\n(bench plant 23.3 V/channel, R = 0.29 Ω)")
        a_an.set_xlabel("Time from step [ms]")
        fs_.ylabel(a_an, "Voltage difference", "V")
        e = next((e for n, e in hw_ev if n == name), None)
        if e is not None:
            t_ev = pd.Timestamp(e["time_utc"])
            g = run[(run["t_utc"] >= t_ev - pd.Timedelta(seconds=3)) & (run["t_utc"] <= t_ev + pd.Timedelta(seconds=6))]
            tg = (g["t_utc"] - t_ev).dt.total_seconds().to_numpy()
            for sig in ("vd1", "vd2"):
                a_hw.plot(tg, g[sig], ".", ms=3, color=fs_.COL[sig], alpha=0.5)
                mu = pd.Series(g[sig].to_numpy(float), index=pd.DatetimeIndex(g["t_utc"])).rolling("500ms", center=True).mean().to_numpy()
                a_hw.plot(tg, mu, color=fs_.COL[sig], lw=1.4, label=fs_.LABEL[sig] + " (0.5 s mean)")
            legs = str(e["detail"]).split(",")[2:]
            a_hw.set_title(f"Bench 16 Oct {t_ev.tz_convert(config.LOCAL_TZ):%H:%M:%S}: S1 legs {legs[0]}/{legs[1]}, S2 legs {legs[2]}/{legs[3]}\n(200 kHz, 40 Hz telemetry)")
            for i, sig in enumerate(("vd1", "vd2")):
                pre_ = g[(tg < -0.3)][sig].median(); post_ = g[(tg > 1.5)][sig].median()
                a_hw.annotate(f"Δ{fs_.LABEL[sig].split(' =')[0]} = {post_ - pre_:+.2f} V (measured)", (0.02, 0.95 - 0.09 * i), xycoords="axes fraction",
                              ha="left", va="top", fontsize=8.5, color=fs_.COL[sig])
        a_hw.set_xlabel("Time from command [s]")
        fs_.ylabel(a_hw, "Voltage difference", "V")
        for axis in (a_an, a_hw):
            axis.axvline(0, color="k", lw=0.8, ls="--", alpha=0.7)
            axis.axhline(0, color="k", lw=0.5, alpha=0.4)
            headroom(axis, 0.3)
            fs_.legend(axis, ncol=1, loc="lower right")
    fig.suptitle("S5 open-loop common-duty steps: analytical prediction Δv_d = −V̄·u_c (top) against the 16 Oct bench (bottom)")
    return fs_.save(fig, "compare", "S5_duty_steps_hw_vs_analytical")


def compare_metrics_vs_kscale(T4, HW=None):
    """tau / rise / settle / overshoot of the v_d2 response to the +1 V reference step (S4) vs kscale, per phase
    (colour) and setup (marker), with the first-order design line and the hardware sampling bound."""
    import figstyle as fs_
    from matplotlib.lines import Line2D
    from matplotlib.ticker import NullFormatter, FixedLocator
    sims = T4[(T4["signal"] == "vd2") & (T4["scenario"] == "S4") & ((T4["f_khz"] == 200) | T4["f_khz"].isna()) & (T4["delta"].abs() > 0.1)]
    if sims.empty:
        return None
    ks = np.array([0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 1.5])
    fig, ax = fs_.figure(rows=2, cols=2, width=12.5, height=8.2, sharex=False)
    panels = [("tau", "Fitted time constant τ [ms]", lambda r: r["tau"] * 1e3), ("rise_10_90", "Rise time 10–90 % [ms]", lambda r: r["rise_10_90"] * 1e3),
              ("t_settle_2", "Settling time, 2 % band [ms]", lambda r: r["t_settle_2"] * 1e3), ("overshoot_pct", "Overshoot [%]", lambda r: r["overshoot_pct"] if r.get("has_overshoot") else 0.0)]
    mk = {"PV80": "o", "BENCH": "s"}
    for axis, (key, lab, fn) in zip(ax.ravel(), panels):
        for ph in ("analytical", "simulink", "qspice"):
            for setup in ("PV80", "BENCH"):
                g = sims[(sims["phase"] == ph) & (sims["setup"] == setup)].sort_values("kscale")
                if g.empty:
                    continue
                vals = [fn(r) for _, r in g.iterrows()]
                axis.plot(g["kscale"], vals, "-" if setup == "PV80" else "--", marker=mk[setup], ms=6, color=fs_.phase_style(ph)["color"], lw=1.1)
        if key in ("tau", "rise_10_90", "t_settle_2"):
            factor = {"tau": 1.0, "rise_10_90": 2.197, "t_settle_2": 3.912}[key]
            axis.plot(ks, factor * 1e3 / (ks * config.KI_V), "k:", lw=1.3)
            axis.set_yscale("log")
        if HW is not None and len(HW) and key in ("rise_10_90", "t_settle_2"):
            h = HW[(HW["signal"] == "vd2") & (HW["scenario"] == "S1")]
            for setup in ("BENCH", "PV80"):
                hh = h[h["setup"] == setup]
                if hh.empty:
                    continue
                dt = hh["dt_median"].median() * 1e3
                axis.plot(sorted(set(hh["kscale"].round(3))), [dt] * len(set(hh["kscale"].round(3))), "v" if setup == "BENCH" else "^", ms=8,
                          color=config.SETUP_STYLE[setup]["color"], alpha=0.85)
        axis.set_xscale("log")
        axis.xaxis.set_major_locator(FixedLocator([0.1, 0.2, 0.3, 0.5, 1.0]))
        axis.set_xticklabels(["0.1", "0.2", "0.3", "0.5", "1"])
        axis.xaxis.set_minor_formatter(NullFormatter())
        axis.set_xlabel("kscale (gain scale)")
        axis.set_ylabel(lab)
        axis.set_title(lab.split(" [")[0] + " of v_d2, +1 V reference step")
    handles = [Line2D([], [], color=fs_.phase_style(ph)["color"], lw=1.5, label=fs_.phase_style(ph)["label"]) for ph in ("analytical", "simulink", "qspice")]
    handles += [Line2D([], [], color="#333333", marker="o", ls="-", label="PV80 (3 x 80 W panels)"), Line2D([], [], color="#333333", marker="s", ls="--", label="BENCH (3 PSU channels in current limit)"),
                Line2D([], [], color="k", ls=":", lw=1.3, label="design: first order, kI = 2π·150 rad/s"),
                Line2D([], [], color=config.SETUP_STYLE["BENCH"]["color"], marker="v", ls="none", ms=8, label="hardware bench, loop close: ≤ one telemetry sample (23 ms) — upper bound"),
                Line2D([], [], color=config.SETUP_STYLE["PV80"]["color"], marker="^", ls="none", ms=8, label="hardware carpark PV, loop close: ≤ one telemetry sample — upper bound")]
    fig.legend(handles=handles, loc="outside lower center", ncol=3, fontsize=8.5, frameon=False)
    fig.suptitle("Closed-loop step metrics of v_d2 vs gain scale (200 kHz gain set); hardware cannot resolve the loop's own transient")
    return fs_.save(fig, "compare", "metrics_vs_kscale")


def compare_ripple():
    import figstyle as fs_
    p = os.path.join(config.OUT, "tables", "T6_ripple.csv")
    if not os.path.exists(p):
        return None
    T6 = pd.read_csv(p)
    fig, ax = fs_.figure(rows=1, cols=2, width=12.5, height=5.0, sharex=False)
    f = np.linspace(150e3, 450e3, 200)
    import ripple
    ax[0].plot(f / 1e3, [ripple.analytical(46.6, x)["ic_pp"] for x in f], "-", color=fs_.phase_style("analytical")["color"], label="analytical V̄/(2 f (L+M)), V̄ = 46.6 V, L+M = 13.75 µH")
    ax[0].plot(f / 1e3, [ripple.analytical(46.6, x)["leg_pp"] for x in f], "--", color=fs_.phase_style("analytical")["color"], label="per leg V̄/(4 f (L+M))")
    q = T6[T6["source"].str.startswith("QSPICE")]
    ax[0].plot(q["f_khz"], q["ic_pp_A"], "o", ms=7, color=fs_.phase_style("qspice")["color"], label="QSPICE device model: i_c pk-pk")
    ax[0].plot(q["f_khz"], q["leg_pp_A"], "s", ms=6, color=fs_.phase_style("qspice")["color"], mfc="none", label="QSPICE: per-leg pk-pk")
    h = T6[T6["source"].str.startswith("hardware")]
    ax[0].plot(h["f_khz"], h["ic_pp_A"], "^", ms=7, color=fs_.phase_style("hardware")["color"], label="hardware telemetry i_c2 pk-pk (45 Hz samples: sensing noise, not ripple)")
    ax[0].set_xlabel("Switching frequency [kHz]")
    fs_.ylabel(ax[0], "Peak-to-peak current", "A")
    ax[0].set_title("Switching ripple of the circulating current vs f_sw")
    fs_.legend(ax[0], ncol=1, loc="upper right", fontsize=8)
    headroom(ax[0], 0.5)
    for fk, col in ((300, "#1b2d55"), (400, "#7a8fbf")):
        cp = os.path.join(config.OUT, "qspice", f"ripple_{fk}k.csv")
        if os.path.exists(cp):
            d = pd.read_csv(cp)
            ax[1].plot(d["t_s"] * 1e6, d["ic1"], color=col, lw=1.2, label=f"i_c1 QSPICE raw, {fk} kHz")
            ax[1].plot(d["t_s"] * 1e6, d["ILA1"], color=col, lw=0.9, ls="--", label=f"I_LA1, {fk} kHz")
    npz = os.path.join(config.NOTEBOOKS, "data", "qspice_ud_sweep.npz")
    if os.path.exists(npz):
        z = np.load(npz)
        k = "f200_run1_du0"
        if f"{k}/t_ripple" in z.files:
            t = z[f"{k}/t_ripple"] * 1e6
            ax[1].plot(t, z[f"{k}/iA1_ripple"] - z[f"{k}/iB1_ripple"], color="#d9822b", lw=1.2, label="i_c1 QSPICE, 200 kHz (ud sweep)")
            ax[1].plot(t, z[f"{k}/iA1_ripple"], color="#d9822b", lw=0.9, ls="--", label="I_LA1, 200 kHz")
    ax[1].set_xlabel("Time [µs]")
    fs_.ylabel(ax[1], "Current", "A")
    ax[1].set_title("Two switching periods, open loop at u_d = 0 (QSPICE S10i, 23.3 V per channel)")
    fs_.legend(ax[1], ncol=2, loc="upper right", fontsize=8)
    headroom(ax[1], 0.45)
    fig.suptitle("Winding-current ripple: analytical law, QSPICE, and what the 45 Hz telemetry shows instead")
    return fs_.save(fig, "compare", "ripple_vs_fsw")


def compare_hw_steady():
    """Hardware steady state vs kscale: vd2 error / noise, ic2 noise, per setup and switching frequency (T2)."""
    import figstyle as fs_
    p = os.path.join(config.OUT, "tables", "T2_hw_steady_state.csv")
    if not os.path.exists(p):
        return None
    T2 = pd.read_csv(p)
    cl = T2[(T2["state"] == "RUN_CL") & (T2["duration_s"] > 20)]
    if cl.empty:
        return None
    fig, ax = fs_.figure(rows=1, cols=3, width=13.5, height=4.6, sharex=False)
    groups = [("PV80", 200, "o", config.SETUP_STYLE["PV80"]["color"]), ("BENCH", 200, "s", "#d9822b"), ("BENCH", 300, "D", "#8c5a1e"), ("BENCH", 400, "^", "#4d3311")]
    for setup, fk, mk, col in groups:
        g = cl[(cl["setup"] == setup) & (cl["f_khz"] == fk)].sort_values("kscale")
        if g.empty:
            continue
        lab = f"{config.SETUP_STYLE[setup]['label']} {fk} kHz"
        ax[0].errorbar(g["kscale"], g["vd2_mean"], yerr=g["vd2_std"], fmt=mk, color=col, ms=6, capsize=3, label=lab)
        ax[1].plot(g["kscale"], g["vd2_std"], mk, color=col, ms=6, label=lab)
        ax[2].plot(g["kscale"], g["ic2_std"], mk, color=col, ms=6, label=lab)
    ax[0].axhline(0, color="k", lw=0.8, ls=":")
    ax[0].set_title("v_d2 steady-state mean ± std (reference 0 V)")
    fs_.ylabel(ax[0], "v_d2", "V")
    ax[1].set_title("v_d2 sample-to-sample std (noise floor)")
    fs_.ylabel(ax[1], "std", "V")
    ax[2].set_title("i_c2 sample-to-sample std (reference 0 A)")
    fs_.ylabel(ax[2], "std", "A")
    for axis in ax:
        axis.set_xlabel("kscale")
        axis.set_xlim(0, 0.9)
        axis.set_xticks([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8])
        headroom(axis, 0.35)
        fs_.legend(axis, ncol=1, fontsize=8)
    fig.suptitle("Hardware closed-loop steady state vs gain scale (settled RUN_CL segments > 20 s, first 2 s skipped)")
    return fs_.save(fig, "compare", "hw_steady_state_vs_kscale")


def energy_figures():
    import figstyle as fs_
    p = os.path.join(config.OUT, "tables", "T7_energy.csv")
    if not os.path.exists(p):
        return []
    T7 = pd.read_csv(p)
    sol = T7[(T7["setup"] == "PV80") & (T7["scope"] == "case")].copy()
    out = []
    if not sol.empty:
        sol["label"] = [f"{c}\n{'open loop' if l == 'OL' else 'k = %g' % k}" for c, l, k in zip(sol["cid"], sol["loop"], sol["kscale"].fillna(0))]
        fig, ax = fs_.figure(rows=1, cols=2, width=12.5, height=5.2, sharex=False)
        x = np.arange(len(sol))
        wdt = 0.27
        ax[0].bar(x - wdt, sol["P_load_W"], wdt, color=fs_.COL["Pstr"], label="P_load (e-load)")
        ax[0].bar(x, sol["P_shuffled_W"], wdt, color="#1f77b4", label="P_shuffled (through the shufflers)")
        ax[0].bar(x + wdt, sol["P_returned_W"], wdt, color="#2ca02c", label="P_returned (above the weakest-module limit)")
        ax[0].set_xticks(x)
        ax[0].set_xticklabels(sol["label"], fontsize=7.5)
        fs_.ylabel(ax[0], "Mean power", "W")
        ax[0].set_title("Mean powers per solar test case (20 Oct 2026)")
        fs_.legend(ax[0], ncol=1)
        headroom(ax[0], 0.35)
        ax[1].bar(x - wdt / 2, sol["E_load_Wh"], wdt, color=fs_.COL["Pstr"], label="E_load")
        ax[1].bar(x + wdt / 2, sol["E_returned_Wh"], wdt, color="#2ca02c", label="E_returned")
        for xi, (_, r) in zip(x, sol.iterrows()):
            ax[1].text(xi, max(r["E_load_Wh"], r["E_returned_Wh"]) * 1.02, f"{r['seconds']:.0f} s", ha="center", fontsize=7.5, color="#444444")
        ax[1].set_xticks(x)
        ax[1].set_xticklabels(sol["label"], fontsize=7.5)
        fs_.ylabel(ax[1], "Energy", "Wh")
        ax[1].set_title("Energy over each window (RUN rows only; window lengths differ)")
        fs_.legend(ax[1], ncol=1)
        headroom(ax[1], 0.35)
        fig.suptitle("Solar energy: delivered, processed by the shufflers, and returned relative to a weakest-module-limited string")
        out.append(fs_.save(fig, "energy", "solar_energy"))
    # shade event time series of S02
    if "S02" in config.TEST_CASES:
        import energy as en
        run = hw.run_frame("S02")
        m = en.means_1s(run)
        if len(m):
            fig, ax = fs_.figure(rows=2, cols=1, width=10, height=6.8)
            tt = m.index.tz_convert(config.LOCAL_TZ)
            for k in (1, 2, 3):
                ax[0].plot(tt, m[f"IM{k}"], color=fs_.COL[f"IM{k}"], lw=1.3, label=f"I_M{k} (KCL)")
            ax[0].plot(tt, m["Istr_i"], color=fs_.COL["Istr"], lw=1.6, ls="--", label="I_string (e-load)")
            ax[0].plot(tt, m[["IM1", "IM2", "IM3"]].min(axis=1), color="k", lw=1.0, ls=":", label="min_k I_k (weakest module)")
            fs_.ylabel(ax[0], "Current", "A")
            ax[0].set_title("Module currents rebuilt by KCL (1 s means) and the string current")
            fs_.legend(ax[0], ncol=3)
            P_mod = m["VM1"] * m["IM1"] + m["VM2"] * m["IM2"] + m["VM3"] * m["IM3"]
            P_ret = ((m["Istr_i"] - m[["IM1", "IM2", "IM3"]].min(axis=1).clip(lower=0)) * m["Vel_i"]).clip(lower=0)
            P_sh = m["id1"].abs() * (m["VM1"] + m["VM2"]) / 2 + m["id2"].abs() * (m["VM2"] + m["VM3"]) / 2
            ax[1].plot(tt, m["Pstr_i"], color=fs_.COL["Pstr"], lw=1.5, label="P_load (e-load)")
            ax[1].plot(tt, P_mod, color="#6c6c6c", lw=1.0, ls="--", label="Σ V_Mk I_Mk (modules)")
            ax[1].plot(tt, P_sh, color="#1f77b4", lw=1.2, label="P_shuffled")
            ax[1].plot(tt, P_ret, color="#2ca02c", lw=1.2, label="P_returned")
            fs_.ylabel(ax[1], "Power", "W")
            ax[1].set_title("Powers (1 s means)")
            fs_.legend(ax[1], ncol=4)
            for axis in ax:
                fs_.time_axis(axis)
                headroom(axis, 0.35)
            ax[1].set_xlabel("Local time (AEST), 20 Oct 2026")
            fig.suptitle("S02 closed loop, peak sun, kscale 0.1: module 1 ≈ 0 A throughout; the shufflers deliver modules 2–3 to the 61 V load")
            out.append(fs_.save(fig, "energy", "S02_shade_power"))
    return out


def compare_all(frames, T4, T5):
    out = []
    HW = None
    p = os.path.join(config.OUT, "tables", "T3_hw_events.csv")
    if os.path.exists(p):
        import compare as cm
        HW = cm.hardware_rows()
    keys = sorted({(f.attrs.get("scenario"), f.attrs.get("setup"), round(f.attrs.get("kscale") or 0.0, 3)) for f in frames
                   if f.attrs.get("scenario") in ("S1", "S3", "S4")})
    for scen, setup, k in keys:
        for sig in {"S1": ["vd2", "ic2", "id2"], "S3": ["id2", "vd2", "Pstr"], "S4": ["vd2", "ic2"]}[scen]:
            pth = compare_step(frames, scen, setup, k, sig, T5)
            if pth:
                out.append(pth)
    out.append(compare_duty_step(frames))
    out.append(compare_metrics_vs_kscale(T4, HW))
    out.append(compare_ripple())
    out.append(compare_hw_steady())
    out += energy_figures()
    return [o for o in out if o]


if __name__ == "__main__":
    main()
