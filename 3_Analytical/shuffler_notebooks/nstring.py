"""nstring.py - averaged model of a string of N PV modules with N-1 interleaved buck-boost "power shufflers" on
inverse-coupled inductors: nodal ladder of the modules + sum / difference winding modes of every shuffler.
Large-signal equilibrium, small-signal state space, DC gain G(N), modes, controllability / observability,
the deployed PI + decoupler closed loop and the predictions used by 8_Results/analysis.

Variables (firmware / telemetry conventions, modules counted from the top; see shuffler_nstring.ipynb section 1)
    n_k        node k of the ladder, k = 1..N+1 (n_1 = string +, n_{N+1} = ground), potential phi_k
    v_k        voltage of module k = phi_k - phi_{k+1}        (telemetry VMk)
    I_k, g_k   module current at the operating point and small-signal conductance -dI/dv (PV: ~Imp/Vmp; CV PSU: large; CC PSU: 0)
    C_k        capacitance across module k (both shuffler capacitors that share it, in parallel)
    shuffler j spans modules j (upper) and j+1 (lower): rails T_j = n_j, B_j = n_{j+2}, midpoint M_j = n_{j+1}; Vbar_j = v_j + v_{j+1}
    d_A, d_B   high-side duties of legs A and B;   u_c = d_A + d_B - 1 (common),  u_d = d_A - d_B (differential)
    i_A, i_B   winding currents, positive from the pole through the winding INTO the midpoint
    i_m = i_A + i_B   shuffled (midpoint-injection) current   = ILA - ILB in telemetry  (sum mode, inductance L_m = L - M)
    i_c = i_A - i_B   circulating (pole-to-pole) current      = ILA + ILB in telemetry  (difference mode, L_c = L + M)
    L, M       self and mutual inductance of the coupled windings (ERUC23-4R1K: L = 2.05 uH leakage + 5.85 uH magnetising,
               M = 5.85 uH); as built the magnetising current is i_A - i_B (QSPICE subcircuit, turns 1:-1), so the circulating
               mode sees L + M = 13.75 uH and the shuffled mode the leakage L - M = 2.05 uH
    R_w        series resistance of one winding path (copper + switch + sense); R_m, R_c per mode (default R_w)
    y = [vd_j = v_j - v_{j+1}, i_c_j]   controlled outputs;  u = [u_c_j, u_d_j]  (identification order uc_1..uc_{N-1}, ud_1..)

    python3 nstring.py          # N = 2 check against the 2026 identification, G(3), equilibrium check against QSPICE, poles
"""
import glob
import json
import math
import os
from dataclasses import dataclass, field

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", ".."))
PARAMS_DIR = os.path.join(REPO, "6_RTOS", "ctrl_core", "params")

KI_V, KI_I = 2 * math.pi * 150, 2 * math.pi * 400
KP_V, KP_I = 1.58e-4, 1.08e-4
TS, FC = 100e-6, 2000.0
L_SELF, L_MUT = 7.9e-6, 5.85e-6           # ERUC23-4R1K: 2.05 uH leakage + 5.85 uH magnetising per winding, M = 5.85 uH
R_PHASE_SIM = 0.061                       # Simulink averaged model: per-phase damping resistor (decision 3.2)
R_PHASE_SW = 0.016                        # QSPICE: Rdc 1.85 m + STD45N10F7 ~11 m + hall 0.7 m + traces (ideal-switch value)


@dataclass
class Params:
    N: int = 3
    V: list = field(default_factory=lambda: [20.5, 20.5, 20.5])    # module voltages at the operating point [V]
    g: list = field(default_factory=lambda: [0.19, 0.19, 0.19])    # module small-signal conductance -dI/dV at the op. point [S]
    C: list = field(default_factory=lambda: [130e-6, 260e-6, 130e-6])   # capacitance across each module [F]
    I: list = None                     # module currents at the operating point [A] (equilibrium); None = balanced
    L_self: float = L_SELF
    M: float = L_MUT
    coupling: str = "inverse"          # "inverse" (as built: i_c sees L+M) or "direct" (the pre-decision-1.4 wiring: i_m sees L+M)
    L_m: float = None                  # override: sum-mode inductance
    L_c: float = None                  # override: difference-mode inductance
    R_w: float = R_PHASE_SIM           # series resistance of one winding path [ohm]
    R_m: float = None                  # resistance of the sum mode (default R_w)
    R_c: float = None                  # resistance seen by the circulating mode (default R_w; switching plant: effective 0.29 ohm at 200 kHz)
    G_load: float = 20.0               # load conductance at the top node (DL3021 in CV: 1 / 0.05 ohm); ~0 for a current sink
    i_m0: list = None                  # shuffled current at the operating point per shuffler [A] (0 = balanced)
    label: str = ""

    def __post_init__(self):
        assert len(self.V) == len(self.g) == len(self.C) == self.N
        if self.coupling == "inverse":
            Lm, Lc = self.L_self - self.M, self.L_self + self.M
        else:
            Lm, Lc = self.L_self + self.M, self.L_self - self.M
        self.L_m = Lm if self.L_m is None else self.L_m
        self.L_c = Lc if self.L_c is None else self.L_c
        self.R_m = self.R_w if self.R_m is None else self.R_m
        self.R_c = self.R_w if self.R_c is None else self.R_c
        if self.i_m0 is None:
            self.i_m0 = equilibrium(self, self.I)["i_m"].tolist() if self.I is not None else [0.0] * (self.N - 1)

    @property
    def NS(self):
        return self.N - 1

    def Vbar(self, j):
        return self.V[j] + self.V[j + 1]


def pv80(N=3, **kw):
    """3 x KAUSSP80 at Vmp (g about Imp/Vmp), DL3021 CV load."""
    kw.setdefault("label", "PV80 (CV load)")
    return Params(N=N, V=[20.5] * N, g=[0.19] * N, C=[130e-6] + [260e-6] * (N - 2) + [130e-6], **kw)


def bench(N=3, cc_channel=1, **kw):
    """Bench: NGE103 channels at 25 V with one channel in current limit (g = 0, its voltage sags to about 20 V) and
    the others in CV (stiff: the QSPICE nge_ch model clamps through 0.05 ohm, g = 20 S). The QSPICE S10 netlist
    (ILIM1 = 0.8 A lowest) puts channel 1 in current limit; on the 16 Oct bench the middle module sat at 20 V, so
    use cc_channel=2 for the hardware wiring."""
    V = [25.0] * N
    g = [20.0] * N
    V[cc_channel - 1], g[cc_channel - 1] = 20.0, 0.0
    kw.setdefault("label", f"BENCH (PSU ch{cc_channel} in CC, CV load)")
    return Params(N=N, V=V, g=g, C=[130e-6] + [260e-6] * (N - 2) + [130e-6], **kw)


def bench_qspice(N=3, V=23.3, **kw):
    """The QSPICE S10i identification point: CV load at 70 V holds the string, the shufflers equalise the three
    nge_ch channels at ~23.3 V, i.e. BELOW their 25 V set point, so all three are in current limit (g = 0) and the
    module currents are the limits 0.8 / 1.0 / 1.3 A."""
    kw.setdefault("label", "BENCH QSPICE S10i (all channels in CC, CV load)")
    kw.setdefault("I", [0.8, 1.0, 1.3][:N] if N == 3 else None)
    return Params(N=N, V=[V] * N, g=[0.0] * N, C=[130e-6] + [260e-6] * (N - 2) + [130e-6], **kw)


# ----------------------------------------------------------------------------- large-signal equilibrium
def laplacian(N):
    """T(N): (N-1) x (N-1) tridiagonal (-1/2, 1, -1/2) charge-balance matrix of the shuffled currents at D = 1/2."""
    T = np.eye(N - 1)
    for j in range(N - 2):
        T[j, j + 1] = T[j + 1, j] = -0.5
    return T


def green(N):
    """Closed form of T(N)^-1: 2 min(j,k) (N - max(j,k)) / N  (Green's function of the Dirichlet ladder)."""
    G = np.zeros((N - 1, N - 1))
    for j in range(1, N):
        for k in range(1, N):
            G[j - 1, k - 1] = 2.0 * min(j, k) * (N - max(j, k)) / N
    return G


def equilibrium(p, I_mod, iters=3):
    """Averaged equilibrium of the string for module currents I_mod (A) at the module voltages p.V:
    charge balance at every interior node  i_m_j - (1 - D_{j-1}) i_m_{j-1} - D_{j+1} i_m_{j+1} = I_j - I_{j+1},
    volt-second balance per shuffler       D_j Vbar_j - v_{j+1} = R_m i_m_j / 2,
    string current from the top node       I_str = I_1 - D_1 i_m_1.
    Returns i_m, D, I_str, vd_drop (= v_j - v_{j+1} the loop would see at D = 1/2, R_m i_m)."""
    N = p.N
    I = np.asarray(I_mod, float)
    dI = I[:-1] - I[1:]
    D = np.array([p.V[j + 1] / p.Vbar(j) for j in range(N - 1)])
    i_m = np.linalg.solve(laplacian(N), dI)
    for _ in range(iters):                                   # duty-dependent charge balance, R drop in the volt-seconds
        T = np.eye(N - 1)
        for j in range(N - 2):
            T[j, j + 1] = -D[j + 1]
            T[j + 1, j] = -(1 - D[j])
        i_m = np.linalg.solve(T, dI)
        D = np.array([(p.V[j + 1] + p.R_m * i_m[j] / 2) / p.Vbar(j) for j in range(N - 1)])
    return dict(i_m=i_m, D=D, I_str=float(I[0] - D[0] * i_m[0]), I_mean=float(I.mean()), vd_drop=p.R_m * i_m)


# ----------------------------------------------------------------------------- small-signal state space
def ladder(p):
    """Nodal capacitance and conductance matrices of the module ladder (node N+1 = ground), the shuffler injection
    matrix S (i_m_j: +1 at M_j, -1/2 at T_j and B_j) and the output selector Dv (vd_j from the potentials)."""
    N, NS = p.N, p.N - 1
    Cn, Gn = np.zeros((N, N)), np.zeros((N, N))
    for k in range(N):                       # module k between node k and node k+1
        a, b = k, k + 1
        for (i, j, s) in ((a, a, 1), (b, b, 1), (a, b, -1), (b, a, -1)):
            if i < N and j < N:
                Cn[i, j] += s * p.C[k]
                Gn[i, j] += s * p.g[k]
    Gn[0, 0] += p.G_load
    S = np.zeros((N, NS))
    for j in range(NS):
        T, Mn, Bn = j, j + 1, j + 2
        S[Mn, j] += 1.0
        S[T, j] -= 0.5
        if Bn < N:
            S[Bn, j] -= 0.5
    Dv = np.zeros((NS, N))
    for j in range(NS):
        Dv[j, j] += 1.0
        Dv[j, j + 1] -= 2.0
        if j + 2 < N:
            Dv[j, j + 2] += 1.0
    return Cn, Gn, S, Dv


def build_ss(p):
    """x = [phi_1..phi_N, i_m_1..i_m_{N-1}, i_c_1..i_c_{N-1}]; u = [uc_1.., ud_1..]; w = PV current steps per module;
    y = [vd_1..vd_{N-1}, ic_1..ic_{N-1}]. Returns A, B, Bw, C, D (continuous time)."""
    N, NS = p.N, p.N - 1
    nx = N + 2 * NS
    Cn, Gn, S, Dv = ladder(p)
    Su = np.zeros((N, 2 * NS))               # u_c moves the rail currents: -(i_m0/2) u_c at T and B (second-order u_d i_c0 term dropped)
    for j in range(NS):
        T, Bn = j, j + 2
        Su[T, j] -= 0.5 * p.i_m0[j]
        if Bn < N:
            Su[Bn, j] -= 0.5 * p.i_m0[j]
    Cinv = np.linalg.inv(Cn)
    A = np.zeros((nx, nx))
    B = np.zeros((nx, 2 * NS))
    Bw = np.zeros((nx, N))                   # PV current step of module k: +w at its top node, -w at its bottom node
    A[:N, :N] = -Cinv @ Gn
    A[:N, N:N + NS] = Cinv @ S
    B[:N, :] = Cinv @ Su
    for k in range(N):
        Bw[k, k] += 1.0
        if k + 1 < N:
            Bw[k + 1, k] -= 1.0
    Bw[:N, :] = Cinv @ Bw[:N, :]
    for j in range(NS):
        Vbar = p.Vbar(j)
        r = N + j                            # sum mode: L_m di_m/dt = u_c Vbar + vd_j - R_m i_m
        A[r, :N] = Dv[j] / p.L_m
        A[r, r] = -p.R_m / p.L_m
        B[r, j] = Vbar / p.L_m
        rc = N + NS + j                      # difference mode: L_c di_c/dt = u_d Vbar - R_c i_c
        A[rc, rc] = -p.R_c / p.L_c
        B[rc, NS + j] = Vbar / p.L_c
    C = np.zeros((2 * NS, nx))
    C[:NS, :N] = Dv
    C[NS:, N + NS:] = np.eye(NS)
    D = np.zeros((2 * NS, 2 * NS))
    return A, B, Bw, C, D


def dc_gain(p):
    A, B, _Bw, C, D = build_ss(p)
    return -C @ np.linalg.solve(A, B) + D


def dc_gain_closed_form(p):
    """G(N) without the state space: voltage block -diag(Vbar) (I + R_m Ge)^-1 ... evaluated through the ladder's DC
    conductance: vd = -Z_e (i_m) with Z_e = Dv Gn^-1 S the (N-1)x(N-1) transfer impedance of the ladder; at DC
    i_m = (Vbar u_c + vd) / R_m  =>  vd = -(I + Z_e / R_m)^-1 Z_e diag(Vbar) u_c / R_m, i_c = diag(Vbar) u_d / R_c."""
    N, NS = p.N, p.N - 1
    Cn, Gn, S, Dv = ladder(p)
    Ze = -Dv @ np.linalg.solve(Gn + 1e-9 * np.eye(p.N), S)   # vd = -Ze i_m: transfer impedance of the ladder (ohm, > 0 on the diagonal)
    Vb = np.diag([p.Vbar(j) for j in range(NS)])
    Gv = -np.linalg.solve(np.eye(NS) * p.R_m + Ze, Ze @ Vb)
    G = np.zeros((2 * NS, 2 * NS))
    G[:NS, :NS] = Gv
    G[NS:, NS:] = Vb / p.R_c
    return G, Ze


def tf_gain(p, w):
    A, B, _Bw, C, D = build_ss(p)
    s = 1j * w
    return C @ np.linalg.solve(s * np.eye(len(A)) - A, B) + D


def modes(p):
    """Eigenvalues of the open-loop plant: list of (frequency Hz, damping ratio, kind)."""
    A, *_ = build_ss(p)
    out = []
    for lam in np.linalg.eigvals(A):
        if abs(lam.imag) > 1e-6 and lam.imag > 0:
            wn = abs(lam)
            out.append((wn / (2 * math.pi), -lam.real / wn, "oscillatory"))
        elif abs(lam.imag) <= 1e-6:
            out.append((abs(lam.real) / (2 * math.pi), 1.0, "real"))
    return sorted(out)


def reduced_voltage_mode(p, j):
    """Second-order model of the voltage mode of shuffler j seen alone: C_e dvd/dt = -i_m - g_e vd,
    L_m di_m/dt = Vbar u_c + vd - R_m i_m, with C_e, g_e from the ladder (vd_j per unit i_m_j at DC and at high
    frequency). Returns dict(C_e, g_e, f0, zeta, A2, B2)."""
    Cn, Gn, S, Dv = ladder(p)
    Gn = Gn + 1e-9 * np.eye(p.N)                             # g = 0 everywhere (CC supplies): the DC impedance is infinite, g_e -> 0
    ge = -1.0 / (Dv @ np.linalg.solve(Gn, S))[j, j]         # vd_j = -i_m_j / g_e at DC
    Ce = -1.0 / (Dv @ np.linalg.solve(Cn, S))[j, j]         # C_e dvd_j/dt = -i_m_j at high frequency
    w0 = 1 / math.sqrt(p.L_m * Ce)
    zeta = 0.5 * (p.R_m * math.sqrt(Ce / p.L_m) + ge * math.sqrt(p.L_m / Ce))
    A2 = np.array([[-ge / Ce, -1 / Ce], [1 / p.L_m, -p.R_m / p.L_m]])
    B2 = np.array([[0.0], [p.Vbar(j) / p.L_m]])
    return dict(C_e=Ce, g_e=ge, f0=w0 / (2 * math.pi), zeta=zeta, A2=A2, B2=B2)


def cond_vs_N(make, Ns=range(2, 9)):
    return {N: float(np.linalg.cond(dc_gain(make(N)))) for N in Ns}


def structure(G, NS):
    """Blocks of G: [vd ; ic] x [uc ; ud] -> dict of the four blocks."""
    return {"vd/uc": G[:NS, :NS], "vd/ud": G[:NS, NS:], "ic/uc": G[NS:, :NS], "ic/ud": G[NS:, NS:]}


# ----------------------------------------------------------------------------- controllability / observability
def ctrb(A, B):
    cols, M = [B], B
    for _ in range(1, A.shape[0]):
        M = A @ M
        cols.append(M)
    return np.hstack(cols)


def obsv(A, C):
    rows, M = [C], C
    for _ in range(1, A.shape[0]):
        M = M @ A
        rows.append(M)
    return np.vstack(rows)


def _scaled(p, w_ref=2 * math.pi * 1e4):
    """A, B, C in per-unit form: potentials in 20 V, currents in A, time in 1/w_ref (entries O(1) so ranks are meaningful)."""
    A, B, Bw, C, D = build_ss(p)
    N, NS = p.N, p.N - 1
    Dx = np.diag([1.0 / 20.0] * N + [1.0] * (2 * NS))
    return Dx @ A @ np.linalg.inv(Dx) / w_ref, Dx @ B / w_ref, C @ np.linalg.inv(Dx), Dx


def pbh(p, tol=1e-6):
    """PBH test per eigenvalue of the scaled plant: smallest singular value of [A - lambda I, B_group] (0 =
    uncontrollable from that input group) and of [A - lambda I; C] (0 = unobservable from y). Returns a list of
    dicts sorted by frequency with the mode shape (|eigenvector| normalised, states [phi_1..N, i_m.., i_c..])."""
    As, Bs, Cs, Dx = _scaled(p)
    N, NS = p.N, p.N - 1
    n = As.shape[0]
    lam, V = np.linalg.eig(As)
    out = []
    for k in range(n):
        if lam[k].imag < -1e-9:
            continue
        row = dict(f_hz=abs(lam[k]) * 1e4, zeta=(-lam[k].real / abs(lam[k]) if abs(lam[k]) > 1e-12 else 1.0),
                   real_hz=lam[k].real * 1e4, imag_hz=lam[k].imag * 1e4)
        for name, Bg in (("u_c", Bs[:, :NS]), ("u_d", Bs[:, NS:]), ("u", Bs)):
            row["ctrb_" + name] = float(np.linalg.svd(np.hstack([As - lam[k] * np.eye(n), Bg]), compute_uv=False)[-1])
        row["obsv_y"] = float(np.linalg.svd(np.vstack([As - lam[k] * np.eye(n), Cs]), compute_uv=False)[-1])
        row["obsv_vd"] = float(np.linalg.svd(np.vstack([As - lam[k] * np.eye(n), Cs[:NS]]), compute_uv=False)[-1])
        v = V[:, k]
        row["shape"] = np.round(np.abs(v) / np.abs(v).max(), 2)
        row["controllable"] = row["ctrb_u"] > tol
        row["observable"] = row["obsv_y"] > tol
        out.append(row)
    return sorted(out, key=lambda r: r["f_hz"])


def ranks(p, tol=1e-6):
    """Controllable / observable dimensions from the PBH test (n minus the modes that fail it)."""
    rows = pbh(p, tol)
    n = p.N + 2 * (p.N - 1)
    mult = lambda r: 2 if abs(r["imag_hz"]) > 1e-6 else 1
    cnt = lambda key: n - sum(mult(r) for r in rows if r[key] <= tol)
    return dict(n=n, ctrb_u=cnt("ctrb_u"), ctrb_uc=cnt("ctrb_u_c"), ctrb_ud=cnt("ctrb_u_d"), obsv_y=cnt("obsv_y"), obsv_vd_only=cnt("obsv_vd"))


# ----------------------------------------------------------------------------- identified G (hardware-side sources)
def identified_G():
    """G = diag(kI) M^-1 from every gain-set JSON (6_RTOS/ctrl_core/params), M in the firmware layout
    (u = M e, u = [uc1, uc2, ud1, ud2], e = [evd1, evd2, eic1, eic2])."""
    out = {}
    for path in sorted(glob.glob(os.path.join(PARAMS_DIR, "shuffler_params*.json"))):
        try:
            d = json.load(open(path))
            M = np.array(d["ctrl"]["M"], float)
            n = M.shape[0] // 2
            kI = np.diag([KI_V] * n + [KI_I] * n)
            out[d.get("version", os.path.basename(path))] = kI @ np.linalg.inv(M)
        except Exception as e:                     # noqa: BLE001
            out[os.path.basename(path)] = f"unreadable: {e}"
    return out


# ----------------------------------------------------------------------------- closed loop (the firmware's PI + decoupler, Ts, LPF)
def discretise(A, B, Ts):
    from scipy.linalg import expm
    n, m = A.shape[0], B.shape[1]
    Mx = np.zeros((n + m, n + m))
    Mx[:n, :n] = A * Ts
    Mx[:n, n:] = B * Ts
    E = expm(Mx)
    return E[:n, :n], E[:n, n:]


class ClosedLoop:
    """Discrete closed loop at Ts: ZOH plant, first-order LPF on y, PI u = kscale (Mp e + M xi), xi += Ts e,
    one-tick computation delay on u (the firmware applies the duties at the next tick)."""

    def __init__(self, p, M=None, kscale=1.0, kp_v=KP_V, kp_i=KP_I, fc=FC, Ts=TS):
        self.p, self.Ts = p, Ts
        A, B, Bw, C, D = build_ss(p)
        Ad, Bd = discretise(A, np.hstack([B, Bw]), Ts)
        self.Ad, self.Bd, self.Bwd, self.C = Ad, Bd[:, :B.shape[1]], Bd[:, B.shape[1]:], C
        NS = p.N - 1
        G = dc_gain(p)
        kI = np.diag([KI_V] * NS + [KI_I] * NS)
        self.M = (np.linalg.solve(G, kI) if M is None else np.array(M, float)) * kscale
        self.Mp = self.M @ np.diag([kp_v] * NS + [kp_i] * NS)
        self.a = 2 * math.pi * fc * Ts / (1 + 2 * math.pi * fc * Ts)
        self.ny, self.nu = C.shape[0], B.shape[1]

    def A_cl(self):
        """State matrix of the closed loop with z = [x, yf, xi, u_prev] (for poles)."""
        nx, ny, nu = self.Ad.shape[0], self.ny, self.nu
        n = nx + ny + ny + nu
        A = np.zeros((n, n))
        ix, iyf, ixi, iu = slice(0, nx), slice(nx, nx + ny), slice(nx + ny, nx + 2 * ny), slice(nx + 2 * ny, n)
        A[ix, ix] = self.Ad
        A[ix, iu] = self.Bd
        A[iyf, iyf] = (1 - self.a) * np.eye(ny)
        A[iyf, ix] = self.a * self.C
        E_x = -self.a * self.C
        E_yf = -(1 - self.a) * np.eye(ny)
        A[ixi, ixi] = np.eye(ny)
        A[ixi, ix] = self.Ts * E_x
        A[ixi, iyf] = self.Ts * E_yf
        A[iu, ix] = self.Mp @ E_x + self.M @ (self.Ts * E_x)
        A[iu, iyf] = self.Mp @ E_yf + self.M @ (self.Ts * E_yf)
        A[iu, ixi] = self.M
        return A

    def poles(self):
        z = np.linalg.eigvals(self.A_cl())
        s = np.log(z.astype(complex)) / self.Ts
        out = []
        for lam in s:
            if abs(lam) < 1e-3:
                continue
            if lam.imag > 1e-6:
                out.append((abs(lam) / (2 * math.pi), -lam.real / abs(lam)))
            elif abs(lam.imag) <= 1e-6:
                out.append((abs(lam.real) / (2 * math.pi), 1.0))
        return sorted(out)

    def simulate(self, T, r=None, w=None, x0=None):
        """Time response: r(t) reference vector (ny), w(t) PV current steps (N), x0 initial plant state. Returns t, y, u."""
        n = int(round(T / self.Ts))
        nx, ny, nu = self.Ad.shape[0], self.ny, self.nu
        x = np.zeros(nx) if x0 is None else np.array(x0, float)
        yf, xi, u = np.zeros(ny), np.zeros(ny), np.zeros(nu)
        t = np.arange(n) * self.Ts
        Y, U, X = np.zeros((n, ny)), np.zeros((n, nu)), np.zeros((n, nx))
        self.X = X
        for k in range(n):
            tk = t[k]
            rk = r(tk) if r is not None else np.zeros(ny)
            wk = w(tk) if w is not None else np.zeros(self.p.N)
            y = self.C @ x
            Y[k], U[k], X[k] = y, u, x
            yf = yf + self.a * (y - yf)
            e = rk - yf
            xi = xi + self.Ts * e
            u_next = self.Mp @ e + self.M @ xi
            x = self.Ad @ x + self.Bd @ u + self.Bwd @ wk
            u = u_next
        return t, Y, U

    def ol_fixed_point(self, w):
        """Plant state with duties at 0.5 (u = 0) under a constant PV-current disturbance vector w."""
        A, B, Bw, C, D = build_ss(self.p)
        return -np.linalg.solve(A, Bw @ np.asarray(w, float))


# ----------------------------------------------------------------------------- predictions used by the comparison
def design_numbers(kscale):
    """Pure-integral closed loop kI/(s+kI): time constants and 10-90 / 2 % times per loop."""
    out = {}
    for name, kI in (("vd", KI_V), ("ic", KI_I)):
        tau = 1 / (kscale * kI)
        out[name] = dict(tau=tau, rise_10_90=2.197 * tau, t_settle_2=3.912 * tau, bandwidth_hz=kscale * kI / (2 * math.pi))
    return out


def how_far_off(p, measured=None):
    """Predicted vs measured numbers of the retrospective and of the 3-module identification."""
    NS = p.N - 1
    G = dc_gain(p)
    rows = [("u_d -> i_c DC gain [A/unit]", float(G[NS, NS]), "-1250 string (2026-07-16), -200 two-module", "sign: convention of ILA/ILB"),
            ("u_c -> v_d DC gain [V/unit]", float(G[0, 0]), "-71.8 .. -76.5", "")]
    for f, z, kind in modes(p):
        if kind == "oscillatory":
            rows.append(("resonance [Hz] / damping", f"{f:.0f} Hz, zeta {z:.2f}", "6340 Hz, zeta 0.53 (two-module ident)", ""))
            break
    return rows


def fmt_matrix(G, nd=1):
    return "\n".join("  [" + "  ".join(f"{v:9.{nd}f}" for v in row) + "]" for row in np.atleast_2d(G))


def main():
    np.set_printoptions(precision=3, suppress=True, linewidth=140)
    two = Params(N=2, V=[38.7, 38.7], g=[0.37, 0.37], C=[100e-6, 100e-6], R_w=0.028, R_c=0.386, G_load=1e-3, label="2026 two-module (battery path in the loop)")
    print("N = 2 check (2026-06-27 identification: u_c->v_d -76.5 V/unit, u_d->i_c 200 A/unit, u_c->i_m -32 A/unit):")
    print(fmt_matrix(dc_gain(two)))
    print("  modes:", [(f"{f:.0f} Hz", f"zeta {z:.2f}") for f, z, k in modes(two) if k == "oscillatory"])
    b = bench()
    eq = equilibrium(b, [0.8, 1.0, 1.3])
    print("\nequilibrium, QSPICE S10i baseline (ILIM 0.8 / 1.0 / 1.3 A): i_m =", eq["i_m"], " D =", eq["D"], f" I_str = {eq['I_str']:.3f} (mean {eq['I_mean']:.3f})")
    print("  QSPICE RUN 1 settled: ish1 -0.464, ish2 -0.539 A, istr 1.024 A")
    for p in (pv80(), bench(), bench(cc_channel=2)):
        print(f"\nG(3) {p.label}:  rows [vd1 vd2 ic1 ic2], cols [uc1 uc2 ud1 ud2]")
        print(fmt_matrix(dc_gain(p)))
        Gc, Ze = dc_gain_closed_form(p)
        print("  closed form agrees:", np.allclose(Gc, dc_gain(p), atol=1e-6), " cond(G) =", f"{np.linalg.cond(dc_gain(p)):.1f}",
              " modes:", [(f"{f:.0f} Hz", f"z {z:.2f}") for f, z, k in modes(p) if k == "oscillatory"][:4])
    print("\nranks (PV80):", ranks(pv80()))
    print("\ncond(G(N)) for the PV80 string, N = 2..8:", {n: round(c, 1) for n, c in cond_vs_N(lambda n: pv80(N=n)).items()})
    print("\nidentified G from the gain sets (G = diag(kI) M^-1):")
    for name, G in identified_G().items():
        print(" ", name)
        print(fmt_matrix(G) if not isinstance(G, str) else "   " + G)
    print("\nclosed-loop poles (PV80, model M = G^-1 diag(kI), slowest first) per kscale:")
    for k in (0.1, 0.3, 1.0):
        cl = ClosedLoop(pv80(), kscale=k)
        print(f"  kscale {k}: ", [(f"{f:.0f} Hz", f"z {z:.2f}") for f, z in cl.poles()[:6]])
    print("\ndesign numbers (pure integral):", {k: {n: f"tau {v['tau'] * 1e3:.2f} ms" for n, v in design_numbers(k).items()} for k in (0.1, 0.3, 1.0)})


if __name__ == "__main__":
    main()
