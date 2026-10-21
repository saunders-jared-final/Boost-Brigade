"""nstring_derive.py - the symbolic derivation behind nstring.py, with sympy, for the notebook:

  1. one shuffler: the four dual-switch states of the two half bridges, KVL of the coupled windings, KCL at the
     three nodes it touches -> dwell-weighted (state-space) average -> bilinear averaged model;
  2. the sum / difference (shuffled / circulating) transform of the winding equations;
  3. the module ladder of N modules: nodal KCL with the shuffler injections -> the N-module averaged model;
  4. equilibrium: volt-second balance (duty = voltage ratio) and charge balance (the tridiagonal T i_m = Delta I);
  5. the 2026 four-state model (shuffler_statespace.ipynb) recovered from the same equations at N = 2.

Everything here is symbolic; nstring.py is the numeric twin and the notebook checks the two against each other.
"""
import sympy as sp

# ----------------------------------------------------------------------------- symbols
L, M, R = sp.symbols("L M R", positive=True)                 # self, mutual inductance, winding-path resistance
dA, dB = sp.symbols("d_A d_B", real=True)
uc, ud = sp.symbols("u_c u_d", real=True)
iA, iB = sp.symbols("i_A i_B", real=True)
im, ic = sp.symbols("i_m i_c", real=True)
phiT, phiM, phiB = sp.symbols("phi_T phi_M phi_B", real=True)
vj, vj1 = sp.symbols("v_j v_{j+1}", real=True)               # module voltages above and below the midpoint
Vbar = sp.symbols(r"\bar V", positive=True)
Vf = sp.symbols("V_f", positive=True)                        # body-diode drop (dead-time states only)

Lmat = sp.Matrix([[L, -M], [-M, L]])                         # as built: magnetising current = i_A - i_B  (QSPICE ERUC23 subckt, turns 1:-1)


def pole_voltage(s, i=None):
    """Average pole potential for switch state s in {1: high side on, 0: low side on, 'dead': both off}.
    In a dead time the winding current picks the body diode: i > 0 (into the midpoint) -> low-side diode -> phi_B - V_f,
    i < 0 -> high-side diode -> phi_T + V_f."""
    if s == 1:
        return phiT
    if s == 0:
        return phiB
    return sp.Piecewise((phiB - Vf, i > 0), (phiT + Vf, True))


def switch_state(sA, sB):
    """Circuit equations of one shuffler in the dual-switch state (sA, sB):
    winding KVL  Lmat d/dt [i_A, i_B] = [v_poleA - phi_M - R i_A, v_poleB - phi_M - R i_B]
    node KCL     current drawn from T, injected at M, drawn from B (all by the shuffler)."""
    vA, vB = pole_voltage(sA), pole_voltage(sB)
    rhs = sp.Matrix([vA - phiM - R * iA, vB - phiM - R * iB])
    di = Lmat.inv() * rhs
    iT = (iA if sA == 1 else 0) + (iB if sB == 1 else 0)     # current leaving node T into the legs whose high side is on
    iB_ = (iA if sA == 0 else 0) + (iB if sB == 0 else 0)    # current leaving node B into the legs whose low side is on
    return dict(di=sp.simplify(di), i_from_T=iT, i_into_M=iA + iB, i_from_B=iB_)


def dwell():
    """Dwell fractions of the four dual-switch states for independent (interleaved) carriers."""
    return {(1, 1): dA * dB, (1, 0): dA * (1 - dB), (0, 1): (1 - dA) * dB, (0, 0): (1 - dA) * (1 - dB)}


def averaged():
    """Dwell-weighted average of the four states: the bilinear averaged model of one shuffler."""
    w = dwell()
    di = sp.zeros(2, 1)
    iT = iM = iB_ = 0
    for s, f in w.items():
        st = switch_state(*s)
        di += f * st["di"]
        iT += f * st["i_from_T"]
        iM += f * st["i_into_M"]
        iB_ += f * st["i_from_B"]
    return dict(di=sp.simplify(di), i_from_T=sp.expand(iT), i_into_M=sp.expand(iM), i_from_B=sp.expand(iB_))


def modal():
    """Sum and difference of the averaged winding equations with the pole voltages written as
    v_pole = phi_B + d Vbar (Vbar = phi_T - phi_B = v_j + v_{j+1}) and phi_M - phi_B = v_{j+1}."""
    av = averaged()
    sub = {phiT: phiB + vj + vj1, phiM: phiB + vj1}
    LdI = sp.simplify((Lmat * av["di"]).subs(sub))           # = [v_A - phi_M - R i_A, v_B - phi_M - R i_B] averaged
    eq_sum = sp.simplify(LdI[0] + LdI[1])                    # (L - M) d i_m/dt
    eq_dif = sp.simplify(LdI[0] - LdI[1])                    # (L + M) d i_c/dt
    msub = {dA: (1 + uc + ud) / 2, dB: (1 + uc - ud) / 2, iA: (im + ic) / 2, iB: (im - ic) / 2}
    eq_sum = sp.expand(eq_sum.subs(msub))
    eq_dif = sp.expand(eq_dif.subs(msub))
    rails = {k: sp.expand(av[k].subs(msub)) for k in ("i_from_T", "i_into_M", "i_from_B")}
    return dict(L_sum=L - M, L_dif=L + M, rhs_sum=eq_sum, rhs_dif=eq_dif, rails=rails)


# ----------------------------------------------------------------------------- the N-module ladder
def string_model(N, equal_g=True):
    """Symbolic averaged small-signal model of the N-module string. Returns dict with the state vector,
    A, B (inputs u_c_j, u_d_j), the DC gain G(N) and the symbols used."""
    NS = N - 1
    g = sp.symbols(f"g_1:{N + 1}", positive=True) if not equal_g else [sp.symbols("g", positive=True)] * N
    C = sp.symbols(f"C_1:{N + 1}", positive=True)
    Vb = sp.symbols(f"Vbar_1:{NS + 1}", positive=True)
    Lm, Lc, Rm, Rc, GL = sp.symbols("L_m L_c R_m R_c G_L", positive=True)
    phi = sp.Matrix(sp.symbols(f"phi_1:{N + 1}", real=True))
    imv = sp.Matrix(sp.symbols(f"i_m1:{NS + 1}", real=True))
    icv = sp.Matrix(sp.symbols(f"i_c1:{NS + 1}", real=True))
    ucv = sp.Matrix(sp.symbols(f"u_c1:{NS + 1}", real=True))
    udv = sp.Matrix(sp.symbols(f"u_d1:{NS + 1}", real=True))
    Cn, Gn = sp.zeros(N, N), sp.zeros(N, N)
    for k in range(N):
        for (i, j, s) in ((k, k, 1), (k + 1, k + 1, 1), (k, k + 1, -1), (k + 1, k, -1)):
            if i < N and j < N:
                Cn[i, j] += s * C[k]
                Gn[i, j] += s * g[k]
    Gn[0, 0] += GL
    S = sp.zeros(N, NS)
    for j in range(NS):
        S[j + 1, j] += 1
        S[j, j] -= sp.Rational(1, 2)
        if j + 2 < N:
            S[j + 2, j] -= sp.Rational(1, 2)
    Dv = sp.zeros(NS, N)
    for j in range(NS):
        Dv[j, j] += 1
        Dv[j, j + 1] -= 2
        if j + 2 < N:
            Dv[j, j + 2] += 1
    vd = Dv * phi
    f_phi = Cn.inv() * (-Gn * phi + S * imv)
    f_im = sp.Matrix([(Vb[j] * ucv[j] + vd[j] - Rm * imv[j]) / Lm for j in range(NS)])
    f_ic = sp.Matrix([(Vb[j] * udv[j] - Rc * icv[j]) / Lc for j in range(NS)])
    x = sp.Matrix.vstack(phi, imv, icv)
    u = sp.Matrix.vstack(ucv, udv)
    f = sp.Matrix.vstack(f_phi, f_im, f_ic)
    A, B = f.jacobian(x), f.jacobian(u)
    Cy = sp.Matrix.vstack(Dv.row_join(sp.zeros(NS, 2 * NS)), sp.zeros(NS, N + NS).row_join(sp.eye(NS)))
    G = sp.simplify(-Cy * A.inv() * B)
    return dict(x=x, u=u, A=A, B=B, C=Cy, G=G, Cn=Cn, Gn=Gn, S=S, Dv=Dv, syms=dict(g=g, C=C, Vb=Vb, Lm=Lm, Lc=Lc, Rm=Rm, Rc=Rc, GL=GL))


def equilibrium_symbolic(N):
    """Charge balance at the interior nodes with equal duties 1/2: T i_m = Delta I, and its closed-form inverse."""
    NS = N - 1
    I = sp.symbols(f"I_1:{N + 1}", real=True)
    imv = sp.Matrix(sp.symbols(f"i_m1:{NS + 1}", real=True))
    T = sp.eye(NS)
    for j in range(NS - 1):
        T[j, j + 1] = T[j + 1, j] = -sp.Rational(1, 2)
    dI = sp.Matrix([I[j] - I[j + 1] for j in range(NS)])
    sol = T.inv() * dI
    D = sp.symbols(f"D_1:{NS + 1}", positive=True)
    Istr = I[0] - sp.Rational(1, 2) * sol[0]
    return dict(T=T, dI=dI, i_m=sp.simplify(sol), I_str=sp.simplify(Istr), I=I)


def original_2026_model():
    """The 2026 four-state model (shuffler_statespace.ipynb): x = [I_L1, I_L2, V_C1, V_C2], both inductor currents
    defined from the midpoint towards the switch node, independent inductors, no pinning. Returned as the
    nonlinear averaged f(x, d) so the notebook can show it is the N = 2 case of switch_state()/averaged()
    with i_A = -I_L1, i_B = -I_L2, phi_T - phi_M = V_C1, phi_M - phi_B = V_C2."""
    IL1, IL2, VC1, VC2 = sp.symbols("I_L1 I_L2 V_C1 V_C2", real=True)
    C1, C2 = sp.symbols("C_1 C_2", positive=True)
    Ipv1, Ipv2, Iload = sp.symbols("I_pv1 I_pv2 I_load", real=True)
    vL = sp.Matrix([-dA * VC1 + (1 - dA) * VC2, -dB * VC1 + (1 - dB) * VC2])
    dI = vL / L
    dVC1 = (dA * IL1 + dB * IL2 + Ipv1 - Iload) / C1
    dVC2 = (Ipv2 - (1 - dA) * IL1 - (1 - dB) * IL2) / C2
    return dict(x=sp.Matrix([IL1, IL2, VC1, VC2]), f=sp.Matrix([dI[0], dI[1], dVC1, dVC2]), syms=(IL1, IL2, VC1, VC2, C1, C2, Ipv1, Ipv2, Iload))


if __name__ == "__main__":
    sp.init_printing()
    m = modal()
    print("(L - M) d i_m/dt =", m["rhs_sum"])
    print("(L + M) d i_c/dt =", m["rhs_dif"])
    print("rail currents:", m["rails"])
    e = equilibrium_symbolic(3)
    print("T(3) =", e["T"], " i_m =", e["i_m"].T, " I_str =", e["I_str"])
    s2 = string_model(2)
    print("G(2) =", s2["G"])
