"""One step-response metric definition for every phase (hardware at 50 Hz, simulations at 10 kHz, analytical).

    m = step_metrics(t, y, t0, ref=0.0)            # dict, see KEYS

Levels are robust (medians); the response is normalised by the measured change delta = y_final - y_initial;
rise time is 10-90 % (interpolated crossings), overshoot is against the measured final value, settling is the last
excursion outside a 2 % / 5 % band (never narrower than 3 x the pre-event noise), steady-state error is against
the reference when one is given. Steps smaller than band_floor are treated as disturbances: peak deviation and
time back inside the band. A first-order (+ delay) or second-order (+ delay) model is fitted by least squares and
returns tau or (zeta, wn) with a 1-sigma confidence interval: that fitted time constant is what makes 50 Hz
telemetry comparable with 10 kHz simulations. n_transient_samples < 4 marks the time metrics as upper bounds.
"""
import math

import numpy as np
from scipy.optimize import least_squares
from scipy.signal import medfilt

KEYS = ["y_initial", "y_final", "delta", "ss_error", "rise_10_90", "n_rise_samples", "t_peak", "peak_value", "overshoot_pct", "has_overshoot", "undershoot_pct",
        "t_settle_2", "t_settle_5", "t_settle_abs", "band_abs", "iae", "peak_dev", "band_2", "n_transient_samples", "dt_median", "resolved",
        "fit_model", "tau", "tau_ci", "zeta", "zeta_ci", "wn", "wn_ci", "delay", "fit_rmse", "fit_r2", "t_s2_fit", "kind", "noise"]


def _cross(t, z, level):
    """First time z crosses `level` upwards (linear interpolation); nan if never."""
    above = z >= level
    if not above.any():
        return math.nan
    i = int(np.argmax(above))
    if i == 0:
        return float(t[0])
    z0, z1, t0, t1 = z[i - 1], z[i], t[i - 1], t[i]
    return float(t0 + (level - z0) / (z1 - z0) * (t1 - t0)) if z1 != z0 else float(t1)


def _mad(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return math.nan
    return float(1.4826 * np.median(np.abs(x - np.median(x))))


def _first_order(p, t):
    k, tau, d = p
    tt = np.clip(t - d, 0, None)
    return k * (1 - np.exp(-tt / max(tau, 1e-9)))


def _second_order(p, t):
    k, zeta, wn, d = p
    tt = np.clip(t - d, 0, None)
    zeta = min(max(zeta, 1e-3), 0.999)
    wd = wn * math.sqrt(1 - zeta * zeta)
    return k * (1 - np.exp(-zeta * wn * tt) * (np.cos(wd * tt) + zeta / math.sqrt(1 - zeta * zeta) * np.sin(wd * tt)))


def _fit(model, p0, bounds, t, y):
    res = least_squares(lambda p: model(p, t) - y, p0, bounds=bounds, max_nfev=2000)
    r = res.fun
    dof = max(len(y) - len(p0), 1)
    s2 = float(r @ r) / dof
    try:
        cov = np.linalg.inv(res.jac.T @ res.jac) * s2
        ci = np.sqrt(np.clip(np.diag(cov), 0, None))
    except np.linalg.LinAlgError:
        ci = np.full(len(p0), math.nan)
    ss_tot = float(((y - y.mean()) ** 2).sum()) or 1e-12
    return res.x, ci, math.sqrt(s2), 1 - float(r @ r) / ss_tot


def step_metrics(t, y, t0, *, y_initial=None, y_final=None, ref=None, pre=(-0.05, 0.0), post_frac=0.2,
                 band_floor=0.1, filt=None, fit="auto", t_end=None, abs_band=None):
    """See the module docstring. abs_band (same unit as y): also report t_settle_abs, the last time |y - y_final| > abs_band.
    peak_value / t_peak are always reported; has_overshoot says whether the peak stands above the final value by more than
    the larger of 2 % and three noise sigmas (otherwise the 'peak' is the noise tail and t_peak is not a response time).
    undershoot_pct is the initial wrong-way excursion, iae the integral of |y - y_final| after t0 (unit*s)."""
    t = np.asarray(t, float)
    y = np.asarray(y, float)
    ok = np.isfinite(t) & np.isfinite(y)
    t, y = t[ok], y[ok]
    out = dict.fromkeys(KEYS, math.nan)
    out["n_rise_samples"] = 0
    if len(t) < 4:
        out.update(resolved=False, kind="empty", n_transient_samples=0)
        return out
    if t_end is None:
        t_end = float(t[-1])
    sel = t <= t_end
    t, y = t[sel], y[sel]
    yf = y
    if filt:
        k = int(filt[1]) | 1
        yf = medfilt(y, k) if len(y) > k else y
    dt = float(np.median(np.diff(t))) if len(t) > 1 else math.nan
    # levels
    pre_mask = (t >= t0 + pre[0]) & (t < t0 + pre[1])
    if pre_mask.sum() < 3:
        before = np.where(t < t0)[0]
        pre_mask = np.zeros(len(t), bool)
        pre_mask[before[-5:]] = True
    noise = _mad(yf[pre_mask]) if pre_mask.sum() >= 3 else math.nan
    if y_initial is None:
        y_initial = float(np.median(yf[pre_mask])) if pre_mask.any() else float(yf[0])
    after = t >= t0
    ta, ya, yraw = t[after] - t0, yf[after], y[after]
    if len(ta) < 2:
        out.update(resolved=False, kind="empty", n_transient_samples=0, y_initial=y_initial)
        return out
    post = ta >= (ta[-1]) * (1 - post_frac)
    if not np.isfinite(noise):                      # no pre-event samples (e.g. the first controlled frame): noise of the settled tail
        noise = _mad(ya[post]) if post.sum() >= 3 else 0.0
        if not np.isfinite(noise):
            noise = 0.0
    y_final_meas = float(np.median(ya[post])) if post.any() else float(ya[-1])
    if y_final is None:
        y_final = y_final_meas
    delta = y_final - y_initial
    out.update(y_initial=y_initial, y_final=y_final, delta=delta, dt_median=dt, noise=noise,
               ss_error=(y_final_meas - ref) if ref is not None else math.nan)
    out["iae"] = float(np.trapz(np.abs(ya - y_final), ta)) if len(ta) > 1 else math.nan
    if abs_band is not None and len(ta) > 1:
        outside = np.where(np.abs(ya - y_final) > abs_band)[0]
        out["t_settle_abs"] = float(ta[outside[-1] + 1]) if len(outside) and outside[-1] + 1 < len(ta) else (float(ta[-1]) if len(outside) else 0.0)
        out["band_abs"] = float(abs_band)
    if abs(delta) > band_floor:
        z = (ya - y_initial) / delta
        band2 = max(0.02, 3 * noise / abs(delta))
        band5 = max(0.05, 3 * noise / abs(delta))
        t10, t90 = _cross(ta, z, 0.1), _cross(ta, z, 0.9)
        ipk = int(np.argmax(z))
        out["t_peak"] = float(ta[ipk])
        out["peak_value"] = float(y_initial + z[ipk] * delta)
        out["overshoot_pct"] = float((z[ipk] - 1) * 100)
        out["has_overshoot"] = bool(z[ipk] - 1 > max(0.02, 3 * noise / abs(delta)))
        zmin = float(np.min(z[: max(ipk, 1)]))
        out["undershoot_pct"] = float(-zmin * 100) if zmin < -max(0.02, 3 * noise / abs(delta)) else 0.0
        out["rise_10_90"] = t90 - t10 if np.isfinite(t10) and np.isfinite(t90) else math.nan
        out["n_rise_samples"] = int(((ta >= t10) & (ta <= t90)).sum()) if np.isfinite(t10) and np.isfinite(t90) else 0
        for name, band in (("t_settle_2", band2), ("t_settle_5", band5)):
            outside = np.where(np.abs(z - 1) > band)[0]
            out[name] = float(ta[outside[-1] + 1]) if len(outside) and outside[-1] + 1 < len(ta) else (float(ta[-1]) if len(outside) else 0.0)
        out["band_2"] = band2 * abs(delta)
        out["kind"] = "step"
    else:
        dev = ya - y_final_meas
        band = max(band_floor, 3 * noise)
        ipk = int(np.argmax(np.abs(dev)))
        out["peak_dev"] = float(dev[ipk])
        out["t_peak"] = float(ta[ipk])
        out["peak_value"] = float(ya[ipk])
        out["has_overshoot"] = bool(abs(dev[ipk]) > band)
        outside = np.where(np.abs(dev) > band)[0]
        ts = float(ta[outside[-1] + 1]) if len(outside) and outside[-1] + 1 < len(ta) else (float(ta[-1]) if len(outside) else 0.0)
        out["t_settle_2"] = out["t_settle_5"] = ts
        out["band_2"] = band
        out["kind"] = "disturbance"
    ts2 = out["t_settle_2"]
    n_tr = int(((ta > 0) & (ta <= ts2)).sum()) if np.isfinite(ts2) else 0
    out["n_transient_samples"] = n_tr
    n_rise = out.get("n_rise_samples")
    out["resolved"] = bool(n_tr >= 4 and (n_rise is None or not np.isfinite(float(n_rise)) or n_rise >= 2))
    # model fit on the raw samples
    if fit and abs(delta) > band_floor and len(ta) >= 5:
        yn = yraw - y_initial
        tau0 = max(ts2 / 4 if np.isfinite(ts2) and ts2 > 0 else dt * 2, dt / 2)
        use_second = (fit == "second") or (fit == "auto" and n_tr >= 10)
        try:
            p1, ci1, rmse1, r21 = _fit(_first_order, [delta, tau0, 0.0], ([-np.inf, 1e-6, 0.0], [np.inf, np.inf, max(dt, 1e-6) * 3 + 1e-9]), ta, yn)
            best = ("first", p1, ci1, rmse1, r21)
            if use_second:
                wn0 = 2.0 / max(tau0, 1e-6)
                p2, ci2, rmse2, r22 = _fit(_second_order, [delta, 0.6, wn0, 0.0],
                                           ([-np.inf, 0.05, 1e-3, 0.0], [np.inf, 0.999, np.inf, max(dt, 1e-6) * 3 + 1e-9]), ta, yn)
                if rmse2 < 0.9 * rmse1:
                    best = ("second", p2, ci2, rmse2, r22)
            name, p, ci, rmse, r2 = best
            out.update(fit_model=name, fit_rmse=rmse, fit_r2=r2, delay=float(p[-1]))
            if name == "first":
                out.update(tau=float(p[1]), tau_ci=float(ci[1]), t_s2_fit=3.9 * float(p[1]))
            else:
                out.update(zeta=float(p[1]), zeta_ci=float(ci[1]), wn=float(p[2]), wn_ci=float(ci[2]),
                           t_s2_fit=4.0 / (float(p[1]) * float(p[2])))
        except Exception as e:                       # a failed fit must not kill the table
            out["fit_model"] = f"failed: {e}"
    return out


def fmt(v, unit="", nd=3):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "-"
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    return f"{v:.{nd}g}{unit}"


def bound(m, key):
    """Time metric as text: '<= 20 ms' when the transient was not resolved."""
    v = m.get(key)
    if v is None or not np.isfinite(v):
        return "-"
    ms = v * 1e3
    dt_ms = (m.get("dt_median") or 0) * 1e3
    if m.get("kind") == "step" and (not m.get("resolved", True) or (key == "rise_10_90" and (m.get("n_rise_samples") or 0) < 2)):
        b = max(ms, dt_ms)
        return f"<= {b:.0f} ms" if b >= 10 else f"<= {b:.2g} ms"
    return f"{ms:.3g} ms"


RIPPLE_KEYS = ["n", "duration", "mean", "std", "pk_pk", "pk_pk_robust", "rms_detrended", "f_dominant_hz", "p_dominant_frac", "fs_hz"]


def ripple_stats(t, y, detrend="linear", fs=None, f_min=0.0):
    """Steady-state statistics of one trace: mean, std, peak-to-peak (true and 0.5-99.5 % robust), RMS of the detrended
    signal and the dominant frequency of its Welch spectrum (above f_min). Non-uniform samples are put on a uniform grid at
    the median spacing first. For 45 Hz hardware telemetry this is sample-to-sample noise, not switching ripple."""
    from scipy.signal import welch
    t = np.asarray(t, float)
    y = np.asarray(y, float)
    ok = np.isfinite(t) & np.isfinite(y)
    t, y = t[ok], y[ok]
    out = dict.fromkeys(RIPPLE_KEYS, math.nan)
    out["n"] = int(len(y))
    if len(y) < 4:
        return out
    out["duration"] = float(t[-1] - t[0])
    out["mean"], out["std"] = float(np.mean(y)), float(np.std(y, ddof=1))
    out["pk_pk"] = float(np.max(y) - np.min(y))
    out["pk_pk_robust"] = float(np.percentile(y, 99.5) - np.percentile(y, 0.5))
    if detrend == "linear":
        c = np.polyfit(t - t[0], y, 1)
        r = y - np.polyval(c, t - t[0])
    else:
        r = y - np.mean(y)
    out["rms_detrended"] = float(np.sqrt(np.mean(r * r)))
    dt = float(np.median(np.diff(t))) if fs is None else 1.0 / fs
    if dt <= 0 or out["duration"] < 4 * dt:
        return out
    tu = np.arange(t[0], t[-1], dt)
    ru = np.interp(tu, t, r)
    out["fs_hz"] = 1.0 / dt
    if len(ru) >= 16:
        f, pxx = welch(ru, fs=1.0 / dt, nperseg=min(len(ru), 1024))
        sel = f > f_min
        if sel.any() and np.nansum(pxx[sel]) > 0:
            i = int(np.argmax(pxx[sel]))
            out["f_dominant_hz"] = float(f[sel][i])
            out["p_dominant_frac"] = float(pxx[sel][i] / np.sum(pxx[sel]))
    return out


def peak_text(m):
    """Peak time as text with the overshoot caveat."""
    if m.get("kind") != "step" or not np.isfinite(m.get("t_peak", math.nan)):
        return "-"
    txt = bound(m, "t_peak")
    return txt if m.get("has_overshoot") else "none (monotonic)"
