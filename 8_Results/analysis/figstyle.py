"""One figure style for every phase (hardware, QSPICE, Simulink, analytical): fonts, colours, sizes and a saver that
writes PDF (vector, selectable text) and PNG side by side under out/figures/<family>/.

    import figstyle as fs
    fig, ax = fs.figure(cols=2, rows=3)      # slide-sized (16:9 friendly)
    fs.save(fig, "hardware", "B06_overview")  # -> out/figures/hardware/B06_overview.{pdf,png}
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import config  # noqa: E402

FIG_DIR = os.path.join(config.OUT, "figures")
PNG_DPI = 200

plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
    "font.size": 10, "axes.titlesize": 10.5, "axes.labelsize": 10, "legend.fontsize": 8.5,
    "xtick.labelsize": 9, "ytick.labelsize": 9, "figure.titlesize": 12, "figure.titleweight": "bold",
    "axes.titleweight": "bold", "axes.grid": True, "grid.alpha": 0.3, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
    "lines.linewidth": 1.1, "svg.fonttype": "none", "pdf.fonttype": 42, "figure.dpi": 100,
    "axes.formatter.useoffset": False, "axes.formatter.use_mathtext": True,
})

# signal colours (same signal = same colour in every figure)
COL = {
    "ILA1": "#1f77b4", "ILB1": "#8fbbe0", "ILA2": "#d62728", "ILB2": "#f29e9e",
    "ILA3": "#2ca02c", "ILB3": "#98df8a",
    "id1": "#1f77b4", "id2": "#d62728", "id3": "#2ca02c", "ic1": "#1f77b4", "ic2": "#d62728", "ic3": "#2ca02c",
    "VM1": "#6c6c6c", "VM2": "#1f77b4", "VM3": "#d62728", "VM4": "#2ca02c", "Vstr": "#2ca02c",
    "vd1": "#1f77b4", "vd2": "#d62728", "vd3": "#2ca02c",
    "dA1": "#1f77b4", "dB1": "#8fbbe0", "dA2": "#d62728", "dB2": "#f29e9e", "dA3": "#2ca02c", "dB3": "#98df8a",
    "Vel": "#2ca02c", "Istr": "#9467bd", "Pstr": "#b5652a", "setpoint": "#444444",
    "IM1": "#6c6c6c", "IM2": "#1f77b4", "IM3": "#d62728", "IM4": "#2ca02c",
    "rv1": "#1f77b4", "rv2": "#d62728", "beta": "#9467bd", "stress": "#b5652a",
}
LABEL = {
    "ILA1": "I_LA1", "ILB1": "I_LB1", "ILA2": "I_LA2", "ILB2": "I_LB2", "ILA3": "I_LA3", "ILB3": "I_LB3",
    "id1": "i_sh1 = I_LA1 − I_LB1", "id2": "i_sh2 = I_LA2 − I_LB2", "id3": "i_sh3",
    "ic1": "i_c1 = I_LA1 + I_LB1", "ic2": "i_c2 = I_LA2 + I_LB2", "ic3": "i_c3",
    "VM1": "V_M1", "VM2": "V_M2", "VM3": "V_M3", "VM4": "V_M4", "vd1": "v_d1 = V_M1 − V_M2", "vd2": "v_d2 = V_M2 − V_M3", "vd3": "v_d3",
    "dA1": "d_A1", "dB1": "d_B1", "dA2": "d_A2", "dB2": "d_B2", "dA3": "d_A3", "dB3": "d_B3",
    "Vel": "V_string (e-load)", "Istr": "I_string (e-load)", "Pstr": "P_string (e-load)",
    "IM1": "I_M1", "IM2": "I_M2", "IM3": "I_M3", "IM4": "I_M4",
}
UNIT = {"V": "[V]", "A": "[A]", "W": "[W]", "d": "[–]", "s": "[s]", "ms": "[ms]"}
STATE_COL = {"IDLE": "#e6e6e6", "SOFTSTART": "#ffe6a8", "RUN_OL": "#d6e9ff", "RUN_CL": "#d2f2d6", "FAULT": "#f7b7b7", "STOP": "#e8d5f5"}
EVENT_COL = {"close": "#2a9d3e", "ol_start": "#2a6fdb", "kscale_apply": "#666666", "duty_step": "#8b4513", "dutys": "#8b4513",
             "load_step": "#9467bd", "shade_on": "#7b2cbf", "shade_off": "#c77dff", "transient_on": "#e07b00", "transient_off": "#e07b00",
             "fault": "#d62728", "vref": "#000000"}


def phase_style(phase):
    return config.PHASE_STYLE.get(phase, dict(label=phase, color="#000000", ls="-"))


def figure(rows=1, cols=1, width=None, height=None, sharex=True, **kw):
    """Slide-friendly figure: 10 x 5.6 in for one panel, scaled for grids."""
    w = width or (10.0 if cols == 1 else 12.5)
    h = height or (5.6 if rows == 1 else min(2.6 * rows + 1.0, 9.5))
    fig, ax = plt.subplots(rows, cols, figsize=(w, h), sharex=sharex, constrained_layout=True, **kw)
    return fig, ax


def save(fig, family, name, png=True, pdf=True, close=True):
    d = os.path.join(FIG_DIR, family)
    os.makedirs(d, exist_ok=True)
    base = os.path.join(d, name)
    if pdf:
        fig.savefig(base + ".pdf")
    if png:
        fig.savefig(base + ".png", dpi=PNG_DPI)
    if close:
        plt.close(fig)
    return base


def decimate(t, y, n_max=4000):
    """Keep at most n_max points of a long trace, preserving min/max per bin so spikes survive."""
    t = np.asarray(t, float)
    y = np.asarray(y, float)
    if len(t) <= n_max:
        return t, y
    k = int(np.ceil(len(t) / (n_max // 2)))
    nb = len(t) // k
    tt, yy = t[:nb * k].reshape(nb, k), y[:nb * k].reshape(nb, k)
    imin, imax = np.nanargmin(yy, axis=1), np.nanargmax(yy, axis=1)
    idx = np.sort(np.concatenate([np.arange(nb) * k + imin, np.arange(nb) * k + imax]))
    return t[idx], y[idx]


def envelope(ax, t, y, color, label, rule="1s", mean_lw=1.1, alpha=0.18):
    """Long hardware trace: mean line inside a min/max band per `rule` (pandas offset), gaps preserved."""
    s = pd.Series(np.asarray(y, float), index=pd.DatetimeIndex(t)).dropna()
    if s.empty:
        return
    r = s.resample(rule)
    lo, hi, mu = r.min(), r.max(), r.mean()
    ax.fill_between(mu.index, lo.values, hi.values, color=color, alpha=alpha, lw=0)
    ax.plot(mu.index, mu.values, color=color, lw=mean_lw, label=label)


def trace(ax, t, y, color, label, raw_max=9000, rule="1s", lw=0.8, alpha=0.9, **kw):
    """Raw line when short, envelope when long. t = DatetimeIndex-like or float seconds."""
    y = np.asarray(y, float)
    if len(y) <= raw_max or not isinstance(t[0] if len(t) else None, (pd.Timestamp, np.datetime64)):
        ax.plot(t, y, color=color, lw=lw, alpha=alpha, label=label, **kw)
    else:
        envelope(ax, t, y, color, label, rule=rule)


def time_axis(ax, tz=config.LOCAL_TZ, fmt="%H:%M:%S"):
    ax.xaxis.set_major_formatter(mdates.DateFormatter(fmt, tz=tz))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(tz=tz, minticks=4, maxticks=8))


def state_bands(ax, segs, alpha=0.5, label_states=False):
    """Shade the firmware state behind an axis from a segments table with start_utc / end_utc / state."""
    for _, s in segs.iterrows():
        a, b = pd.Timestamp(s["start_utc"]), pd.Timestamp(s["end_utc"])
        ax.axvspan(a, b, color=STATE_COL.get(s["state"], "#eeeeee"), alpha=alpha, lw=0, zorder=0)


def mark_events(axes, ev, kinds=None, label_ax=None, fontsize=7):
    """Vertical dashed lines for events (DataFrame with time_utc, kind, detail)."""
    kinds = kinds or tuple(EVENT_COL)
    for _, e in ev.iterrows():
        if e["kind"] not in kinds:
            continue
        col = EVENT_COL.get(e["kind"], "#000000")
        for ax in axes:
            ax.axvline(pd.Timestamp(e["time_utc"]), color=col, lw=0.8, ls="--", alpha=0.8, zorder=1)
        if label_ax is not None:
            label_ax.annotate(e["kind"].replace("_", " "), (pd.Timestamp(e["time_utc"]), 1.0), xycoords=("data", "axes fraction"),
                              rotation=90, fontsize=fontsize, va="top", ha="right", color=col)


def legend(ax, ncol=2, loc="upper right", **kw):
    h, l = ax.get_legend_handles_labels()
    if h:
        ax.legend(h, l, ncol=ncol, loc=loc, handlelength=1.6, columnspacing=1.0, **kw)


def ylabel(ax, text, unit=None):
    ax.set_ylabel(f"{text} {UNIT.get(unit, unit or '')}".strip())
