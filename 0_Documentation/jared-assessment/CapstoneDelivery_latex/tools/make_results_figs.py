#!/usr/bin/env python3
"""Regenerate the Results-section figures in figures/results/ from the results
pipeline data (8_Results/analysis/out), in the report's print style (STIX serif,
one categorical palette, one axis per panel, panels stacked so each gets the full
text width).

    python3 tools/make_results_figs.py

Figures
    twin_sim        Simulink carpark twin: +1 V reference step at three gain scales, shade CL vs OL
    qspice_run      QSPICE + firmware DLL, PV80 k=0.3: closure -> +1 V step -> shade on module 3
    bench_B06       bench 300 kHz CL k=0.3 with PSU / e-load steps (raw samples + 1 s mean)
    solar_S02       carpark peak sun CL k=0.1 with the shade event, powers delivered / returned
    duty_steps      bench open-loop duty steps against the averaged-model prediction
    metrics_k       fitted tau and overshoot of the +1 V step vs gain scale, three models"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
if not os.path.isdir(os.path.join(ROOT, "8_Results")):
    ROOT = os.environ.get("BOOST_BRIGADE", "/mnt/c/Users/jazsa/Documents/Boost-Brigade")
SRC = os.path.join(ROOT, "8_Results", "analysis", "out")
OUT = os.path.join(HERE, "..", "figures", "results")
os.makedirs(OUT, exist_ok=True)

# categorical slots in fixed order (validated light palette); entity 1/2/3 always the same hue
C1, C2, C3, C4 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
GREY, INK, MUTED = "#8a8a85", "#2b2b2a", "#555550"
PHASE = {"analytical": (C1, "o", "-"), "qspice": (C2, "s", "-"), "simulink": (C3, "D", "-")}
PHASE_NAME = {"analytical": "Analytical ($N=3$ model)", "qspice": "QSPICE + firmware DLL", "simulink": "Simulink carpark twin"}
W = 6.3          # text width [in]

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["STIXGeneral", "Times New Roman", "DejaVu Serif"], "mathtext.fontset": "stix",
    "font.size": 9, "axes.labelsize": 9, "axes.titlesize": 9, "legend.fontsize": 8, "xtick.labelsize": 8, "ytick.labelsize": 8,
    "axes.edgecolor": GREY, "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED, "axes.titlecolor": INK,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": "#e4e3df", "grid.linewidth": 0.6,
    "axes.axisbelow": True, "legend.frameon": False, "lines.linewidth": 1.4, "pdf.fonttype": 42,
    "axes.titlelocation": "left", "axes.titleweight": "normal", "axes.formatter.useoffset": False,
})


def save(fig, name):
    fig.savefig(os.path.join(OUT, name + ".pdf"))
    fig.savefig(os.path.join(OUT, name + ".png"), dpi=150)
    plt.close(fig)
    print("wrote", name)


def panel_tag(ax, s):
    ax.set_title(s, fontsize=9, loc="left", pad=3)


def legend_right(ax, **kw):
    ax.legend(loc="upper left", bbox_to_anchor=(1.005, 1.0), borderaxespad=0, handlelength=1.8, **kw)


def mark(ax, x, label, y=1.0, color=MUTED, ha="left"):
    ax.axvline(x, color=color, lw=0.8, ls=(0, (3, 2)), zorder=1)
    if label:
        ax.text(x, y, " " + label, transform=ax.get_xaxis_transform(), fontsize=7.5, color=color, va="bottom", ha=ha)


# --------------------------------------------------------------------------- hardware helpers
def load_hw(cid_prefix):
    f = [x for x in os.listdir(os.path.join(SRC, "hw")) if x.startswith(cid_prefix)][0]
    d = pd.read_csv(os.path.join(SRC, "hw", f))
    d["t"] = pd.to_datetime(d["t_local"].str.slice(0, 26))
    return d, f[:-4]


def load_events(stem):
    p = os.path.join(SRC, "events", stem + ".events.csv")
    e = pd.read_csv(p)
    e["t"] = pd.to_datetime(e["time_local"].str.slice(0, 19).str.replace("T", " "))
    return e


def with_gaps(d, gap_s=1.0):
    """Insert NaN rows where the run stops so lines are not drawn across IDLE periods."""
    d = d.sort_values("t").reset_index(drop=True)
    dt = d["t"].diff().dt.total_seconds()
    idx = np.where(dt > gap_s)[0]
    if len(idx) == 0:
        return d
    parts, last = [], 0
    for i in idx:
        parts.append(d.iloc[last:i])
        gap = d.iloc[[i - 1]].copy()
        for c in gap.columns:
            if c != "t":
                gap[c] = np.nan
        gap["t"] = d["t"].iloc[i - 1] + pd.Timedelta(milliseconds=1)
        parts.append(gap)
        last = i
    parts.append(d.iloc[last:])
    return pd.concat(parts, ignore_index=True)


def raw_and_mean(ax, d, col, color, label, win="1s", lw=1.3, band=True):
    """1 s rolling mean, with the +-1 sigma of the raw 44 Hz samples as a light band."""
    s = d.set_index("t")[col]
    r = s.rolling(win, min_periods=5)
    m, sd = r.mean(), r.std()
    m[s.isna()] = np.nan
    sd[s.isna()] = np.nan
    if band:
        ax.fill_between(m.index, m - sd, m + sd, color=color, alpha=0.16, lw=0, zorder=1)
    ax.plot(m.index, m.values, color=color, lw=lw, label=label, zorder=3)


def time_axis(ax, fmt="%H:%M"):
    ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt))


# --------------------------------------------------------------------------- 1. Simulink carpark twin
def twin_sim():
    base = os.path.join(SRC, "sim", "carpark")
    rd = lambda n: pd.read_csv(os.path.join(base, n + ".csv"))  # noqa: E731
    fig, axs = plt.subplots(3, 1, figsize=(W, 4.5), sharex=False)
    # (a) reference step at three gain scales
    ax = axs[0]
    for k, c in zip(["0.1", "0.3", "1"], [C1, C2, C3]):
        d = rd(f"S4_vref_PV80_k{k}")
        t0 = json.load(open(os.path.join(base, f"S4_vref_PV80_k{k}.json")))["t0"]
        t = (d.t - t0) * 1e3
        ax.plot(t, d.VM2 - d.VM3, color=c, label=f"$v_{{d,2}}$, $k={k}$")
        ax.plot(t, d.VM1 - d.VM2, color=c, lw=0.9, ls=(0, (4, 2)), label=f"$v_{{d,1}}$, $k={k}$")
    ax.step([-30, 0, 60], [0, 1, 1], where="post", color=INK, lw=0.8, ls=":", label="reference $r_{v,2}$")
    ax.set_xlim(-5, 80)
    ax.set_ylabel("voltage difference [V]")
    panel_tag(ax, "(a) $+1$ V step on the $v_{d,2}$ reference: $v_{d,2}$ follows, $v_{d,1}$ (dashed) stays at zero")
    legend_right(ax, ncol=1)
    # (b) shade: CL vs OL on vd
    ax = axs[1]
    cl, ol = rd("S3_shade_PV80_k0.3"), rd("S3_shade_OL_PV80_k0.3")
    for d, ls, tag in [(ol, (0, (4, 2)), "open loop"), (cl, "-", "closed loop")]:
        t = (d.t - 0.03) * 1e3
        ax.plot(t, d.VM1 - d.VM2, color=C1, ls=ls, label=f"$v_{{d,1}}$, {tag}")
        ax.plot(t, d.VM2 - d.VM3, color=C2, ls=ls, label=f"$v_{{d,2}}$, {tag}")
    ax.set_xlim(-5, 60)
    ax.set_ylim(-0.03, 0.15)
    ax.set_ylabel("voltage difference [V]")
    panel_tag(ax, "(b) module 3 shaded to 2/3 at $t=0$ ($k=0.3$): the loop removes the residual the open loop keeps")
    legend_right(ax)
    # (c) shade: currents
    ax = axs[2]
    t = (cl.t - 0.03) * 1e3
    for j, c in [(1, C1), (2, C2), (3, C3)]:
        ax.plot(t, cl[f"IM{j}"], color=c, lw=0.9, ls=(0, (1.5, 1.5)), label=f"module current $I_{j}$")
    ax.plot(t, cl.I_String, color=INK, lw=1.0, label="string current")
    ax.plot(t, cl.ILA1 - cl.ILB1, color=C1, label="shuffled $i_{m,1}$")
    ax.plot(t, cl.ILA2 - cl.ILB2, color=C2, label="shuffled $i_{m,2}$")
    ax.set_xlim(-5, 60)
    ax.set_xlabel("time from the event [ms]")
    ax.set_ylabel("current [A]")
    panel_tag(ax, "(c) same shade, closed loop: the shufflers carry the deficit and the string settles at the mean current")
    legend_right(ax)
    fig.tight_layout(h_pad=1.0)
    save(fig, "twin_sim")


# --------------------------------------------------------------------------- 2. QSPICE run
def qspice_run():
    d = pd.read_csv(os.path.join(SRC, "qspice", "pv80_k0.3.csv"))
    ev = json.load(open(os.path.join(SRC, "qspice", "pv80_k0.3.json")))["events"]
    t = d.t * 1e3
    fig, axs = plt.subplots(3, 1, figsize=(W, 4.2), sharex=True)
    ax = axs[0]
    ax.plot(t, d.vd1, color=C1, label="$v_{d,1}$")
    ax.plot(t, d.vd2, color=C2, label="$v_{d,2}$")
    tv = ev["vref"] * 1e3
    ax.step([0, tv, t.max()], [0, 1, 1], where="post", color=INK, lw=0.8, ls=":", label="reference $r_{v,2}$")
    ax.set_ylabel("voltage difference [V]")
    ax.set_ylim(-1.5, 1.6)
    legend_right(ax)
    ax = axs[1]
    ax.plot(t, d.id1, color=C1, label="shuffled $i_{m,1}$")
    ax.plot(t, d.id2, color=C2, label="shuffled $i_{m,2}$")
    ax.plot(t, d.ic1, color=C1, lw=0.9, ls=(0, (4, 2)), label="circulating $i_{c,1}$")
    ax.plot(t, d.ic2, color=C2, lw=0.9, ls=(0, (4, 2)), label="circulating $i_{c,2}$")
    ax.set_ylabel("current [A]")
    ax.set_ylim(-1.6, 3.4)
    legend_right(ax)
    ax = axs[2]
    for j, c in [(1, C1), (2, C2), (3, C3)]:
        ax.plot(t, d[f"IM{j}"], color=c, label=f"module current $I_{j}$")
    ax.plot(t, d.Istr, color=INK, lw=1.0, label="string current")
    ax.set_ylabel("current [A]")
    ax.set_xlabel("simulated time [ms]")
    legend_right(ax)
    for i, ax in enumerate(axs):
        mark(ax, ev["close"] * 1e3, "loop closes" if i == 0 else "")
        mark(ax, tv, "$+1$ V reference step" if i == 0 else "")
        mark(ax, ev["shade_on"] * 1e3, "module 3 shaded to 2/3" if i == 0 else "")
    ax.set_xlim(-1, t.max())
    fig.tight_layout(h_pad=0.6)
    save(fig, "qspice_run")


# --------------------------------------------------------------------------- 3. bench B06
def bench_B06():
    d, stem = load_hw("B06_")
    d = with_gaps(d[(d.state == "RUN_CL") & (d.t >= "2026-10-16 17:21:00")])
    e = load_events(stem)
    steps = e[e.kind == "load_step"].reset_index(drop=True)
    fig, axs = plt.subplots(4, 1, figsize=(W, 4.6), sharex=True)
    ax = axs[0]
    raw_and_mean(ax, d, "id1", C1, "shuffled $i_{m,1}$")
    raw_and_mean(ax, d, "id2", C2, "shuffled $i_{m,2}$")
    ax.set_ylabel("current [A]")
    legend_right(ax)
    ax = axs[1]
    raw_and_mean(ax, d, "ic1", C1, "circulating $i_{c,1}$")
    raw_and_mean(ax, d, "ic2", C2, "circulating $i_{c,2}$")
    ax.set_ylabel("current [A]")
    legend_right(ax)
    ax = axs[2]
    raw_and_mean(ax, d, "vd1", C1, "$v_{d,1}$")
    raw_and_mean(ax, d, "vd2", C2, "$v_{d,2}$")
    ax.axhline(0, color=INK, lw=0.8, ls=":", label="reference (0 V)")
    ax.set_ylabel("voltage difference [V]")
    ax.set_ylim(-0.1, 0.1)
    legend_right(ax)
    ax = axs[3]
    raw_and_mean(ax, d, "Istr", C3, "string current\n(e-load)")
    ax.set_ylabel("current [A]")
    legend_right(ax)
    for i, ax in enumerate(axs):
        for n, r in steps.iterrows():
            mark(ax, r.t, str(n + 1) if i == 0 else "")
    axs[-1].set_xlabel("local time, 16 Oct 2026 (AEST)")
    axs[-1].xaxis.set_major_locator(mdates.MinuteLocator())
    time_axis(axs[-1], "%H:%M")
    fig.tight_layout(h_pad=0.5)
    save(fig, "bench_B06")
    print("  B06 steps:", [(n + 1, r.t.strftime("%H:%M:%S"), r.detail) for n, r in steps.iterrows()])


# --------------------------------------------------------------------------- 4. solar S02
def solar_S02():
    d, stem = load_hw("S02_")
    d = with_gaps(d[d.state == "RUN_CL"])
    e = load_events(stem)
    fig, axs = plt.subplots(4, 1, figsize=(W, 4.6), sharex=True)
    ax = axs[0]
    for j, c in [(1, C1), (2, C2), (3, C3)]:
        raw_and_mean(ax, d, f"IM{j}", c, f"module $I_{j}$ (KCL)")
    raw_and_mean(ax, d, "Istr", INK, "string (e-load)")
    ax.set_ylabel("current [A]")
    legend_right(ax)
    ax = axs[1]
    raw_and_mean(ax, d, "id1", C1, "shuffled $i_{m,1}$")
    raw_and_mean(ax, d, "id2", C2, "shuffled $i_{m,2}$")
    ax.set_ylabel("current [A]")
    legend_right(ax)
    ax = axs[2]
    raw_and_mean(ax, d, "vd1", C1, "$v_{d,1}$")
    raw_and_mean(ax, d, "vd2", C2, "$v_{d,2}$")
    ax.axhline(0, color=INK, lw=0.8, ls=":", label="reference (0 V)")
    ax.set_ylim(-0.2, 0.2)
    ax.set_ylabel("voltage difference [V]")
    legend_right(ax)
    ax = axs[3]
    raw_and_mean(ax, d, "Pstr_i", C3, "delivered to load")
    raw_and_mean(ax, d, "P_ret", C4, "returned by the\nshufflers")
    ax.set_ylabel("power [W]")
    legend_right(ax)
    on = e[e.kind == "mismatch_on"].t.tolist()
    off = e[e.kind == "mismatch_off"].t.tolist()
    for i, ax in enumerate(axs):
        for a, b in zip(on, off):
            ax.axvspan(a, b, color="#ecebe5", zorder=0, lw=0)
    for a, b in zip(on, off):
        axs[0].text(a + (b - a) / 2, 1.0, "high mismatch", transform=axs[0].get_xaxis_transform(), fontsize=7.5, color=MUTED, ha="center", va="bottom")
    axs[-1].set_xlabel("local time, 20 Oct 2026 (AEST)")
    axs[-1].xaxis.set_major_locator(mdates.MinuteLocator())
    time_axis(axs[-1], "%H:%M")
    fig.tight_layout(h_pad=0.5)
    save(fig, "solar_S02")


# --------------------------------------------------------------------------- 5. duty steps
def duty_steps():
    d, stem = load_hw("B01s_")
    d = d[(d.t >= "2026-10-16 15:10:40") & (d.t <= "2026-10-16 15:16:10")]
    d = with_gaps(d[d.state == "RUN_OL"])
    vbar = 46.6
    # commanded leg duties (S1 legs, S2 legs) before / after each step, from the pod command log
    steps = [("15:11:42", (0.50, 0.49), (0.50, 0.51)),
             ("15:13:00", (0.50, 0.51), (0.49, 0.50)),
             ("15:15:15", (0.49, 0.50), (0.51, 0.50))]
    fig, ax = plt.subplots(figsize=(W, 2.9))
    raw_and_mean(ax, d, "vd1", C1, "$v_{d,1}$ measured")
    raw_and_mean(ax, d, "vd2", C2, "$v_{d,2}$ measured")
    # prediction: start from the measured level before the first step, add -Vbar * duc at each step
    m = d.set_index("t")[["vd1", "vd2"]]
    t_first = pd.Timestamp("2026-10-16 " + steps[0][0])
    lvl = m[(m.index < t_first) & (m.index > t_first - pd.Timedelta(seconds=20))].median().values
    xs, y1, y2 = [m.index.min()], [lvl[0]], [lvl[1]]
    for ts, before, after in steps:
        tt = pd.Timestamp("2026-10-16 " + ts)
        duc = [2 * (after[i] - before[i]) for i in range(2)]
        lvl = lvl + np.array([-vbar * duc[0], -vbar * duc[1]])
        xs.append(tt), y1.append(lvl[0]), y2.append(lvl[1])
        dtxt = ", ".join(f"S{i + 1} {before[i]:.2f}$\\to${after[i]:.2f}" for i in range(2) if before[i] != after[i])
        mark(ax, tt, dtxt)
    xs.append(m.index.max()), y1.append(y1[-1]), y2.append(y2[-1])
    ax.step(xs, y1, where="post", color=C1, lw=1.0, ls=(0, (4, 2)), label="$v_{d,1}$ predicted, $-\\bar V\\Delta u_{c,1}$")
    ax.step(xs, y2, where="post", color=C2, lw=1.0, ls=(0, (4, 2)), label="$v_{d,2}$ predicted, $-\\bar V\\Delta u_{c,2}$")
    ax.set_ylabel("voltage difference [V]")
    ax.set_xlabel("local time, 16 Oct 2026 (AEST)")
    time_axis(ax, "%H:%M")
    ax.set_ylim(-1.6, 1.6)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=4, handlelength=1.8, fontsize=7.5)
    fig.tight_layout()
    save(fig, "duty_steps")


# --------------------------------------------------------------------------- 6. metrics vs k
def metrics_k():
    t = pd.read_csv(os.path.join(SRC, "tables", "T5_cross_phase.csv"))
    s = t[(t.scenario == "S4") & (t.signal == "vd2")]
    fig, axs = plt.subplots(1, 2, figsize=(W, 2.8))
    kk = np.logspace(np.log10(0.08), np.log10(1.25), 50)
    ax = axs[0]
    ax.plot(kk, 1e3 / (kk * 2 * np.pi * 150), color=INK, lw=1.0, ls=":", label="design $1/(k\\,2\\pi\\,150)$")
    ax.axhline(23, color=MUTED, lw=0.8, ls=(0, (1, 1.5)))
    ax.text(0.085, 25, "one hardware telemetry frame (23 ms)", fontsize=7, color=MUTED, va="bottom")
    for ph, (c, mk, _) in PHASE.items():
        for setup, ls, fill in [("PV80", "-", c), ("BENCH", (0, (3, 2)), "white")]:
            q = s[s.setup == setup].dropna(subset=[f"{ph}_tau_ms"])
            ax.plot(q.kscale, q[f"{ph}_tau_ms"], color=c, ls=ls, lw=1.1, marker=mk, ms=4.5, mfc=fill, mec=c)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xticks([0.1, 0.2, 0.3, 0.5, 1])
    ax.set_xticklabels(["0.1", "0.2", "0.3", "0.5", "1"])
    ax.set_ylim(0.3, 50)
    ax.set_xlabel("gain scale $k$")
    ax.set_ylabel("fitted time constant $\\tau$ [ms]")
    panel_tag(ax, "(a) time constant")
    ax = axs[1]
    for ph, (c, mk, _) in PHASE.items():
        for setup, ls, fill in [("PV80", "-", c), ("BENCH", (0, (3, 2)), "white")]:
            q = s[s.setup == setup].dropna(subset=[f"{ph}_overshoot_pct"])
            ax.plot(q.kscale, q[f"{ph}_overshoot_pct"], color=c, ls=ls, lw=1.1, marker=mk, ms=4.5, mfc=fill, mec=c)
    ax.set_xscale("log")
    ax.set_xticks([0.1, 0.2, 0.3, 0.5, 1])
    ax.set_xticklabels(["0.1", "0.2", "0.3", "0.5", "1"])
    ax.set_ylim(-0.5, 10)
    ax.set_xlabel("gain scale $k$")
    ax.set_ylabel("overshoot [%]")
    panel_tag(ax, "(b) overshoot")
    h = [plt.Line2D([], [], color=c, marker=mk, ms=4.5, lw=1.1) for c, mk, _ in PHASE.values()]
    lab = list(PHASE_NAME.values())
    h += [plt.Line2D([], [], color=MUTED, marker="o", ms=4.5, lw=1.1),
          plt.Line2D([], [], color=MUTED, marker="o", ms=4.5, mfc="white", lw=1.1, ls=(0, (3, 2))),
          plt.Line2D([], [], color=INK, lw=1.0, ls=":")]
    lab += ["solar plant (PV80)", "bench plant", "design $1/(k\\,2\\pi\\,150)$"]
    fig.legend(h, lab, loc="lower center", ncol=3, bbox_to_anchor=(0.5, -0.01), handlelength=2.2, fontsize=7.5)
    fig.tight_layout(rect=(0, 0.13, 1, 1))
    save(fig, "metrics_k")


# --------------------------------------------------------------------------- 7. MIL validate examples
def mil_validate():
    base = os.path.join(SRC, "sim", "mil_validate")
    fig, axs = plt.subplots(2, 1, figsize=(W, 4.4))
    ax = axs[0]
    d = pd.read_csv(os.path.join(base, "04_shade-refs.csv"))
    t = d.t * 1e3
    for j, (c, r) in enumerate(zip([C1, C2, C3], [0, 2, -2]), start=1):
        ax.plot(t, d[f"VM{j}"] - d[f"VM{j + 1}"], color=c, label=f"$v_{{d,{j}}}$")
        ax.axhline(r, color=c, lw=0.8, ls=":")
    ax.set_ylim(-3, 3)
    ax.set_xlabel("time [ms]")
    ax.set_ylabel("voltage difference [V]")
    panel_tag(ax, "(a) test 04: module 3 at 500 W/m$^2$, references $r_v = [0, 2, -2]$ V (dotted) are tracked")
    legend_right(ax)
    ax = axs[1]
    d = pd.read_csv(os.path.join(base, "05_shade-deep.csv"))
    t = d.t * 1e3
    ax.plot(t, d.stress, color=INK, label="stress index")
    ax.plot(t, d.beta, color=C4, label="governor gain $\\beta$")
    ax.axhline(0.9, color=INK, lw=0.8, ls=":", label="$S_{hi} = 0.9$")
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("stress, $\\beta$ [--]")
    ax.set_xlabel("time [ms]")
    panel_tag(ax, "(b) test 05: module 3 at 200 W/m$^2$, the supervisor holds the stress at its limit by relaxing $r_v$")
    legend_right(ax)
    fig.tight_layout(h_pad=1.0)
    save(fig, "mil_validate")


# --------------------------------------------------------------------------- 8. die temperatures
def thermal():
    fig, axs = plt.subplots(1, 2, figsize=(W, 2.6), sharey=True)
    fcol = {200: C1, 300: C2, 400: C3}
    for ax, prefix, day in [(axs[0], "B", "16 Oct (bench)"), (axs[1], "S", "20 Oct (solar)")]:
        seen = set()
        for f in sorted(os.listdir(os.path.join(SRC, "hw"))):
            if not f.startswith(prefix) or not f.endswith(".csv"):
                continue
            d = pd.read_csv(os.path.join(SRC, "hw", f), usecols=["t_local", "T1", "T2"])
            d["t"] = pd.to_datetime(d["t_local"].str.slice(0, 26))
            fk = int(f.split("_")[2].rstrip("k"))
            lab = f"{fk} kHz" if fk not in seen else None
            seen.add(fk)
            d = d.set_index("t")[["T1", "T2"]].max(axis=1).resample("10s").max().dropna()
            ax.plot(d.index, d.values, color=fcol[fk], lw=1.4, label=lab)
            cid = f.split("_")[0]
            if prefix == "B" or cid in ("S01", "S02"):
                ax.text(d.index[len(d) // 2], d.max() + 0.6, cid, fontsize=6.5, color=MUTED, ha="center")
            elif cid == "S07":
                ax.text(d.index[len(d) // 2], d.max() + 1.2, "S03–S11, minimal sun", fontsize=6.5, color=MUTED, ha="center")
        ax.set_ylim(20, 45)
        panel_tag(ax, day)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
        ax.set_xlabel("local time (AEST)")
    axs[0].set_ylabel("hottest INA239 die [$^\\circ$C]")
    axs[0].legend(loc="upper left", ncol=3, fontsize=7.5)
    fig.tight_layout()
    save(fig, "thermal")


if __name__ == "__main__":
    thermal()
    mil_validate()
    twin_sim()
    qspice_run()
    bench_B06()
    solar_S02()
    duty_steps()
    metrics_k()
