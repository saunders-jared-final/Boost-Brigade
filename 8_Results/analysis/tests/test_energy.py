import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import energy  # noqa: E402


def _frame(seconds=30, istr=1.0, i1=1.0, i2=1.0, i3=1.0, v=20.0, vel=60.0):
    n = seconds * 44
    t = pd.date_range("2026-10-20 05:00:00", periods=n, freq="22.7ms", tz="UTC")
    df = pd.DataFrame({"t_utc": t, "VM1": v, "VM2": v, "VM3": v, "ILA1": 0.0, "ILB1": 0.0, "ILA2": 0.0, "ILB2": 0.0,
                       "id1": 0.0, "id2": 0.0, "ic1": 0.0, "ic2": 0.0, "IM1": i1, "IM2": i2, "IM3": i3, "Istr_i": istr, "Vel_i": vel,
                       "Pstr_i": istr * vel, "P_mod": v * (i1 + i2 + i3), "P_sh1": 0.0, "P_sh2": 0.0, "P_sh": 0.0})
    return df


def test_uniform_string_returns_nothing():
    e = energy.integrate(energy.means_1s(_frame()))
    assert abs(e["E_load_J"] - 30 * 60.0) < 61, e["E_load_J"]          # 60 W for 30 s (edge bins)
    assert e["E_returned_J"] == 0.0
    assert abs(e["efficiency"] - 1.0) < 1e-6


def test_dead_module_returns_everything():
    e = energy.integrate(energy.means_1s(_frame(istr=1.0, i1=-0.03, i2=1.5, i3=1.53)))
    assert abs(e["E_returned_J"] - e["E_load_J"]) < 1e-6                  # weakest module at <= 0 A: a series string gives nothing
    assert e["returned_frac"] == 1.0


def test_partial_shade_returns_the_difference():
    e = energy.integrate(energy.means_1s(_frame(istr=1.0, i1=0.6, i2=1.2, i3=1.2)))
    assert abs(e["P_returned_W"] - (1.0 - 0.6) * 60.0) < 1e-6
