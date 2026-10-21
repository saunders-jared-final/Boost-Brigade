"""nswitch.py - switching-level simulator of the N-module shuffler string, the switching twin of nstring.py.

Same ladder (module capacitors, small-signal PV conductances g_k + current sources I_k, load conductance), same
coupled windings (inductance matrix [[L, -M], [-M, L]] per shuffler), but every half bridge is switched:
  * carriers: sawtooth at f_sw, leg B of every shuffler 180 deg behind leg A (optionally a phase offset between shufflers);
  * dead time: a fraction t_d of the period at both edges (QSPICE PWM_Modulator: high side on while ramp < d - 0.04,
    low side on while d < ramp < 0.96; firmware: 200 ns = 4 % at 200 kHz);
  * during a dead time the pole follows the winding current: i > 0 (into the midpoint) -> low-side body diode
    (pole = phi_B - V_f), i < 0 -> high-side body diode (pole = phi_T + V_f); optional pole capacitance C_p
    (2 C_oss) so the pole slews at i / C_p and a transition that does not finish inside the dead time is hard-switched;
  * switches: on-resistance R_on in series with the winding path resistance R_w.

The plant is linear inside each switch configuration, so the integrator is exact: x_{k+1} = Phi_s x_k + Gamma_s w,
with Phi_s = expm(A_s h) cached per configuration. The step h is a fixed fraction of the switching period (default
1/400) and a finer one inside dead times when C_p > 0.

    import nswitch; r = nswitch.simulate(p, f_sw=200e3, T=2e-3, dA=..., dB=...)
"""
import math
from dataclasses import dataclass, field

import numpy as np
from scipy.linalg import expm

import nstring as ns


@dataclass
class SwitchCfg:
    f_sw: float = 200e3
    dead_frac: float = 0.04          # dead time per edge as a fraction of the period (QSPICE: 0.04)
    R_on: float = 0.011              # switch on-resistance [ohm] (STD45N10F7 Rd 10.9 mOhm)
    V_f: float = 0.8                 # body-diode forward drop [V]
    C_p: float = 0.0                 # pole capacitance (2 C_oss) [F]; 0 = ideal instantaneous commutation
    steps_per_period: int = 400
    dead_substeps: int = 10          # extra subdivision of each step inside a dead time when C_p > 0
    phase_shuffler: float = 0.0      # carrier offset between consecutive shufflers [fraction of a period]
    I_mod: list = None               # module currents [A] (defaults: g_k V_k, i.e. all modules at their operating point)


def _ladder_mats(p):
    Cn, Gn, S, Dv = ns.ladder(p)
    return Cn, Gn, Dv


class Plant:
    """State x = [phi_1..phi_N, (i_A, i_B) per shuffler, (phi_pA, phi_pB) per shuffler when C_p > 0]."""

    def __init__(self, p, cfg):
        self.p, self.cfg = p, cfg
        N, NS = p.N, p.N - 1
        self.N, self.NS = N, NS
        self.Cn, self.Gn, self.Dv = _ladder_mats(p)
        self.Cinv = np.linalg.inv(self.Cn)
        self.use_cp = cfg.C_p > 0
        self.nx = N + 2 * NS + (2 * NS if self.use_cp else 0)
        self.Linv = np.linalg.inv(np.array([[p.L_self, -p.M], [-p.M, p.L_self]]) if p.coupling == "inverse"
                                  else np.array([[p.L_self, p.M], [p.M, p.L_self]]))
        I = np.array(cfg.I_mod if cfg.I_mod is not None else [p.g[k] * p.V[k] for k in range(N)], float)
        # operating point: potentials from p.V, shuffled currents from the averaged equilibrium for the module currents I;
        # the constant nodal source w is chosen so that this point is the equilibrium of the ladder (the PV sources are
        # linearised: current I_k - g_k (v_k - V_k) per module, the load G_load (phi_1 - V_str) + I_str)
        self.I_mod = I
        self.eq = ns.equilibrium(p, I)
        phi_op = np.cumsum(np.array(p.V, float)[::-1])[::-1]          # phi_k = sum of module voltages below and including k
        _Cn, _Gn, S, _Dv = ns.ladder(p)
        self.phi_op = phi_op
        self.w_nodes = self.Gn @ phi_op - S @ self.eq["i_m"]
        self.cache = {}

    # -- per-leg connection codes: 0 low side on, 1 high side on, 2 dead: low diode, 3 dead: high diode, 4 dead: floating (C_p only)
    def _matrices(self, codes):
        """A, b for the configuration 'codes' (tuple of 2*NS leg codes). x' = A x + b."""
        p, cfg, N, NS, nx = self.p, self.cfg, self.N, self.NS, self.nx
        A = np.zeros((nx, nx))
        b = np.zeros(nx)
        # ladder: Cn phi' = -Gn phi + w + injections from the windings (every winding current i enters the midpoint,
        # and leaves the rail node its pole is connected to)
        Ablk = np.zeros((N, nx))
        Ablk[:, :N] = -self.Gn
        bnodes = self.w_nodes.copy()
        for j in range(NS):
            T, Mn, Bn = j, j + 1, j + 2
            for leg in range(2):
                iw = N + 2 * j + leg                      # index of the winding current
                code = codes[2 * j + leg]
                Ablk[Mn, iw] += 1.0                       # winding current into the midpoint
                if self.use_cp:
                    ip = N + 2 * NS + 2 * j + leg        # pole potential state
                    # pole node: C_p phi_p' = -i_w + (rail - phi_p)/R_on when a switch or diode conducts
                    A[ip, iw] -= 1.0 / cfg.C_p
                    if code in (1, 3):                    # tied to T through R_on (diode: with V_f offset)
                        A[ip, ip] -= 1.0 / (cfg.R_on * cfg.C_p)
                        A[ip, T] += 1.0 / (cfg.R_on * cfg.C_p)
                        if code == 3:
                            b[ip] += cfg.V_f / (cfg.R_on * cfg.C_p)
                        Ablk[T, iw] -= 1.0                # rail supplies the winding current (through R_on; the C_p current is second order)
                    elif code in (0, 2):
                        A[ip, ip] -= 1.0 / (cfg.R_on * cfg.C_p)
                        if Bn < N:
                            A[ip, Bn] += 1.0 / (cfg.R_on * cfg.C_p)
                            Ablk[Bn, iw] -= 1.0
                        if code == 2:
                            b[ip] -= cfg.V_f / (cfg.R_on * cfg.C_p)
                else:
                    if code in (1, 3):
                        Ablk[T, iw] -= 1.0
                    elif code in (0, 2) and Bn < N:
                        Ablk[Bn, iw] -= 1.0
        A[:N, :] = self.Cinv @ Ablk
        b[:N] = self.Cinv @ bnodes
        # windings: Lmat [iA', iB'] = [v_pole - phi_M - (R_w + R_on) i]
        for j in range(NS):
            T, Mn, Bn = j, j + 1, j + 2
            rows = np.zeros((2, nx))
            rhs0 = np.zeros(2)
            for leg in range(2):
                iw = N + 2 * j + leg
                code = codes[2 * j + leg]
                rows[leg, iw] -= p.R_w + cfg.R_on
                rows[leg, Mn] -= 1.0
                if self.use_cp:
                    rows[leg, N + 2 * NS + 2 * j + leg] += 1.0
                else:
                    if code in (1, 3):
                        rows[leg, T] += 1.0
                        if code == 3:
                            rhs0[leg] += cfg.V_f
                    else:
                        if Bn < N:
                            rows[leg, Bn] += 1.0
                        if code == 2:
                            rhs0[leg] -= cfg.V_f
            A[N + 2 * j:N + 2 * j + 2, :] = self.Linv @ rows
            b[N + 2 * j:N + 2 * j + 2] = self.Linv @ rhs0
        return A, b

    def step_mats(self, codes, h):
        key = (codes, h)
        if key not in self.cache:
            A, b = self._matrices(codes)
            n = self.nx
            Mx = np.zeros((n + 1, n + 1))
            Mx[:n, :n] = A * h
            Mx[:n, n] = b * h
            E = expm(Mx)
            self.cache[key] = (E[:n, :n], E[:n, n])
        return self.cache[key]


def simulate(p, f_sw=200e3, T=2e-3, dA=None, dB=None, cfg=None, x0=None, record_every=1):
    """Run the switching plant. dA, dB: per-shuffler duty functions of time (or constants). Returns dict with t,
    phi, iA, iB (arrays), derived v (module voltages), im, ic, and the configuration log."""
    cfg = cfg or SwitchCfg(f_sw=f_sw)
    cfg.f_sw = f_sw
    pl = Plant(p, cfg)
    N, NS = p.N, p.N - 1
    Tsw = 1.0 / f_sw
    h = Tsw / cfg.steps_per_period
    nsteps = int(round(T / h))
    D0 = pl.eq["D"]                                  # default duties: the averaged equilibrium of the operating point
    dA = dA if callable(dA) else (lambda t, v=dA: D0.copy() if v is None else np.asarray(v, float) * np.ones(NS))
    dB = dB if callable(dB) else (lambda t, v=dB: D0.copy() if v is None else np.asarray(v, float) * np.ones(NS))
    x = np.zeros(pl.nx) if x0 is None else np.array(x0, float)
    if x0 is None:                                   # start at the averaged operating point
        x[:N] = pl.phi_op
        for j in range(NS):
            x[N + 2 * j] = x[N + 2 * j + 1] = 0.5 * pl.eq["i_m"][j]
        if pl.use_cp:
            for j in range(NS):
                for leg in range(2):
                    x[N + 2 * NS + 2 * j + leg] = 0.5 * (x[j] + (x[j + 2] if j + 2 < N else 0.0))
    nrec = nsteps // record_every + 1
    t_out = np.zeros(nrec)
    X = np.zeros((nrec, pl.nx))
    codes_log = np.zeros((nrec, 2 * NS), np.int8)
    rec = 0
    td = cfg.dead_frac
    for k in range(nsteps):
        t = k * h
        dAk, dBk = dA(t), dB(t)
        codes = []
        for j in range(NS):
            for leg, d in ((0, dAk[j]), (1, dBk[j])):
                ph = (t / Tsw + (0.5 if leg == 1 else 0.0) + j * cfg.phase_shuffler) % 1.0    # sawtooth position
                if ph < d - td:
                    code = 1
                elif ph < d:
                    code = None                       # dead time (high -> low)
                elif ph < 1.0 - td:
                    code = 0
                else:
                    code = None                       # dead time (low -> high)
                if code is None:
                    i = x[N + 2 * j + leg]
                    if pl.use_cp:
                        phiT = x[j]
                        phiB = x[j + 2] if j + 2 < N else 0.0
                        php = x[N + 2 * NS + 2 * j + leg]
                        code = 2 if php <= phiB - cfg.V_f + 1e-6 and i > 0 else (3 if php >= phiT + cfg.V_f - 1e-6 and i < 0 else 4)
                    else:
                        code = 2 if i > 0 else 3
                codes.append(code)
        codes = tuple(codes)
        if pl.use_cp and any(c >= 2 for c in codes):
            hs = h / cfg.dead_substeps
            for _ in range(cfg.dead_substeps):
                Phi, Gam = pl.step_mats(codes, hs)
                x = Phi @ x + Gam
                # re-evaluate the diode clamps inside the dead time
                codes2 = list(codes)
                for j in range(NS):
                    for leg in range(2):
                        c = codes[2 * j + leg]
                        if c >= 2:
                            i = x[N + 2 * j + leg]
                            phiT = x[j]
                            phiB = x[j + 2] if j + 2 < N else 0.0
                            php = x[N + 2 * NS + 2 * j + leg]
                            codes2[2 * j + leg] = 2 if (php <= phiB - cfg.V_f and i > 0) else (3 if (php >= phiT + cfg.V_f and i < 0) else 4)
                codes = tuple(codes2)
        else:
            Phi, Gam = pl.step_mats(codes, h)
            x = Phi @ x + Gam
        if k % record_every == 0:
            t_out[rec], X[rec], codes_log[rec] = t, x, codes
            rec += 1
    t_out, X, codes_log = t_out[:rec], X[:rec], codes_log[:rec]
    phi = X[:, :N]
    v = np.column_stack([phi[:, k] - (phi[:, k + 1] if k + 1 < N else 0.0) for k in range(N)])
    iA = X[:, N:N + 2 * NS:2]
    iB = X[:, N + 1:N + 2 * NS:2]
    return dict(t=t_out, phi=phi, v=v, iA=iA, iB=iB, im=iA + iB, ic=iA - iB, vd=np.column_stack([v[:, j] - v[:, j + 1] for j in range(NS)]),
                codes=codes_log, cfg=cfg, h=h, nx=pl.nx)


def tick_average(t, y, Ts=100e-6):
    """Mean over consecutive Ts windows (the firmware's tick average); returns (t_tick, y_tick)."""
    n = int(np.floor(t[-1] / Ts))
    idx = np.floor(t / Ts).astype(int)
    out = np.zeros((n, y.shape[1] if y.ndim > 1 else 1))
    yy = y if y.ndim > 1 else y[:, None]
    for k in range(n):
        m = idx == k
        out[k] = yy[m].mean(axis=0)
    return (np.arange(n) + 0.5) * Ts, out


def settled(t, y, a, b):
    m = (t >= a) & (t <= b)
    return y[m].mean(axis=0)


def ripple_pp(t, y, a, b):
    m = (t >= a) & (t <= b)
    return y[m].max(axis=0) - y[m].min(axis=0)


def static_characteristic(p, f_sw, dus, j=0, T=1.5e-3, cfg=None, I_mod=None):
    """Settled i_c_j and v_d_j for a list of u_d steps on shuffler j (duties 0.5 +- u_d/2 from t = 0)."""
    rows = []
    for du in dus:
        c = cfg or SwitchCfg(f_sw=f_sw)
        if I_mod is not None:
            c.I_mod = I_mod
        D0 = ns.equilibrium(p, c.I_mod if c.I_mod is not None else [p.g[k] * p.V[k] for k in range(p.N)])["D"]
        dAv, dBv = D0.copy(), D0.copy()
        dAv[j] += du / 2
        dBv[j] -= du / 2
        r = simulate(p, f_sw=f_sw, T=T, dA=dAv, dB=dBv, cfg=c, record_every=4)
        a, b = T - 0.3e-3, T
        rows.append(dict(du=du, ic=float(settled(r["t"], r["ic"][:, j], a, b)), im=float(settled(r["t"], r["im"][:, j], a, b)),
                         vd=float(settled(r["t"], r["vd"][:, j], a, b)), ic_pp=float(ripple_pp(r["t"], r["ic"][:, j], b - 4 / f_sw, b)),
                         iA_pp=float(ripple_pp(r["t"], r["iA"][:, j], b - 4 / f_sw, b))))
    return rows


if __name__ == "__main__":
    import time
    p = ns.bench_qspice(R_w=ns.R_PHASE_SW)
    t0 = time.time()
    r = simulate(p, f_sw=200e3, T=0.5e-3, cfg=SwitchCfg(I_mod=[0.8, 1.0, 1.3]))
    print(f"{len(r['t'])} points in {time.time() - t0:.1f} s; ripple ic1 pp = {ripple_pp(r['t'], r['ic'][:, 0], 0.4e-3, 0.5e-3):.2f} A "
          f"(V T / 2(L+M) = {46.5 / (2 * 200e3 * 13.75e-6):.2f}), im1 settled {settled(r['t'], r['im'][:, 0], 0.4e-3, 0.5e-3):.3f} A, "
          f"vd1 {settled(r['t'], r['vd'][:, 0], 0.4e-3, 0.5e-3):.3f} V")
