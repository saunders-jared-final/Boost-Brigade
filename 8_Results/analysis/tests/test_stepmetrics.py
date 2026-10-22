import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from stepmetrics import step_metrics   # noqa: E402
import stepmetrics as sm              # noqa: E402


def first_order(t, tau, t0=0.02, yi=-1.0, yf=0.0):
    return yi + (yf - yi) * (1 - np.exp(-np.clip(t - t0, 0, None) / tau))


def second_order(t, zeta, wn, t0=0.02, k=1.0):
    tt = np.clip(t - t0, 0, None)
    wd = wn * math.sqrt(1 - zeta ** 2)
    return k * (1 - np.exp(-zeta * wn * tt) * (np.cos(wd * tt) + zeta / math.sqrt(1 - zeta ** 2) * np.sin(wd * tt)))


def test_first_order_10khz():
    t = np.arange(0, 0.2, 1e-4)
    m = step_metrics(t, first_order(t, 5e-3), 0.02)
    assert abs(m["tau"] - 5e-3) / 5e-3 < 0.05
    assert abs(m["rise_10_90"] - 2.197 * 5e-3) / (2.197 * 5e-3) < 0.05
    assert m["resolved"] and m["kind"] == "step"
    assert abs(m["t_settle_2"] - 3.9 * 5e-3) < 1e-3


def test_first_order_50hz_unresolved():
    t = np.arange(0, 1.0, 0.02)
    m = step_metrics(t, first_order(t, 5e-3), 0.02)
    assert not m["resolved"]
    assert m["n_transient_samples"] < 4


def test_first_order_50hz_slow_with_noise():
    rng = np.random.default_rng(1)
    t = np.arange(0, 1.0, 0.02)
    y = first_order(t, 0.05) + rng.normal(0, 0.01, len(t))
    m = step_metrics(t, y, 0.02, filt=("median", 3))
    assert m["resolved"]
    assert abs(m["tau"] - 0.05) / 0.05 < 0.15, m["tau"]


def test_second_order_10khz():
    t = np.arange(0, 0.2, 1e-4)
    zeta, wn = 0.5, 2 * math.pi * 100
    m = step_metrics(t, second_order(t, zeta, wn), 0.02)
    assert abs(m["overshoot_pct"] - 16.3) < 1.0, m["overshoot_pct"]
    assert m["fit_model"] == "second"
    assert abs(m["zeta"] - zeta) < 0.05 and abs(m["wn"] - wn) / wn < 0.05


def test_disturbance_small_step():
    t = np.arange(0, 0.5, 1e-3)
    y = 0.05 * np.exp(-np.clip(t - 0.1, 0, None) / 0.02) * (t >= 0.1)
    m = step_metrics(t, y, 0.1, band_floor=0.1)
    assert m["kind"] == "disturbance"
    assert abs(m["peak_dev"] - 0.05) < 0.005


def test_ss_error_against_reference():
    t = np.arange(0, 0.3, 1e-4)
    m = step_metrics(t, first_order(t, 5e-3, yi=0.0, yf=0.9), 0.02, ref=1.0)
    assert abs(m["ss_error"] + 0.1) < 0.01



def test_peak_without_overshoot():
    t = np.arange(0, 0.1, 1e-4)
    y = 1 - np.exp(-t / 0.01)
    m = sm.step_metrics(t, y, 0.0, pre=(-0.01, 0.0))
    assert m["kind"] == "step" and not m["has_overshoot"], m
    assert abs(m["peak_value"] - 1.0) < 0.02
    assert m["undershoot_pct"] == 0.0
    assert abs(m["iae"] - 0.01) < 0.002            # integral of exp(-t/tau) = tau


def test_peak_with_overshoot_and_abs_band():
    t = np.arange(0, 0.2, 1e-4)
    zeta, wn = 0.3, 2 * np.pi * 50
    wd = wn * np.sqrt(1 - zeta ** 2)
    y = 1 - np.exp(-zeta * wn * t) * (np.cos(wd * t) + zeta / np.sqrt(1 - zeta ** 2) * np.sin(wd * t))
    m = sm.step_metrics(t, y, 0.0, pre=(-0.01, 0.0), abs_band=0.05)
    assert m["has_overshoot"] and 30 < m["overshoot_pct"] < 45, m["overshoot_pct"]
    assert abs(m["t_peak"] - np.pi / wd) < 5e-4
    assert m["t_settle_abs"] > 0 and m["t_settle_abs"] <= m["t_settle_2"] + 1e-9
    assert abs(m["peak_value"] - (1 + m["overshoot_pct"] / 100)) < 1e-6


def test_undershoot():
    t = np.arange(0, 0.1, 1e-4)
    y = 1 - np.exp(-t / 0.01) - 0.3 * np.exp(-t / 0.002) * (t > 0)
    m = sm.step_metrics(t, y, 0.0, pre=(-0.01, 0.0))
    assert m["undershoot_pct"] > 10, m["undershoot_pct"]


def test_ripple_stats():
    fs = 10000.0
    t = np.arange(0, 0.5, 1 / fs)
    y = 2.0 + 0.5 * np.sin(2 * np.pi * 200 * t) + 0.01 * t
    r = sm.ripple_stats(t, y)
    assert abs(r["mean"] - 2.0025) < 0.01
    assert abs(r["pk_pk"] - 1.0) < 0.02
    assert abs(r["rms_detrended"] - 0.5 / np.sqrt(2)) < 0.01
    assert abs(r["f_dominant_hz"] - 200) < 20, r["f_dominant_hz"]
