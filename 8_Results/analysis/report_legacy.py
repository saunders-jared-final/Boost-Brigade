#!/usr/bin/env python3
"""Writes REPORT.md from out/tables, out/events and out/figures (run compare.py first)."""
import datetime as dt
import glob
import os

import numpy as np
import pandas as pd

import config
import stepmetrics as sm

TAB = os.path.join(config.OUT, "tables")
FIG = os.path.join(config.OUT, "figures")
EV = os.path.join(config.OUT, "events")
REPORT = os.path.join(config.HERE, "REPORT.md")
PHASE_LABEL = {"analytical": "Analytical N=3 (nstring, deployed M)", "simulink_mil": "Simulink MIL 4-module", "simulink": "Simulink carpark 3-module",
               "qspice": "QSPICE switching + firmware DLL", "hardware": "Hardware"}


def rel(p):
    return os.path.relpath(p, config.HERE).replace(os.sep, "/")


def tms(v):
    return "-" if v is None or not np.isfinite(v) else f"{v * 1e3:.3g}"


def condensed(df, scenario):
    """One row per phase / setup / kscale / signal: medians over the cases (hardware has many engagements)."""
    if df.empty:
        return "_no cases_\n"
    lines = ["| phase | setup | kscale | signal | cases | |delta| | rise 10-90 [ms] | overshoot [%] | t settle 2 % [ms] | ss error | tau [ms] (fit) | resolved |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    if "ended_by" in df:
        df = df[df["ended_by"].fillna("") != "FAULT"]        # runs that tripped are listed in the full table only
    primary = {"S1": ["vd2", "id2"], "S4": ["vd2"], "S3": ["Pstr", "id2", "vd2", "VM3"]}.get(scenario)
    if primary:
        df = df[df["signal"].isin(primary)]                   # the circulating currents stay in the full table
    g = df.groupby(["phase", "setup", "kscale", "signal"], dropna=False)
    order = {p: i for i, p in enumerate(["analytical", "simulink_mil", "simulink", "qspice", "hardware"])}
    for (ph, setup, k, sig), d in sorted(g, key=lambda kv: (kv[0][3], order.get(kv[0][0], 9), str(kv[0][1]), kv[0][2])):
        n = len(d)
        res = int(d["resolved"].fillna(False).astype(bool).sum())
        step = d[d["kind"] == "step"]
        med = lambda c: float(np.nanmedian(step[c])) if len(step) and step[c].notna().any() else float("nan")
        tau = float(np.nanmedian(d.loc[d["fit_model"] == "first", "tau"])) if (d["fit_model"] == "first").any() else float("nan")
        rise, ts2 = med("rise_10_90"), med("t_settle_2")
        dtm = float(np.nanmedian(d["dt_median"])) if d["dt_median"].notna().any() else float("nan")
        if res < n and ph == "hardware" and np.isfinite(dtm):       # transient inside one telemetry sample: bounds, not values
            rise_s = f"<= {max(rise if np.isfinite(rise) else 0, dtm) * 1e3:.0f}"
            ts2_s = f"<= {max(ts2 if np.isfinite(ts2) else 0, dtm) * 1e3:.0f}"
        else:
            rise_s, ts2_s = tms(rise), tms(ts2)
        lines.append(f"| {PHASE_LABEL.get(ph, ph)} | {setup} | {k} | {sig} | {n} | {sm.fmt(float(np.nanmedian(np.abs(d['delta']))), '', 2)} | "
                     f"{rise_s} | {sm.fmt(med('overshoot_pct'), '', 2)} | {ts2_s} | {sm.fmt(float(np.nanmedian(d['ss_error'])) if d['ss_error'].notna().any() else float('nan'), '', 2)} | "
                     f"{tms(tau)} | {res}/{n} |")
    return "\n".join(lines) + "\n"


def events_summary():
    lines = ["| window | RUN_CL segments (kscale) | FAULT ends | shade candidates in runs | note |", "|---|---|---|---|---|"]
    confirm = []
    for name, (folder, s, e, note) in config.WINDOWS.items():
        seg_p, ev_p = os.path.join(EV, name + ".segments.csv"), os.path.join(EV, name + ".events.csv")
        if not os.path.exists(seg_p):
            continue
        seg, ev = pd.read_csv(seg_p), pd.read_csv(ev_p)
        runs = seg[(seg["state"] == "RUN_CL") & (seg["duration_s"] > 2)]
        faults = int((seg["ended_by"] == "FAULT").sum())
        cand = ev[ev["kind"].isin(["shade_on", "transient_on"]) & ev["detail"].astype(str).str.startswith("[RUN")]
        lines.append(f"| `{name}` | {len(runs)} ({', '.join(str(k) for k in runs['kscale'].tolist())}) | {faults} | {len(cand)} | {note} |")
        if folder == "Solar_Closed_Loop":
            for _, r in cand.iterrows():
                confirm.append(f"- `{name}`: {r['time_local'][11:19]} {r['kind']} {r['detail']}")
    return "\n".join(lines) + "\n", confirm


def main():
    parts = [f"# Results synthesis: control behaviour across analysis, Simulink, QSPICE, bench and PV\n\n_Generated {dt.datetime.now(config.LOCAL_TZ):%Y-%m-%d %H:%M} by `8_Results/analysis/report.py`; rerun `make report` after any change._\n"]
    parts.append("""## 0 · Findings of the 21 Oct 2026 run

- **Reference step (S4, `vd2`, time constant of the fitted first-order response):** at kscale 0.1 the analytical model
  (12.2 ms PV80), the Simulink carpark model (11.6 / 10.1 ms) and the QSPICE switching model with the firmware DLL
  (12.4 / 9.7 ms) agree with the pure-integral design value (10.6 ms) within 20 %. At kscale 0.3 the same holds
  (3.5-4.0 ms against 3.5 ms design). At kscale 1 the switching model (0.77 / 0.55 ms) and Simulink (0.56 / 0.40 ms)
  are about twice as fast as the design value (1.06 ms) and the analytical closed loop (1.08 ms), and the first
  overshoot appears (QSPICE 4 %, Simulink bench 9 %): the proportional term and a plant gain above the one the
  deployed decoupler assumes become visible at full gain. No reference step was sent on hardware.
- **Loop closing (S1):** on the bench the soft start ramps the duties to 0.5 in about 200 ms and removes most of the
  5 V module mismatch by itself; the controller then takes the 0.5 V residual to zero within one 50 Hz sample
  (<= 23-25 ms) at every kscale from 0.1 to 0.6, consistent with the 4-41 ms settling the simulations predict.
  On the solar day the panels were matched (residual 0.1 V), except the 13:04 run under the shirt (3.7 V idle
  mismatch), where the supervisor then held `vd2` at its own reference.
- **Shade (S3):** all three simulations move the shuffled current by 1.5-1.9 A within a millisecond of a one-third
  irradiance loss on module 3 (analytical 1.7 A, Simulink 1.9 A, QSPICE 1.5 A); on hardware the shade events are
  10-34 W power dips with multi-second recoveries set by the shirt / hand motion and the e-load, not by the loop.
- **Settled statistics (S2):** bench `vd2` noise fell from 0.08 V (early runs) to 0.013-0.017 V after the
  ADC phase-B change at 16:02; on the solar sweep the circulating-current noise grows with gain
  (0.22 A at kscale 0.1 to 0.31 A at 0.8) while `vd2` stays at 0.09-0.17 V.
- **Gain matrices (section 5):** the averaged model reproduces the identified voltage-mode gains (-Vbar: -41 PV80,
  -46.5 at the QSPICE bench point, against -37 to -47 V per unit identified) and the circulating-mode gain is Vbar / R
  with R the plant's effective winding resistance: 61 mOhm in the averaged Simulink model (742 identified) and
  0.27 / 0.79 / 1.66 ohm in the switching plant at 200 / 300 / 400 kHz (142 / 58 / 23 A per unit). That resistance is
  the pole-capacitance commutation during the dead time, R_sw = 64 C_p f_sw^3 (L+M)^2 = 0.21 / 0.72 / 1.70 ohm for
  C_p = 2.2 nF (derived and checked against a QSPICE u_d sweep in `3_Analytical/shuffler_notebooks/shuffler_nstring.ipynb`,
  section 8). The switching plant also carries a -10 to -25 V per unit coupling from differential duty to voltage
  difference that the averaged model does not contain.

## 1 · Method

One metric definition (`stepmetrics.step_metrics`) is applied to every phase and signal. Levels are medians (pre-event window,
last 20 % of the post-event window); the response is normalised by the measured change `delta`; **rise time** is 10-90 % with
interpolated crossings; **overshoot** is against the measured final value; **settling** is the last excursion outside a 2 % (5 %)
band, never narrower than three times the pre-event noise; **steady-state error** is against the reference. Changes smaller than
a floor (0.1 V, 0.3 A, 3 W) are treated as disturbances: peak deviation and time back inside the band. A first-order or
second-order model with delay is fitted by least squares; its time constant (with a 1-sigma interval) is the quantity that
makes 50 Hz telemetry comparable with 10 kHz simulations. When fewer than four samples fall inside the transient the time
metrics are reported as upper bounds (`<=` one sample).

Scenarios: **S1** the loop closing on the string mismatch (hardware: every SOFTSTART -> RUN_CL; QSPICE: the true open-loop ->
closed-loop switch; Simulink and analytical: a reference step of `-vd_OL` from a settled loop, equivalent to first order
because the firmware's bumpless rebase starts the integrators at zero; the analytical row simulates the true initial-condition
response); **S2** settled statistics per kscale; **S3** module 3 shaded to about two thirds from a settled loop (hardware:
candidate events detected in the data, to be confirmed); **S4** a +1 V step on the VM2-VM3 reference (simulations only; no
reference step was sent on hardware).

Design reference (pure-integral loop, `kI_v = 2*pi*150`, `kI_i = 2*pi*400`, scaled by kscale): voltage-difference loop
tau 10.6 / 3.5 / 1.06 ms, 10-90 rise 23 / 7.8 / 2.3 ms, 2 % settling 41 / 14 / 4.1 ms at kscale 0.1 / 0.3 / 1;
circulating-current loop tau 4.0 / 1.3 / 0.40 ms.

Conventions: `vd1 = VM1-VM2`, `vd2 = VM2-VM3`, `ic = ILA+ILB` (circulating, nulled by the controller), `id = ILA-ILB` (shuffled).
Hardware telemetry is 50 Hz; VM1 comes from the e-load through the Pi at 2.2 Hz, so hardware step metrics use `vd2`;
the inductor-current frames are point samples of the switching ripple, so currents enter only through the S2 statistics.
""")
    summ, confirm = events_summary()
    parts.append("## 2 · Hardware data inventory\n\nExports: `8_Results/Bench_Closed_Loop_200kHz/`, `8_Results/Solar_Closed_Loop/` (READMEs there). Events and segments: `out/events/`.\n\n" + summ)
    parts.append("Overview plots per window (state bands, 1 s medians of module voltages, string power, currents, duties, detected events):\n\n"
                 + "\n".join(f"- [{os.path.basename(p)}]({rel(p)})" for p in sorted(glob.glob(os.path.join(EV, "*.png")))) + "\n")
    if confirm:
        parts.append("### Shade / walking candidates for confirmation (solar day, inside runs)\n\nMark the real ones in `out/events/<window>.annot.csv` (columns `time_local,kind,label`), then `make events compare report`.\n\n" + "\n".join(confirm) + "\n")
    for s, fname, title in (("S1", "S1_loop_close", "S1 · Loop closing on the mismatch"), ("S4", "S4_vref2_step", "S4 · +1 V reference step (simulations and analysis)"),
                            ("S3", "S3_shade_m3", "S3 · Module 3 shade")):
        p = os.path.join(TAB, fname + ".csv")
        if os.path.exists(p):
            df = pd.read_csv(p)
            parts.append(f"## 3 · {title}\n\nCondensed (medians over cases; full table: [{fname}.md]({rel(os.path.join(TAB, fname + '.md'))}), CSV alongside).\n\n" + condensed(df, s))
    p = os.path.join(TAB, "S2_settled.md")
    if os.path.exists(p):
        parts.append("## 4 · S2 · Settled statistics per kscale\n\n" + open(p).read())
    p = os.path.join(TAB, "G_compare.md")
    if os.path.exists(p):
        parts.append("## 5 · Identified gain matrices against the N-module model\n\n" + open(p).read()
                     + "\nThe derivation, the N = 2 check against the retrospective, cond(G(N)) and the closed-loop poles are in "
                       "`3_Analytical/shuffler_notebooks/shuffler_nstring.ipynb` (`nstring.py`).\n")
    figs = sorted(glob.glob(os.path.join(FIG, "*.png")))
    if figs:
        parts.append("## 6 · Overlay figures\n\n" + "\n".join(f"![{os.path.basename(f)}]({rel(f)})" for f in figs) + "\n")
    parts.append("""## 7 · Screenshots to take (Grafana, local time)

- Bench 16 Oct, good closed-loop runs: 15:50:30-15:53:00 and 16:02:00-16:04:40 (module voltages, inductor currents, duties, supervisor).
- Bench 16 Oct, the loop-closing instant at 15:50:33 with a 10 s window (shows IDLE -> SOFTSTART -> RUN_CL).
- Solar 20 Oct, the kscale sweep 15:51-16:26 as one window and each level on its own (15:52:05 k0.1, 15:56:54 k0.2, 16:01:08 k0.3, 16:05:37 k0.4, 16:09:44 k0.5, 16:13:19 k0.6, 16:19:11 k0.7, 16:23:11 k0.8).
- Solar 20 Oct, 13:04:18-13:11:19 closed loop with the shade events (string power + shuffled currents), and 12:53:17-12:55:00 open loop for the same panel.
- Solar 20 Oct, 13:00:30-13:01:40 (the person walking round the panels while idle: module 3 voltage dip).
- QSPICE: `Power_Shuffler_Integrated.qsch` and the S10 / S10p stage waveforms if the native look is wanted; the matched runs are in `out/qspice/`.

## 8 · Caveats

- 50 Hz telemetry against 150 / 400 Hz loops: hardware step metrics are upper bounds except at low kscale; the fitted time constant is the comparable number.
- The hardware engagement runs through a 150 ms soft start that ramps the duties to 0.5; that ramp alone removes most of the module mismatch (the half bridge at 0.5 duty forces VM2 = VM3), so the loop's own step is the residual (about 0.5 V on the bench) and completes within one telemetry sample.
- VM1 on hardware is the e-load reading through the Pi (2.2 Hz): vd1 / ic1 hardware metrics are flagged, comparisons use vd2 / ic2 / id2.
- FAULT-terminated bench runs are listed but only segments longer than 2 s after the event contribute.
- The solar kscale sweep ran at 8-14 W of string power (late afternoon); PV irradiance drifts across runs; the shirt shading is not repeatable, so S3 hardware rows carry magnitudes, not matched steps.
- Shade is a bypassed substring in reality (voltage step) but an irradiance scale in the simulations (current step).
- The QSPICE bench model has channel 1 in current limit (ILIM 0.8 / 1.0 / 1.3 A); the 16 Oct bench had the middle module at 20 V. Confirm the PSU settings before matching the bench rows.
- The analytical model is linear: amplitudes are illustrative, time constants are the comparison.
- QSPICE S1 at kscale 0.1 and 0.3 closes the loop 0.5 ms after a cold start (the S10 netlists start from `.ic` voltages), so the
  pre-event level is a still-moving start-up; the kscale 1 cases were rerun with a 3 ms open-loop period (`run_scenarios.py --ten`).
  S3 and S4 are unaffected (the loop is settled long before those events).
- Simulink MIL (4-module ideal model): not in the tables. Its references enter through a bus into the Supervisor subsystem,
  so the in-memory Constant -> Step swap of `run_scenarios.m` breaks the bus; the MIL record remains the validate figures
  (`4_Simulink/1_MIL_Model_In_The_Loop/figs`, reference set at t = 0) until the model gets a Step input of its own.
- On the solar day the supervisor was active: after a shaded engagement the loop regulates `vd2` to the supervisor's `rv2`, not to 0,
  so the hardware S1 steady-state "error" there is the supervisor reference, not a controller offset.
""")
    open(REPORT, "w").write("\n".join(parts))
    print("wrote", REPORT)


if __name__ == "__main__":
    main()
