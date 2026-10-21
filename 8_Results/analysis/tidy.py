"""Common time-series format of every phase: one DataFrame with the columns below (NaN when a phase lacks one),
time `t` in seconds relative to the event of the case, and `attrs` with phase / scenario / kscale / setup / rate_hz /
source / events. Conventions: vd1 = VM1-VM2, vd2 = VM2-VM3, ic = ILA+ILB (circulating), id = ILA-ILB (shuffled)."""
import numpy as np
import pandas as pd

COLS = ["t", "VM1", "VM2", "VM3", "vd1", "vd2", "ILA1", "ILB1", "ILA2", "ILB2", "ic1", "ic2", "id1", "id2",
        "dA1", "dB1", "dA2", "dB2", "rv1", "rv2", "beta", "stress", "kscale", "Vstr", "Istr", "Pstr", "IM1", "IM2", "IM3", "state"]
SIGNAL_LABELS = {"vd1": "VM1-VM2 [V]", "vd2": "VM2-VM3 [V]", "ic1": "ILA1+ILB1 [A]", "ic2": "ILA2+ILB2 [A]",
                 "id1": "ILA1-ILB1 [A]", "id2": "ILA2-ILB2 [A]", "dA2": "duty A2", "VM3": "VM3 [V]", "Pstr": "P string [W]"}


def _has(df, c):
    return c in df.columns and df[c].notna().any()


def derive(df):
    """Add vd / ic / id from VM / IL columns where those carry data (never overwrite a given column with NaN)."""
    if _has(df, "VM1") and _has(df, "VM2") and not _has(df, "vd1"):
        df["vd1"] = df["VM1"] - df["VM2"]
    if _has(df, "VM2") and _has(df, "VM3") and not _has(df, "vd2"):
        df["vd2"] = df["VM2"] - df["VM3"]
    for k in (1, 2):
        if _has(df, f"ILA{k}") and _has(df, f"ILB{k}"):
            if not _has(df, f"ic{k}"):
                df[f"ic{k}"] = df[f"ILA{k}"] + df[f"ILB{k}"]
            if not _has(df, f"id{k}"):
                df[f"id{k}"] = df[f"ILA{k}"] - df[f"ILB{k}"]
    return df


def frame(data, **attrs):
    df = derive(pd.DataFrame(data))
    for c in COLS:
        if c not in df:
            df[c] = np.nan
    df = df[COLS]
    df.attrs.update(attrs)
    return df


def bin_mean(t, y, dt):
    """Mean of y over consecutive bins of width dt (trapezoid on the cumulative integral): the firmware's tick average."""
    t = np.asarray(t, float)
    y = np.asarray(y, float)
    edges = np.arange(t[0], t[-1], dt)
    if len(edges) < 2:
        return edges, np.array([])
    cum = np.concatenate([[0.0], np.cumsum(0.5 * (y[1:] + y[:-1]) * np.diff(t))])
    ce = np.interp(edges, t, cum)
    return edges[:-1] + dt / 2, np.diff(ce) / dt


def to_rate(df, dt):
    """Resample a tidy frame to a fixed grid by bin means (numeric columns); state by previous value."""
    t = df["t"].to_numpy()
    out = {}
    for c in COLS:
        if c in ("t", "state"):
            continue
        y = df[c].to_numpy(float)
        if np.isfinite(y).sum() < 2:
            out[c] = None
            continue
        ok = np.isfinite(y)
        tc, yc = bin_mean(t[ok], y[ok], dt)
        out["t"] = tc
        out[c] = yc
    tc = out.pop("t")
    res = pd.DataFrame({"t": tc})
    for c, v in out.items():
        res[c] = v if v is not None else np.nan
    if "state" in df and df["state"].notna().any():
        res["state"] = pd.Series(df["state"].to_numpy(), index=t).reindex(tc, method="ffill").to_numpy()
    res.attrs.update(df.attrs)
    res.attrs["rate_hz"] = 1.0 / dt
    return res


def hold_sample(df, dt):
    """Snapshot semantics of the 50 Hz T frame: previous sample at each grid point."""
    t = df["t"].to_numpy()
    grid = np.arange(t[0], t[-1], dt)
    idx = np.searchsorted(t, grid, side="right") - 1
    res = df.iloc[np.clip(idx, 0, len(df) - 1)].copy()
    res["t"] = grid
    res.attrs.update(df.attrs)
    res.attrs["rate_hz"] = 1.0 / dt
    return res.reset_index(drop=True)
