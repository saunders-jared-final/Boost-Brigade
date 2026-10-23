#!/usr/bin/env python3
"""Regenerate figures/misc/pv_shading.pdf: P-V curves of a 4-module series
string under the partial-shading scenarios of the EGH490-1 progress report
(2.10.3, Fig. 6), light theme for the report.

Python port of 4_Simulink/1_MIL_Model_In_The_Loop/PV_Modelling/
pv_string_validation.m: single-diode AIKO Neostar A555 module, bypass diode
at -0.7 V, string I-V found by sweeping the string current.

    python3 tools/make_pv_shading.py"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.optimize import brentq

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "figures", "misc", "pv_shading.pdf")

# AIKO Neostar A555 datasheet + fitted single-diode parameters (as in the .m)
ISC, VOC, NS, KI, KV, TSTC = 14.96, 45.90, 60, 0.05, -0.22, 298.15
A, RS, RSH = 1.0, 0.158, 51807
V_BYPASS = 0.7
T_CELL = 25.0

SCENARIOS = [  # irradiance [W/m2], top module first
    ("Uniform 1000 W/m²",            [1000, 1000, 1000, 1000]),
    ("One module shaded (500)",      [1000, 1000, 1000,  500]),
    ("One module heavy shade (200)", [1000, 1000, 1000,  200]),
    ("Two modules shaded",           [1000, 1000,  500,  500]),
    ("Graduated shading",            [1000,  800,  500,  200]),
]
COLOURS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]   # validated categorical, light
STYLES = ["-", "-", (0, (5, 2)), "-", (0, (1.5, 1.5))]


def module_iv(G):
    """Module I-V curve at irradiance G (pv_module_iv in the .m)."""
    q, k = 1.602176634e-19, 1.380649e-23
    T = T_CELL + 273.15
    nsvt = NS * A * k * T / q
    isc_t = ISC * (1 + KI / 100 * (T - TSTC))
    voc_t = VOC * (1 + KV / 100 * (T - TSTC))
    io = (isc_t - (voc_t - isc_t * RS) / RSH) * np.exp(-voc_t / nsvt)
    iph = (io * np.exp(voc_t / nsvt) + voc_t / RSH) * G / 1000
    voc_g = brentq(lambda v: iph - io * np.exp(v / nsvt) - v / RSH, 0.1, 2 * VOC)
    V = np.linspace(0, voc_g, 1000)
    I = np.array([brentq(lambda i: iph - io * (np.exp((v + i * RS) / nsvt) - 1) - (v + i * RS) / RSH - i,
                         -1.0, iph + 1.0) for v in V])
    return V, np.clip(I, 0, None)


def string_pv(G_vec):
    curves = [module_iv(G) for G in G_vec]
    isc_max = max(I[0] for _, I in curves)
    I_sweep = np.linspace(isc_max, 0, 2000)
    V_str = np.zeros_like(I_sweep)
    for V, I in curves:
        # I falls with V; above the module's Isc its bypass diode conducts
        v_mod = np.interp(I_sweep, I[::-1], V[::-1])
        V_str += np.where(I_sweep > I[0], -V_BYPASS, v_mod)
    ok = V_str >= 0
    V_str, I_str = V_str[ok], I_sweep[ok]
    order = np.argsort(V_str)
    return V_str[order], (V_str * I_str)[order]


def local_maxima(V, P, min_prom=20.0):
    """Peaks of P(V) that stand at least min_prom W above the following dip."""
    idx = [i for i in range(1, len(P) - 1) if P[i] >= P[i - 1] and P[i] > P[i + 1]]
    return [i for i in idx if P[i] - P[i:].min() > min_prom]


def main():
    plt.rcParams.update({"font.family": "serif", "font.serif": ["STIXGeneral", "Times New Roman", "DejaVu Serif"], "mathtext.fontset": "stix", "font.size": 9, "axes.edgecolor": "#8a8a85",
                         "axes.labelcolor": "#2b2b2a", "xtick.color": "#555550", "ytick.color": "#555550"})
    fig, ax = plt.subplots(figsize=(5.4, 3.3))
    for (name, G), c, ls in zip(SCENARIOS, COLOURS, STYLES):
        V, P = string_pv(G)
        g = int(np.argmax(P))
        ax.plot(V, P, color=c, lw=1.6, ls=ls, label=f"{name}: {P[g]:.0f} W at {V[g]:.0f} V", zorder=2)
        for i in local_maxima(V, P):
            if i != g:   # hollow ring = local maximum an MPPT can get stuck on
                ax.plot(V[i], P[i], "o", ms=5.5, mfc="white", mec=c, mew=1.4, zorder=3)
        ax.plot(V[g], P[g], "o", ms=6.5, color=c, mec="white", mew=1.2, zorder=4)
        print(f"{name:30s} G={G}  Pmpp={P[g]:7.1f} W  Vmpp={V[g]:5.1f} V  "
              f"local maxima at {[round(float(V[i])) for i in local_maxima(V, P)]} V")
    ax.set_xlabel("String voltage [V]")
    ax.set_ylabel("String power [W]")
    ax.set_xlim(0, 190)
    ax.set_ylim(0, 2400)
    ax.grid(color="#e4e3df", lw=0.6)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    h, l = ax.get_legend_handles_labels()
    h += [plt.Line2D([], [], ls="none", marker="o", ms=6.5, color="#555550", mec="white"),
          plt.Line2D([], [], ls="none", marker="o", ms=5.5, mfc="white", mec="#555550", mew=1.4)]
    l += ["global maximum", "local maximum"]
    ax.legend(h, l, loc="upper left", frameon=False, fontsize=8, handlelength=2.6)
    fig.tight_layout()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    fig.savefig(OUT)
    fig.savefig(OUT.replace(".pdf", ".png"), dpi=150)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
