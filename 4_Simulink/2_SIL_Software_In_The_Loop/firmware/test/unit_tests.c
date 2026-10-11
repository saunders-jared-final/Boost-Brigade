/*
 * unit_tests.c - host sanity tests for the shuffler control stack port
 *
 * Generic over N_MOD (params.h). Two layers:
 *  1. Behavioural checks: reset semantics (en 0->1), duty clamps, supervisor
 *     hysteresis hold band, MPPT direction reversal, stack delay/decimation
 *     plumbing, module-current reconstruction identities.
 *  2. A DOUBLE-precision reference implementation transliterated from the
 *     MATLAB sources (own inv(M) via Gauss-Jordan), run side by side with the
 *     float32 port over a synthetic closed-loop-plausible profile. Bounds
 *     mirror the golden-vector gates.
 *
 * Host-only test code: stdio/double allowed here (core/ stays pure).
 */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "params.h"
#include "shuffler_ctrl.h"
#include "shuffler_mppt.h"
#include "shuffler_recon.h"
#include "shuffler_supervisor.h"
#include "stack.h"

/* ------------------------------------------------------------- harness --- */

static int g_checks = 0;
static int g_fails = 0;

static void check_impl(int ok, const char *expr, const char *fn, int line)
{
    g_checks++;
    if (!ok) {
        g_fails++;
        printf("FAIL %s:%d: %s\n", fn, line, expr);
    }
}

static void check_near_impl(double a, double b, double tol, const char *expr, const char *fn,
                            int line)
{
    g_checks++;
    if (!(fabs(a - b) <= tol)) {
        g_fails++;
        printf("FAIL %s:%d: %s: %.9g vs %.9g (tol %.3g)\n", fn, line, expr, a, b, tol);
    }
}

#define CHECK(cond) check_impl((cond) ? 1 : 0, #cond, __func__, __LINE__)
#define CHECK_NEAR(a, b, tol) \
    check_near_impl((double)(a), (double)(b), (double)(tol), #a " ~ " #b, __func__, __LINE__)

#define NM N_MOD
#define NS N_SHUF
#define NL N_LEG
#define NY N_Y
#define DEC STACK_DECIM

/* ---------------------------------------------- double reference: ctrl --- */

#define REF_PI 3.14159265358979323846

static const float REF_M_F[NY][NY] = CTRL_M_INIT;
static double REF_M[NY][NY];
static double REF_MP[NY][NY];
static double REF_MINV[NY][NY];
static int g_ref_mats_ready = 0;

/* invert an NYxNY via Gauss-Jordan with partial pivoting (double) */
static int invertN(double a_in[NY][NY], double out[NY][NY])
{
    double a[NY][2 * NY];
    int r, c, k;
    for (r = 0; r < NY; r++) {
        for (c = 0; c < NY; c++) {
            a[r][c] = a_in[r][c];
            a[r][c + NY] = (r == c) ? 1.0 : 0.0;
        }
    }
    for (c = 0; c < NY; c++) {
        int piv = c;
        for (r = c + 1; r < NY; r++) {
            if (fabs(a[r][c]) > fabs(a[piv][c])) {
                piv = r;
            }
        }
        if (fabs(a[piv][c]) < 1e-12) {
            return -1;
        }
        if (piv != c) {
            for (k = 0; k < 2 * NY; k++) {
                double t = a[c][k];
                a[c][k] = a[piv][k];
                a[piv][k] = t;
            }
        }
        for (r = 0; r < NY; r++) {
            if (r != c) {
                double f = a[r][c] / a[c][c];
                for (k = 0; k < 2 * NY; k++) {
                    a[r][k] -= f * a[c][k];
                }
            }
        }
    }
    for (r = 0; r < NY; r++) {
        for (c = 0; c < NY; c++) {
            out[r][c] = a[r][c + NY] / a[r][r];
        }
    }
    return 0;
}

static void ref_mats_init(void)
{
    int i, j;
    if (g_ref_mats_ready) {
        return;
    }
    for (i = 0; i < NY; i++) {
        for (j = 0; j < NY; j++) {
            double kp = (j < NS) ? 1.58e-4 : 1.08e-4;
            REF_M[i][j] = (double)REF_M_F[i][j];
            REF_MP[i][j] = REF_M[i][j] * kp;
        }
    }
    if (invertN(REF_M, REF_MINV) != 0) {
        printf("FATAL: reference inv(M) failed\n");
        g_fails++;
    }
    g_ref_mats_ready = 1;
}

typedef struct {
    double xi[NY];
    double y_f[NY];
} refctrl_t;

static void refctrl_init(refctrl_t *s)
{
    memset(s, 0, sizeof *s);
    ref_mats_init();
}

static double refclamp(double x, double lo, double hi)
{
    double y = (x > lo) ? x : lo;
    return (y < hi) ? y : hi;
}

static void refctrl_step(refctrl_t *s, const double VM[NM], const double IL[NL],
                         const double rv[NS], double d[NL])
{
    const double Ts = (double)CTRL_TS, DMIN = 0.05, DMAX = 0.95;
    const double a = 2.0 * REF_PI * 2000.0 * Ts / (1.0 + 2.0 * REF_PI * 2000.0 * Ts);
    double y[NY], e[NY], xi_try[NY], mpe[NY], u[NY], u_act[NY];
    int i, j;

    for (i = 0; i < NS; i++) {
        y[i] = VM[i] - VM[i + 1];
        y[NS + i] = IL[2 * i] + IL[2 * i + 1];
    }
    for (i = 0; i < NY; i++) {
        s->y_f[i] += a * (y[i] - s->y_f[i]);
    }
    for (i = 0; i < NS; i++) {
        e[i] = rv[i] - s->y_f[i];
        e[NS + i] = 0.0 - s->y_f[NS + i];
    }
    for (i = 0; i < NY; i++) {
        xi_try[i] = s->xi[i] + Ts * e[i];
    }
    for (i = 0; i < NY; i++) {
        double acc = 0.0;
        for (j = 0; j < NY; j++) {
            acc += REF_MP[i][j] * e[j];
        }
        mpe[i] = acc;
    }
    for (i = 0; i < NY; i++) {
        double acc = 0.0;
        for (j = 0; j < NY; j++) {
            acc += REF_M[i][j] * xi_try[j];
        }
        u[i] = mpe[i] + acc;
    }
    for (i = 0; i < NS; i++) {
        double uc = u[i], ud = u[NS + i];
        double dA = refclamp(0.5 + 0.5 * (uc + ud), DMIN, DMAX);
        double dB = refclamp(0.5 + 0.5 * (uc - ud), DMIN, DMAX);
        d[2 * i] = dA;
        d[2 * i + 1] = dB;
        u_act[i] = (dA + dB) - 1.0;
        u_act[NS + i] = dA - dB;
    }
    for (i = 0; i < NY; i++) {
        double acc = 0.0;
        for (j = 0; j < NY; j++) {
            acc += REF_MINV[i][j] * (u_act[j] - mpe[j]);
        }
        s->xi[i] = acc;
    }
}

/* ---------------------------------------- double reference: supervisor --- */

typedef struct {
    double b;
    double imf[NM];
    double idf[NS];
    int seeded;
} refsup_t;

static void refsup_init(refsup_t *s)
{
    memset(s, 0, sizeof *s);
}

static void refsup_step(refsup_t *s, const double IM[NM], const double IL[NL],
                        const double dd[NL], double en, double rv[NS], double *beta,
                        double *stress)
{
    const double Ts3 = 1e-3, TF = 5e-3, I_RATED = 10.0;
    const double S_HI = 0.90, S_LO = 0.70, KB = 60.0, KREL = 6.0, BMAX = 4.0, RVMAX = 30.0;
    double id[NS], dl[NM], imax, sid, sdu, st;
    int i;

    for (i = 0; i < NS; i++) {
        id[i] = IL[2 * i] - IL[2 * i + 1];
    }
    if (!s->seeded || en == 0.0) {
        s->b = 0.0;
        for (i = 0; i < NM; i++) {
            s->imf[i] = IM[i];
        }
        for (i = 0; i < NS; i++) {
            s->idf[i] = id[i];
        }
        s->seeded = 1;
    }
    if (en == 0.0) {
        for (i = 0; i < NS; i++) {
            rv[i] = 0.0;
        }
        *beta = 0.0;
        *stress = 0.0;
        return;
    }
    for (i = 0; i < NM; i++) {
        s->imf[i] += (Ts3 / TF) * (IM[i] - s->imf[i]);
    }
    imax = s->imf[0];
    for (i = 1; i < NM; i++) {
        imax = (s->imf[i] > imax) ? s->imf[i] : imax;
    }
    for (i = 0; i < NM; i++) {
        dl[i] = imax - s->imf[i];
    }
    for (i = 0; i < NS; i++) {
        s->idf[i] += (Ts3 / TF) * (id[i] - s->idf[i]);
    }
    sid = fabs(s->idf[0]);
    for (i = 1; i < NS; i++) {
        sid = (fabs(s->idf[i]) > sid) ? fabs(s->idf[i]) : sid;
    }
    sdu = fabs(dd[0] - 0.5);
    for (i = 1; i < NL; i++) {
        sdu = (fabs(dd[i] - 0.5) > sdu) ? fabs(dd[i] - 0.5) : sdu;
    }
    st = sid / I_RATED;
    if (sdu / 0.45 > st) {
        st = sdu / 0.45;
    }
    if (st > S_HI) {
        s->b += Ts3 * KB * (st - S_HI);
    } else if (st < S_LO) {
        s->b -= Ts3 * KREL * (S_LO - st);
    }
    s->b = refclamp(s->b, 0.0, BMAX);
    for (i = 0; i < NS; i++) {
        rv[i] = refclamp(s->b * (dl[i + 1] - dl[i]), -RVMAX, RVMAX);
    }
    *beta = s->b;
    *stress = st;
}

/* ---------------------------------------------- double reference: mppt --- */

typedef struct {
    double iref, dirn, Pprev, acc, b0;
    int n, boot, st, seeded;
} refmppt_t;

static void refmppt_init(refmppt_t *s)
{
    memset(s, 0, sizeof *s);
    s->iref = (double)MPPT_IREF0;
    s->dirn = 1.0;
    s->boot = 1;
}

static void refmppt_step(refmppt_t *s, double Vstr, double Istr, double beta, double en,
                         double *Iref, double *Pav, double *state)
{
    const double IREF0 = (double)MPPT_IREF0, IMIN = (double)MPPT_IMIN, IMAX = (double)MPPT_IMAX;
    const double DB = 1.0, KA = 0.01, SMIN = 0.05, SMAX = 1.0, S0 = 0.25, BTOL = 1e-3;
    const int N = MPPT_N;

    if (!s->seeded) {
        s->b0 = beta;
        s->seeded = 1;
    }
    if (en == 0.0) {
        s->iref = IREF0;
        s->dirn = 1.0;
        s->Pprev = 0.0;
        s->acc = 0.0;
        s->n = 0;
        s->boot = 1;
        s->b0 = beta;
        s->st = 0;
        *Iref = s->iref;
        *Pav = Vstr * Istr;
        *state = 0.0;
        return;
    }
    s->acc += Vstr * Istr;
    s->n++;
    if (s->n >= N) {
        double Pw = s->acc / (double)N;
        int govActive;
        s->acc = 0.0;
        s->n = 0;
        govActive = fabs(beta - s->b0) > BTOL;
        s->b0 = beta;
        if (govActive) {
            s->boot = 1;
            s->st = 0;
        } else if (s->boot) {
            s->Pprev = Pw;
            s->boot = 0;
            s->iref += s->dirn * S0;
            s->st = 1;
        } else {
            double dP = Pw - s->Pprev;
            if (dP > DB) {
                s->iref += s->dirn * refclamp(KA * fabs(dP), SMIN, SMAX);
                s->st = 1;
            } else if (dP < -DB) {
                s->dirn = -s->dirn;
                s->iref += s->dirn * refclamp(KA * fabs(dP), SMIN, SMAX);
                s->st = 1;
            } else {
                s->st = 2;
            }
            s->Pprev = Pw;
        }
        s->iref = refclamp(s->iref, IMIN, IMAX);
    }
    *Iref = s->iref;
    *Pav = s->Pprev;
    *state = (double)s->st;
}

/* --------------------------------------------- double reference: stack --- */

typedef struct {
    refctrl_t ctrl;
    refsup_t sup;
    refmppt_t mppt;
    int tick;
    double rv_dly[NS], iref_dly;
    double rv_out[NS], iref_out;
    double rv_now[NS], beta, stress, iref_raw, pav, mstate;
} refstack_t;

static void refstack_init(refstack_t *s)
{
    memset(s, 0, sizeof *s);
    refctrl_init(&s->ctrl);
    refsup_init(&s->sup);
    refmppt_init(&s->mppt);
    s->iref_dly = (double)MPPT_IREF0;
    s->iref_out = (double)MPPT_IREF0;
    s->iref_raw = (double)MPPT_IREF0;
}

typedef struct {
    double VM[NM], IM[NM], IL[NL], Vstr, Istr, Vref[NS], en_sup, en_mppt;
} refin_t;

typedef struct {
    double d[NL], rv[NS], beta, stress, iref, iref_dly, pav, mstate;
} refout_t;

static void refstack_step(refstack_t *s, const refin_t *in, refout_t *o)
{
    double rv_ctrl[NS], d[NL];
    int boundary = (s->tick == 0), i;

    if (boundary) {
        for (i = 0; i < NS; i++) {
            s->rv_out[i] = s->rv_dly[i];
        }
        s->iref_out = s->iref_dly;
    }
    for (i = 0; i < NS; i++) {
        rv_ctrl[i] = s->rv_out[i] + in->Vref[i];
    }
    refctrl_step(&s->ctrl, in->VM, in->IL, rv_ctrl, d);
    if (boundary) {
        double rv[NS], beta, stress, iref, pav, mstate;
        refsup_step(&s->sup, in->IM, in->IL, d, in->en_sup, rv, &beta, &stress);
        refmppt_step(&s->mppt, in->Vstr, in->Istr, beta, in->en_mppt, &iref, &pav, &mstate);
        for (i = 0; i < NS; i++) {
            s->rv_dly[i] = rv[i];
            s->rv_now[i] = rv[i];
        }
        s->iref_dly = iref;
        s->beta = beta;
        s->stress = stress;
        s->iref_raw = iref;
        s->pav = pav;
        s->mstate = mstate;
    }
    s->tick = (s->tick + 1) % DEC;
    for (i = 0; i < NL; i++) {
        o->d[i] = d[i];
    }
    for (i = 0; i < NS; i++) {
        o->rv[i] = s->rv_now[i];
    }
    o->beta = s->beta;
    o->stress = s->stress;
    o->iref = s->iref_raw;
    o->iref_dly = s->iref_out;
    o->pav = s->pav;
    o->mstate = s->mstate;
}

/* ------------------------------------------------------------- profile --- */

/* deterministic synthetic string profile in DOUBLE; the float stack sees the
 * float32 cast, exactly as the C Caller sees single-cast Simulink signals */
static void profile(long tick, refin_t *in)
{
    double t = (double)tick * (double)CTRL_TS;
    double g[NM];
    double gsh = (t > 1.10) ? 0.45 : 0.90; /* deep-shade step on module 3: governor engages */
    int k;
    for (k = 0; k < NM; k++) {
        g[k] = 1.0 - 0.02 * (double)k + 0.02 * sin(2.0 * REF_PI * (1.3 - 0.3 * k) * t + k);
    }
    g[2 % NM] = gsh;
    in->Vstr = 0.0;
    for (k = 0; k < NM; k++) {
        in->VM[k] = 38.7 * g[k];
        in->IM[k] = (14.0 - 0.3 * (double)k) * g[k];
        in->Vstr += in->VM[k];
    }
    for (k = 0; k < NL; k++) {
        in->IL[k] = 3.0 * sin(2.0 * REF_PI * 2.0 * t + 0.5 * (double)k) +
                    ((k % 2 == 0) ? 9.0 : -9.0) * (1.0 - gsh);
    }
    in->Istr = 11.0 + 0.5 * sin(2.0 * REF_PI * 0.9 * t);
    for (k = 0; k < NS; k++) {
        in->Vref[k] = 0.0;
    }
    in->Vref[0] = (t > 1.60) ? 0.8 : 0.0;
    in->en_sup = (t > 0.40 && t < 0.44) ? 0.0 : 1.0;
    in->en_mppt = (t > 0.70 && t < 0.72) ? 0.0 : 1.0;
}

static void in_to_float(const refin_t *r, stack_in_t *f)
{
    int k;
    for (k = 0; k < NM; k++) {
        f->VM[k] = (float)r->VM[k];
        f->IM[k] = (float)r->IM[k];
    }
    for (k = 0; k < NL; k++) {
        f->IL[k] = (float)r->IL[k];
    }
    f->Vstr = (float)r->Vstr;
    f->Istr = (float)r->Istr;
    for (k = 0; k < NS; k++) {
        f->Vref[k] = (float)r->Vref[k];
    }
    f->en_sup = (float)r->en_sup;
    f->en_mppt = (float)r->en_mppt;
}

/* --------------------------------------------------------------- tests --- */

static void test_ctrl_zero_inputs(void)
{
    ctrl_state_t s;
    ctrl_in_t in;
    ctrl_out_t out;
    int i;
    memset(&in, 0, sizeof in);
    ctrl_init(&s);
    ctrl_step(&in, &s, &out);
    for (i = 0; i < NL; i++) {
        CHECK(out.d[i] == 0.5f);
    }
}

static void test_ctrl_duty_clamps(void)
{
    ctrl_state_t s;
    ctrl_in_t in;
    ctrl_out_t out;
    int i;
    memset(&in, 0, sizeof in);
    in.rv[0] = 1000.0f; /* deep saturation; M(1,1) < 0 drives uc1 negative */
    ctrl_init(&s);
    ctrl_step(&in, &s, &out);
    CHECK(out.d[0] == CTRL_DMIN); /* dA1 */
    CHECK(out.d[1] == CTRL_DMIN); /* dB1 */
    for (i = 0; i < NL; i++) {
        CHECK(out.d[i] >= CTRL_DMIN && out.d[i] <= CTRL_DMAX);
    }
    in.rv[0] = -1000.0f;
    ctrl_init(&s);
    ctrl_step(&in, &s, &out);
    CHECK(out.d[0] == CTRL_DMAX);
    CHECK(out.d[1] == CTRL_DMAX);
}

static void test_ctrl_antiwindup_steady(void)
{
    /* constant error saturating ALL duties: the every-step Minv recompute
     * must pin xi to the same value each step (no windup ramp). */
    ctrl_state_t s;
    ctrl_in_t in;
    ctrl_out_t out;
    ctrl_accum_t xi1[NY];
    int i;
    memset(&in, 0, sizeof in);
    for (i = 0; i < NS; i++) {
        in.rv[i] = 1000.0f;
    }
    ctrl_init(&s);
    ctrl_step(&in, &s, &out);
    for (i = 0; i < NL; i++) {
        CHECK(out.d[i] == CTRL_DMIN || out.d[i] == CTRL_DMAX);
    }
    for (i = 0; i < NY; i++) {
        xi1[i] = s.xi[i];
    }
    ctrl_step(&in, &s, &out);
    ctrl_step(&in, &s, &out);
    for (i = 0; i < NY; i++) {
        CHECK(s.xi[i] == xi1[i]);
    }
}

static void test_ctrl_vs_double_ref(void)
{
    ctrl_state_t s;
    refctrl_t r;
    double maxerr = 0.0;
    long tick;
    const long NTICK = (long)(1.0 / (double)CTRL_TS); /* 1 s */
    ctrl_init(&s);
    refctrl_init(&r);
    for (tick = 0; tick < NTICK; tick++) {
        refin_t rin;
        ctrl_in_t fin;
        ctrl_out_t fout;
        double rv_ctrl[NS], rd[NL];
        int i;
        profile(tick, &rin);
        for (i = 0; i < NS; i++) {
            rv_ctrl[i] = 0.3 - 0.5 * (double)i; /* exercise every reference channel */
        }
        rv_ctrl[0] += rin.Vref[0];
        for (i = 0; i < NM; i++) {
            fin.VM[i] = (float)rin.VM[i];
        }
        for (i = 0; i < NL; i++) {
            fin.IL[i] = (float)rin.IL[i];
        }
        for (i = 0; i < NS; i++) {
            fin.rv[i] = (float)rv_ctrl[i];
        }
        ctrl_step(&fin, &s, &fout);
        refctrl_step(&r, rin.VM, rin.IL, rv_ctrl, rd);
        for (i = 0; i < NL; i++) {
            double e = fabs((double)fout.d[i] - rd[i]);
            maxerr = (e > maxerr) ? e : maxerr;
        }
    }
    printf("  ctrl float32 vs double ref, %ld ticks: max duty err %.3e\n", NTICK, maxerr);
    CHECK(maxerr < 1e-3); /* golden duty gate */
}

static void test_sup_seed_and_reset(void)
{
    sup_state_t s;
    sup_in_t in;
    sup_out_t out;
    int i;
    memset(&in, 0, sizeof in);
    for (i = 0; i < NM; i++) {
        in.IM[i] = 10.0f + (float)i;
    }
    for (i = 0; i < NL; i++) {
        in.d[i] = 0.5f;
    }
    in.en = 1.0f;
    sup_init(&s);
    sup_step(&in, &s, &out);
    for (i = 0; i < NM; i++) {
        CHECK(s.imf[i] == in.IM[i]); /* seeded then filtered toward itself */
    }
    in.en = 0.0f;
    in.IM[0] = 99.0f;
    sup_step(&in, &s, &out);
    for (i = 0; i < NS; i++) {
        CHECK(out.rv[i] == 0.0f);
    }
    CHECK(out.beta == 0.0f && out.stress == 0.0f);
    CHECK(s.b == 0.0f);
    CHECK(s.imf[0] == 99.0f);
    in.en = 1.0f;
    in.IM[0] = 89.0f;
    sup_step(&in, &s, &out);
    CHECK_NEAR(s.imf[0], 99.0f + 0.2f * (89.0f - 99.0f), 1e-5);
}

static void test_sup_hysteresis_and_bmax(void)
{
    sup_state_t s;
    sup_in_t in;
    sup_out_t out;
    float b_held;
    int i;
    memset(&in, 0, sizeof in);
    for (i = 0; i < NM; i++) {
        in.IM[i] = 10.0f; /* equal: dl = 0, rv = 0 */
    }
    in.en = 1.0f;
    sup_init(&s);
    for (i = 0; i < NL; i++) {
        in.d[i] = 0.95f; /* stress = 1.0 */
    }
    sup_step(&in, &s, &out);
    CHECK_NEAR(out.stress, 1.0, 1e-6);
    CHECK_NEAR(out.beta, 1e-3 * 60.0 * (1.0 - 0.9), 1e-6);
    sup_step(&in, &s, &out);
    CHECK_NEAR(out.beta, 2.0 * 1e-3 * 60.0 * (1.0 - 0.9), 1e-6);
    b_held = out.beta;
    for (i = 0; i < NL; i++) {
        in.d[i] = 0.86f; /* stress = 0.8: hold band */
    }
    sup_step(&in, &s, &out);
    CHECK_NEAR(out.stress, 0.8, 1e-6);
    CHECK(out.beta == b_held);
    sup_step(&in, &s, &out);
    CHECK(out.beta == b_held);
    for (i = 0; i < NL; i++) {
        in.d[i] = 0.5f; /* stress 0: release */
    }
    sup_step(&in, &s, &out);
    CHECK_NEAR(out.beta, b_held - 1e-3 * 6.0 * 0.7, 1e-6);
    for (i = 0; i < 100; i++) {
        sup_step(&in, &s, &out);
    }
    CHECK(out.beta == 0.0f);
    for (i = 0; i < NL; i++) {
        in.d[i] = 0.95f;
    }
    for (i = 0; i < 1000; i++) {
        sup_step(&in, &s, &out);
    }
    CHECK(out.beta == 4.0f);
}

static void test_sup_rv_clamp(void)
{
    sup_state_t s;
    sup_in_t in;
    sup_out_t out;
    int i;
    memset(&in, 0, sizeof in);
    in.en = 1.0f;
    in.IM[1] = 20.0f; /* dl = [20, 0, 20, ...]: dl(2)-dl(1) = -20, dl(3)-dl(2) = +20 */
    for (i = 0; i < NL; i++) {
        in.d[i] = 0.95f; /* stress 1.0: pump b to BMAX */
    }
    sup_init(&s);
    for (i = 0; i < 1000; i++) {
        sup_step(&in, &s, &out);
    }
    CHECK(out.beta == 4.0f);
    CHECK(out.rv[0] == -30.0f);
    CHECK(out.rv[1] == 30.0f);
    for (i = 2; i < NS; i++) {
        CHECK(out.rv[i] == 0.0f);
    }
}

static void test_sup_offset_invariance(void)
{
    /* the supervisor must give identical rv/beta/stress for IM and IM + c:
     * this is what lets the hardware feed RELATIVE reconstructed currents */
    sup_state_t sa, sb;
    sup_in_t ia, ib;
    sup_out_t oa, ob;
    int i, n;
    memset(&ia, 0, sizeof ia);
    ia.en = 1.0f;
    for (i = 0; i < NL; i++) {
        ia.d[i] = 0.5f + 0.4f * (float)(i % 2);
        ia.IL[i] = 2.0f * (float)i;
    }
    sup_init(&sa);
    sup_init(&sb);
    for (n = 0; n < 500; n++) {
        for (i = 0; i < NM; i++) {
            ia.IM[i] = 8.0f + 1.5f * (float)i + 0.5f * (float)(n % 7);
        }
        ib = ia;
        for (i = 0; i < NM; i++) {
            ib.IM[i] = ia.IM[i] - 64.0f; /* exact in float32 */
        }
        sup_step(&ia, &sa, &oa);
        sup_step(&ib, &sb, &ob);
        for (i = 0; i < NS; i++) {
            CHECK_NEAR(oa.rv[i], ob.rv[i], 1e-4);
        }
        CHECK(oa.beta == ob.beta);
        CHECK(oa.stress == ob.stress);
    }
}

static void test_recon_identities(void)
{
    float IL[NL], d[NL], IM[NM];
    int i;
    /* no shuffler current: every module carries the string current -> all equal */
    for (i = 0; i < NL; i++) {
        IL[i] = 0.0f;
        d[i] = 0.3f + 0.1f * (float)i;
    }
    recon_module_currents(IL, d, IM);
    for (i = 0; i < NM; i++) {
        CHECK(IM[i] == 0.0f);
    }
    /* reference module is always zero */
    for (i = 0; i < NL; i++) {
        IL[i] = 1.0f + 0.7f * (float)i;
    }
    recon_module_currents(IL, d, IM);
    CHECK(IM[NM - 1] == 0.0f);
    /* shuffler 1 only, d = 0.5 both legs, ic1 = 4 A into node 2: it takes 2 A
     * from node 1 (module 1 above) and 2 A from node 3; so I1 - I2 = -2 A... */
    for (i = 0; i < NL; i++) {
        IL[i] = 0.0f;
        d[i] = 0.5f;
    }
    IL[0] = 3.0f;
    IL[1] = 1.0f;
    recon_module_currents(IL, d, IM);
    /* I_2 = I_3 + ic_2(0) - ibot_1 = -2 ; I_1 = I_2 + ic_1 - itop_2(0) = -2 + 4 = 2 */
    CHECK_NEAR(IM[1], -2.0, 1e-6);
    CHECK_NEAR(IM[0], 2.0, 1e-6);
}

#if N_MOD == 3
static void test_recon_explicit_3mod(void)
{
    /* independent closed-form node equations for the 3-module board:
     *   I1 = Istr + itop1,  I2 = Istr + itop2 - ibot1,  I3 = Istr - ibot2 */
    int n, i;
    for (n = 0; n < 200; n++) {
        float IL[NL], d[NL], IM[NM];
        double il[NL], dd[NL], itop[NS], ibot[NS], I[NM], Istr = 7.0 + 0.1 * n;
        for (i = 0; i < NL; i++) {
            il[i] = 6.0 * sin(0.37 * n + 1.1 * i);
            dd[i] = 0.05 + 0.9 * (0.5 + 0.5 * sin(0.21 * n + 0.7 * i));
            IL[i] = (float)il[i];
            d[i] = (float)dd[i];
        }
        for (i = 0; i < NS; i++) {
            itop[i] = dd[2 * i] * il[2 * i] + dd[2 * i + 1] * il[2 * i + 1];
            ibot[i] = (1.0 - dd[2 * i]) * il[2 * i] + (1.0 - dd[2 * i + 1]) * il[2 * i + 1];
        }
        I[0] = Istr + itop[0];
        I[1] = Istr + itop[1] - ibot[0];
        I[2] = Istr - ibot[1];
        recon_module_currents(IL, d, IM);
        for (i = 0; i < NM; i++) {
            CHECK_NEAR(IM[i], I[i] - I[2], 1e-4);
        }
    }
}
#endif

static void test_mppt_boot_window_and_deadband(void)
{
    mppt_state_t s;
    mppt_in_t in;
    mppt_out_t out;
    int i;
    in.Vstr = 100.0f;
    in.Istr = 5.0f; /* P = 500 exactly */
    in.beta = 0.0f;
    in.en = 1.0f;
    mppt_init(&s);
    for (i = 0; i < MPPT_N - 1; i++) {
        mppt_step(&in, &s, &out);
        CHECK(out.Iref == MPPT_IREF0);
        CHECK(out.Pav == 0.0f);
        CHECK(out.state == 0.0f);
    }
    mppt_step(&in, &s, &out); /* window 1 boundary: boot perturb */
    CHECK(out.Iref == (MPPT_IREF0 + MPPT_S0));
    CHECK(out.Pav == 500.0f);
    CHECK(out.state == 1.0f);
    for (i = 0; i < MPPT_N - 1; i++) {
        mppt_step(&in, &s, &out);
        CHECK(out.Iref == (MPPT_IREF0 + MPPT_S0));
    }
    mppt_step(&in, &s, &out); /* window 2: dP = 0, deadband */
    CHECK(out.Iref == (MPPT_IREF0 + MPPT_S0));
    CHECK(out.state == 2.0f);
    CHECK(out.Pav == 500.0f);
}

static void test_mppt_adaptive_step_and_reversal(void)
{
    mppt_state_t s;
    mppt_in_t in;
    mppt_out_t out;
    float iref_after_boot;
    int i;
    in.Vstr = 100.0f;
    in.Istr = 5.0f;
    in.beta = 0.0f;
    in.en = 1.0f;
    mppt_init(&s);
    for (i = 0; i < MPPT_N; i++) {
        mppt_step(&in, &s, &out);
    }
    iref_after_boot = out.Iref;
    in.Istr = 5.2f; /* P = 520: dP = +20 -> step 0.2, dirn stays +1 */
    for (i = 0; i < MPPT_N; i++) {
        mppt_step(&in, &s, &out);
    }
    CHECK_NEAR(out.Iref, iref_after_boot + 0.2f, 1e-5);
    CHECK(out.state == 1.0f);
    in.Istr = 5.0f; /* P back to 500: dP = -20 -> reversal */
    for (i = 0; i < MPPT_N; i++) {
        mppt_step(&in, &s, &out);
    }
    CHECK_NEAR(out.Iref, iref_after_boot, 1e-5);
    CHECK(out.state == 1.0f);
    CHECK(s.dirn == -1.0f);
}

static void test_mppt_gov_active_hold(void)
{
    mppt_state_t s;
    mppt_in_t in;
    mppt_out_t out;
    float iref_held;
    int i;
    in.Vstr = 100.0f;
    in.Istr = 5.0f;
    in.beta = 0.0f;
    in.en = 1.0f;
    mppt_init(&s);
    for (i = 0; i < MPPT_N; i++) {
        mppt_step(&in, &s, &out);
    }
    iref_held = out.Iref;
    in.beta = 0.5f;
    for (i = 0; i < MPPT_N; i++) {
        mppt_step(&in, &s, &out);
    }
    CHECK(out.Iref == iref_held);
    CHECK(out.state == 0.0f);
    for (i = 0; i < MPPT_N; i++) {
        mppt_step(&in, &s, &out);
    }
    CHECK_NEAR(out.Iref, iref_held + 0.25f, 1e-6);
    CHECK(out.state == 1.0f);
}

static void test_mppt_en0_reset(void)
{
    mppt_state_t s;
    mppt_in_t in;
    mppt_out_t out;
    int i;
    in.Vstr = 100.0f;
    in.Istr = 5.0f;
    in.beta = 0.0f;
    in.en = 1.0f;
    mppt_init(&s);
    for (i = 0; i < MPPT_N + 10; i++) {
        mppt_step(&in, &s, &out);
    }
    CHECK(out.Iref == (MPPT_IREF0 + MPPT_S0));
    in.en = 0.0f;
    in.Vstr = 90.0f;
    mppt_step(&in, &s, &out);
    CHECK(out.Iref == MPPT_IREF0);
    CHECK(out.Pav == 90.0f * 5.0f);
    CHECK(out.state == 0.0f);
    in.en = 1.0f;
    in.Vstr = 100.0f;
    for (i = 0; i < MPPT_N - 1; i++) {
        mppt_step(&in, &s, &out);
        CHECK(out.Iref == MPPT_IREF0);
    }
    mppt_step(&in, &s, &out);
    CHECK(out.Iref == (MPPT_IREF0 + MPPT_S0));
    CHECK(out.state == 1.0f);
}

static void test_mppt_iref_clamps(void)
{
    mppt_state_t s;
    mppt_in_t in;
    mppt_out_t out;
    int w, i;
    in.Vstr = 100.0f;
    in.beta = 0.0f;
    in.en = 1.0f;
    mppt_init(&s);
    for (w = 0; w < 12; w++) {
        in.Istr = 5.0f + 2.0f * (float)w;
        for (i = 0; i < MPPT_N; i++) {
            mppt_step(&in, &s, &out);
        }
    }
    CHECK(out.Iref == MPPT_IMAX);
    in.Istr = 25.0f;
    for (i = 0; i < MPPT_N; i++) {
        mppt_step(&in, &s, &out);
    }
    CHECK(s.dirn == -1.0f);
    CHECK(out.Iref == (MPPT_IMAX - MPPT_SMAX));
    for (w = 0; w < 12; w++) {
        in.Istr = 26.0f + 1.0f * (float)w;
        for (i = 0; i < MPPT_N; i++) {
            mppt_step(&in, &s, &out);
        }
    }
    CHECK(out.Iref == MPPT_IMIN);
}

static void test_stack_delays_and_decimation(void)
{
    stack_state_t st;
    stack_in_t in;
    stack_out_t out;
    ctrl_state_t cs;
    long tick;
    const long T_BOOT = (long)(MPPT_N - 1) * DEC; /* MPPT call #MPPT_N lands here */
    const long T_DLY = (long)MPPT_N * DEC;        /* one slow frame later on the delayed output */
    int i;
    memset(&in, 0, sizeof in);
    for (i = 0; i < NM; i++) {
        in.VM[i] = 38.0f;
        in.IM[i] = MPPT_IREF0; /* equal modules: supervisor rv stays 0 */
    }
    in.Vstr = 38.0f * (float)NM;
    in.Istr = 11.0f;
    in.Vref[0] = 0.5f;
    in.en_sup = 1.0f;
    in.en_mppt = 1.0f;
    stack_init(&st);
    ctrl_init(&cs);
    for (tick = 0; tick < T_DLY + 3 * DEC; tick++) {
        ctrl_in_t ci;
        ctrl_out_t co;
        stack_step(&in, &st, &out);
        for (i = 0; i < NM; i++) {
            ci.VM[i] = in.VM[i];
        }
        for (i = 0; i < NL; i++) {
            ci.IL[i] = in.IL[i];
        }
        for (i = 0; i < NS; i++) {
            ci.rv[i] = 0.0f;
        }
        ci.rv[0] = 0.5f;
        ctrl_step(&ci, &cs, &co);
        for (i = 0; i < NL; i++) {
            CHECK(out.d[i] == co.d[i]);
        }
        CHECK(out.Iref_dly == ((tick < T_DLY) ? MPPT_IREF0 : (MPPT_IREF0 + MPPT_S0)));
        CHECK(out.Iref == ((tick < T_BOOT) ? MPPT_IREF0 : (MPPT_IREF0 + MPPT_S0)));
        if (tick >= T_BOOT && tick < T_DLY) {
            CHECK(out.mppt_state == 1.0f);
        }
        if (tick < T_BOOT) {
            CHECK(out.mppt_state == 0.0f);
        }
    }
}

static void test_stack_en_reaches_modules(void)
{
    stack_state_t st;
    stack_in_t in;
    stack_out_t out;
    int i;
    long tick;
    memset(&in, 0, sizeof in);
    for (i = 0; i < NM; i++) {
        in.VM[i] = 38.0f;
        in.IM[i] = 10.0f + 2.0f * (float)i;
    }
    in.Vstr = 38.0f * (float)NM;
    in.Istr = 11.0f;
    in.en_sup = 0.0f;
    in.en_mppt = 0.0f;
    stack_init(&st);
    for (tick = 0; tick < 5 * DEC; tick++) {
        stack_step(&in, &st, &out);
        CHECK(out.beta == 0.0f && out.stress == 0.0f);
        for (i = 0; i < NS; i++) {
            CHECK(out.rv[i] == 0.0f);
        }
        CHECK(out.Iref == MPPT_IREF0);
        CHECK(out.mppt_state == 0.0f);
    }
}

static void test_stack_vs_double_ref(void)
{
    stack_state_t fs;
    refstack_t rs;
    double emax_d = 0.0, emax_rv = 0.0, emax_beta = 0.0, emax_iref = 0.0;
    long state_mismatch = 0, tick;
    const long NTICK = (long)(2.0 / (double)CTRL_TS); /* 2 s */
    stack_init(&fs);
    refstack_init(&rs);
    for (tick = 0; tick < NTICK; tick++) {
        refin_t rin;
        refout_t ro;
        stack_in_t fin;
        stack_out_t fo;
        int i;
        double e;
        profile(tick, &rin);
        in_to_float(&rin, &fin);
        stack_step(&fin, &fs, &fo);
        refstack_step(&rs, &rin, &ro);
        for (i = 0; i < NL; i++) {
            e = fabs((double)fo.d[i] - ro.d[i]);
            emax_d = (e > emax_d) ? e : emax_d;
        }
        for (i = 0; i < NS; i++) {
            e = fabs((double)fo.rv[i] - ro.rv[i]);
            emax_rv = (e > emax_rv) ? e : emax_rv;
        }
        e = fabs((double)fo.beta - ro.beta);
        emax_beta = (e > emax_beta) ? e : emax_beta;
        e = fabs((double)fo.Iref - ro.iref);
        emax_iref = (e > emax_iref) ? e : emax_iref;
        if ((double)fo.mppt_state != ro.mstate) {
            state_mismatch++;
        }
    }
    printf("  stack float32 vs double ref, %ld ticks (%.1f s):\n", NTICK,
           (double)NTICK * (double)CTRL_TS);
    printf("    max err  duty %.3e  rv %.3e  beta %.3e  Iref %.3e  state mismatches %ld\n",
           emax_d, emax_rv, emax_beta, emax_iref, state_mismatch);
    CHECK(emax_d < 1e-3);
    CHECK(emax_rv < 1e-2);
    CHECK(emax_beta < 1e-2);
    CHECK(emax_iref < 1e-2);
    CHECK(state_mismatch == 0);
}

int main(void)
{
    printf("shuffler stack unit tests, %s, N_MOD=%d, Ts=%g, accum=%s\n", PARAMS_VERSION, NM,
           (double)CTRL_TS,
#ifdef SHUF_ACCUM_DOUBLE
           "double"
#else
           "float"
#endif
    );
    test_ctrl_zero_inputs();
    test_ctrl_duty_clamps();
    test_ctrl_antiwindup_steady();
    test_ctrl_vs_double_ref();
    test_sup_seed_and_reset();
    test_sup_hysteresis_and_bmax();
    test_sup_rv_clamp();
    test_sup_offset_invariance();
    test_recon_identities();
#if N_MOD == 3
    test_recon_explicit_3mod();
#endif
    test_mppt_boot_window_and_deadband();
    test_mppt_adaptive_step_and_reversal();
    test_mppt_gov_active_hold();
    test_mppt_en0_reset();
    test_mppt_iref_clamps();
    test_stack_delays_and_decimation();
    test_stack_en_reaches_modules();
    test_stack_vs_double_ref();
    printf("%d checks, %d failures\n", g_checks, g_fails);
    return (g_fails == 0) ? 0 : 1;
}
