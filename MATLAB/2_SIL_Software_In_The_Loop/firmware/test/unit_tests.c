/*
 * unit_tests.c - host sanity tests for the shuffler control stack port
 *
 * Two layers:
 *  1. Behavioural checks straight from the acceptance list: reset semantics
 *     (en 0->1), duty clamps at 0.05/0.95, supervisor hysteresis hold band,
 *     MPPT direction reversal, stack delay/decimation plumbing.
 *  2. A DOUBLE-precision reference implementation transliterated directly
 *     from the MATLAB sources (its own inv(M) via Gauss-Jordan - independent
 *     of params.h), run side by side with the float32 port over a synthetic
 *     closed-loop-plausible profile. Bounds mirror the golden-vector gates
 *     and stand in for them until MATLAB goldens exist; the printed maxima
 *     are the design-rule-6 (float32 integrator) drift evidence.
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

/* ---------------------------------------------- double reference: ctrl --- */

/* same double as MATLAB's pi (M_PI is not C99, extensions are off) */
#define REF_PI 3.14159265358979323846

static const double REF_M[6][6] = {
    {-12.798383, 0.000000, -0.000000, -0.000000, 1.043947, 0.000000},
    {-0.132666, -12.627108, 0.000000, -1.014057, 1.021695, 1.025829},
    {-0.130486, -0.200085, -12.492219, -1.001002, 0.000612, 1.002715},
    {0.000000, 0.000000, 0.000000, -1.945483, 0.000000, 0.000000},
    {-0.000000, -0.000000, -0.000000, -0.000000, -2.061583, -0.000000},
    {-0.000000, -0.000000, -0.000000, -0.000000, 0.000000, -2.022595}};
static const double REF_KP[6] = {1.58e-4, 1.58e-4, 1.58e-4, 1.08e-4, 1.08e-4, 1.08e-4};

static double REF_MP[6][6];
static double REF_MINV[6][6];
static int g_ref_mats_ready = 0;

/* invert a 6x6 via Gauss-Jordan with partial pivoting (double) */
static int invert6(const double a_in[6][6], double out[6][6])
{
    double a[6][12];
    int r, c, k;
    for (r = 0; r < 6; r++) {
        for (c = 0; c < 6; c++) {
            a[r][c] = a_in[r][c];
            a[r][c + 6] = (r == c) ? 1.0 : 0.0;
        }
    }
    for (c = 0; c < 6; c++) {
        int piv = c;
        for (r = c + 1; r < 6; r++) {
            if (fabs(a[r][c]) > fabs(a[piv][c])) {
                piv = r;
            }
        }
        if (fabs(a[piv][c]) < 1e-12) {
            return -1;
        }
        if (piv != c) {
            for (k = 0; k < 12; k++) {
                double t = a[c][k];
                a[c][k] = a[piv][k];
                a[piv][k] = t;
            }
        }
        for (r = 0; r < 6; r++) {
            if (r != c) {
                double f = a[r][c] / a[c][c];
                for (k = 0; k < 12; k++) {
                    a[r][k] -= f * a[c][k];
                }
            }
        }
    }
    for (r = 0; r < 6; r++) {
        for (c = 0; c < 6; c++) {
            out[r][c] = a[r][c + 6] / a[r][r];
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
    for (i = 0; i < 6; i++) {
        for (j = 0; j < 6; j++) {
            REF_MP[i][j] = REF_M[i][j] * REF_KP[j];
        }
    }
    if (invert6(REF_M, REF_MINV) != 0) {
        printf("FATAL: reference inv(M) failed\n");
        g_fails++;
    }
    g_ref_mats_ready = 1;
}

typedef struct {
    double xi[6];
    double y_f[6];
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

static void refctrl_step(refctrl_t *s, const double VM[4], const double IL[6],
                         const double rv[3], double d[6])
{
    const double Ts = 50e-6, DMIN = 0.05, DMAX = 0.95;
    const double a = 2.0 * REF_PI * 2000.0 * Ts / (1.0 + 2.0 * REF_PI * 2000.0 * Ts);
    double y[6], e[6], xi_try[6], mpe[6], u[6], u_act[6], dAs[3], dBs[3];
    int i, j;

    y[0] = VM[0] - VM[1];
    y[1] = VM[1] - VM[2];
    y[2] = VM[2] - VM[3];
    y[3] = IL[0] + IL[1];
    y[4] = IL[2] + IL[3];
    y[5] = IL[4] + IL[5];
    for (i = 0; i < 6; i++) {
        s->y_f[i] += a * (y[i] - s->y_f[i]);
    }
    for (i = 0; i < 3; i++) {
        e[i] = rv[i] - s->y_f[i];
        e[i + 3] = 0.0 - s->y_f[i + 3];
    }
    for (i = 0; i < 6; i++) {
        xi_try[i] = s->xi[i] + Ts * e[i];
    }
    for (i = 0; i < 6; i++) {
        double acc = 0.0;
        for (j = 0; j < 6; j++) {
            acc += REF_MP[i][j] * e[j];
        }
        mpe[i] = acc;
    }
    for (i = 0; i < 6; i++) {
        double acc = 0.0;
        for (j = 0; j < 6; j++) {
            acc += REF_M[i][j] * xi_try[j];
        }
        u[i] = mpe[i] + acc;
    }
    for (i = 0; i < 3; i++) {
        double uc = u[i], ud = u[i + 3];
        dAs[i] = refclamp(0.5 + 0.5 * (uc + ud), DMIN, DMAX);
        dBs[i] = refclamp(0.5 + 0.5 * (uc - ud), DMIN, DMAX);
        u_act[i] = (dAs[i] + dBs[i]) - 1.0;
        u_act[i + 3] = dAs[i] - dBs[i];
    }
    for (i = 0; i < 6; i++) {
        double acc = 0.0;
        for (j = 0; j < 6; j++) {
            acc += REF_MINV[i][j] * (u_act[j] - mpe[j]);
        }
        s->xi[i] = acc;
    }
    d[0] = dAs[0];
    d[1] = dBs[0];
    d[2] = dAs[1];
    d[3] = dBs[1];
    d[4] = dAs[2];
    d[5] = dBs[2];
}

/* ---------------------------------------- double reference: supervisor --- */

typedef struct {
    double b;
    double imf[4];
    double idf[3];
    int seeded;
} refsup_t;

static void refsup_init(refsup_t *s)
{
    memset(s, 0, sizeof *s);
}

static void refsup_step(refsup_t *s, const double IM[4], const double IL[6], const double d6[6],
                        double en, double rv[3], double *beta, double *stress)
{
    const double Ts3 = 1e-3, TF = 5e-3, I_RATED = 10.0;
    const double S_HI = 0.90, S_LO = 0.70, KB = 60.0, KREL = 6.0, BMAX = 4.0, RVMAX = 30.0;
    double id[3], dl[4], imax, sid, sdu, st;
    int i;

    id[0] = IL[0] - IL[1];
    id[1] = IL[2] - IL[3];
    id[2] = IL[4] - IL[5];
    if (!s->seeded) {
        s->b = 0.0;
        for (i = 0; i < 4; i++) {
            s->imf[i] = IM[i];
        }
        for (i = 0; i < 3; i++) {
            s->idf[i] = id[i];
        }
        s->seeded = 1;
    }
    if (en == 0.0) {
        s->b = 0.0;
        for (i = 0; i < 4; i++) {
            s->imf[i] = IM[i];
        }
        for (i = 0; i < 3; i++) {
            s->idf[i] = id[i];
        }
        rv[0] = rv[1] = rv[2] = 0.0;
        *beta = 0.0;
        *stress = 0.0;
        return;
    }
    for (i = 0; i < 4; i++) {
        s->imf[i] += (Ts3 / TF) * (IM[i] - s->imf[i]);
    }
    imax = s->imf[0];
    for (i = 1; i < 4; i++) {
        imax = (s->imf[i] > imax) ? s->imf[i] : imax;
    }
    for (i = 0; i < 4; i++) {
        dl[i] = imax - s->imf[i];
    }
    for (i = 0; i < 3; i++) {
        s->idf[i] += (Ts3 / TF) * (id[i] - s->idf[i]);
    }
    sid = fabs(s->idf[0]);
    for (i = 1; i < 3; i++) {
        sid = (fabs(s->idf[i]) > sid) ? fabs(s->idf[i]) : sid;
    }
    sdu = fabs(d6[0] - 0.5);
    for (i = 1; i < 6; i++) {
        sdu = (fabs(d6[i] - 0.5) > sdu) ? fabs(d6[i] - 0.5) : sdu;
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
    for (i = 0; i < 3; i++) {
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
    s->iref = 12.0;
    s->dirn = 1.0;
    s->boot = 1;
}

static void refmppt_step(refmppt_t *s, double Vstr, double Istr, double beta, double en,
                         double *Iref, double *Pav, double *state)
{
    const double IREF0 = 12.0, IMIN = 5.0, IMAX = 14.5;
    const double DB = 1.0, KA = 0.01, SMIN = 0.05, SMAX = 1.0, S0 = 0.25, BTOL = 1e-3;
    const int N = 20;

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
    double rv_dly[3], iref_dly;
    double rv_out[3], iref_out;
    double rv_now[3], beta, stress, iref_raw, pav, mstate;
} refstack_t;

static void refstack_init(refstack_t *s)
{
    memset(s, 0, sizeof *s);
    refctrl_init(&s->ctrl);
    refsup_init(&s->sup);
    refmppt_init(&s->mppt);
    s->iref_dly = 12.0;
    s->iref_out = 12.0;
    s->iref_raw = 12.0;
}

typedef struct {
    double VM[4], IM[4], IL[6], Vstr, Istr, Vref[3], en_sup, en_mppt;
} refin_t;

typedef struct {
    double d[6], rv[3], beta, stress, iref, iref_dly, pav, mstate;
} refout_t;

static void refstack_step(refstack_t *s, const refin_t *in, refout_t *o)
{
    double rv_ctrl[3], d[6];
    int boundary = (s->tick == 0), i;

    if (boundary) {
        for (i = 0; i < 3; i++) {
            s->rv_out[i] = s->rv_dly[i];
        }
        s->iref_out = s->iref_dly;
    }
    for (i = 0; i < 3; i++) {
        rv_ctrl[i] = s->rv_out[i] + in->Vref[i];
    }
    refctrl_step(&s->ctrl, in->VM, in->IL, rv_ctrl, d);
    if (boundary) {
        double rv[3], beta, stress, iref, pav, mstate;
        refsup_step(&s->sup, in->IM, in->IL, d, in->en_sup, rv, &beta, &stress);
        refmppt_step(&s->mppt, in->Vstr, in->Istr, beta, in->en_mppt, &iref, &pav, &mstate);
        for (i = 0; i < 3; i++) {
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
    s->tick = (s->tick + 1) % 20;
    for (i = 0; i < 6; i++) {
        o->d[i] = d[i];
    }
    for (i = 0; i < 3; i++) {
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

/* deterministic synthetic string profile in DOUBLE (the float stack sees the
 * float32 cast, exactly as the C Caller sees single-cast Simulink signals) */
static void profile(long tick, refin_t *in)
{
    double t = (double)tick * 50e-6;
    double g1 = 1.00 + 0.02 * sin(2.0 * REF_PI * 1.3 * t);
    double g2 = 0.95 + 0.03 * sin(2.0 * REF_PI * 0.7 * t + 1.0);
    double g3 = (t > 1.10) ? 0.45 : 0.90; /* deep-shade step: governor engages */
    double g4 = 1.00;
    int k;
    in->VM[0] = 38.7 * g1;
    in->VM[1] = 38.7 * g2;
    in->VM[2] = 38.7 * g3;
    in->VM[3] = 38.7 * g4;
    in->IM[0] = 14.0 * g1;
    in->IM[1] = 13.5 * g2;
    in->IM[2] = 13.0 * g3;
    in->IM[3] = 14.2 * g4;
    for (k = 0; k < 6; k++) {
        in->IL[k] = 3.0 * sin(2.0 * REF_PI * 2.0 * t + 0.5 * (double)k) +
                    ((k % 2 == 0) ? 9.0 : -9.0) * (1.0 - g3);
    }
    in->Vstr = in->VM[0] + in->VM[1] + in->VM[2] + in->VM[3];
    in->Istr = 11.0 + 0.5 * sin(2.0 * REF_PI * 0.9 * t);
    in->Vref[0] = (t > 1.60) ? 0.8 : 0.0;
    in->Vref[1] = 0.0;
    in->Vref[2] = 0.0;
    in->en_sup = (t > 0.40 && t < 0.44) ? 0.0 : 1.0;
    in->en_mppt = (t > 0.70 && t < 0.72) ? 0.0 : 1.0;
}

static void in_to_float(const refin_t *r, stack_in_t *f)
{
    int k;
    for (k = 0; k < 4; k++) {
        f->VM[k] = (float)r->VM[k];
        f->IM[k] = (float)r->IM[k];
    }
    for (k = 0; k < 6; k++) {
        f->IL[k] = (float)r->IL[k];
    }
    f->Vstr = (float)r->Vstr;
    f->Istr = (float)r->Istr;
    for (k = 0; k < 3; k++) {
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
    for (i = 0; i < 6; i++) {
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
    in.rv[0] = 1000.0f; /* deep saturation */
    ctrl_init(&s);
    ctrl_step(&in, &s, &out);
    CHECK(out.d[0] == CTRL_DMIN); /* dA1: uc1 strongly negative */
    CHECK(out.d[1] == CTRL_DMIN); /* dB1 */
    for (i = 0; i < 6; i++) {
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
    /* constant error saturating ALL SIX duties: the every-step Minv recompute
     * must pin xi to the same value each step (no windup ramp). With partial
     * saturation the unsaturated channels legitimately keep integrating, so
     * all three rv channels are driven here. */
    ctrl_state_t s;
    ctrl_in_t in;
    ctrl_out_t out;
    ctrl_accum_t xi1[6];
    int i;
    memset(&in, 0, sizeof in);
    in.rv[0] = 1000.0f;
    in.rv[1] = 1000.0f;
    in.rv[2] = 1000.0f;
    ctrl_init(&s);
    ctrl_step(&in, &s, &out);
    for (i = 0; i < 6; i++) {
        xi1[i] = s.xi[i];
    }
    ctrl_step(&in, &s, &out);
    ctrl_step(&in, &s, &out);
    for (i = 0; i < 6; i++) {
        CHECK(s.xi[i] == xi1[i]);
    }
}

static void test_ctrl_vs_double_ref(void)
{
    ctrl_state_t s;
    refctrl_t r;
    double maxerr = 0.0;
    long tick;
    ctrl_init(&s);
    refctrl_init(&r);
    for (tick = 0; tick < 20000; tick++) { /* 1 s at 50 us */
        refin_t rin;
        ctrl_in_t fin;
        ctrl_out_t fout;
        double rv_ctrl[3], rd[6];
        int i;
        profile(tick, &rin);
        rv_ctrl[0] = rin.Vref[0];
        rv_ctrl[1] = 0.3; /* exercise all three reference channels */
        rv_ctrl[2] = -0.2;
        for (i = 0; i < 4; i++) {
            fin.VM[i] = (float)rin.VM[i];
        }
        for (i = 0; i < 6; i++) {
            fin.IL[i] = (float)rin.IL[i];
        }
        for (i = 0; i < 3; i++) {
            fin.rv[i] = (float)rv_ctrl[i];
        }
        ctrl_step(&fin, &s, &fout);
        refctrl_step(&r, rin.VM, rin.IL, rv_ctrl, rd);
        for (i = 0; i < 6; i++) {
            double e = fabs((double)fout.d[i] - rd[i]);
            maxerr = (e > maxerr) ? e : maxerr;
        }
    }
    printf("  ctrl float32 vs double ref, 20000 ticks: max duty err %.3e\n", maxerr);
    CHECK(maxerr < 1e-3); /* golden duty gate */
}

static void test_sup_seed_and_reset(void)
{
    sup_state_t s;
    sup_in_t in;
    sup_out_t out;
    int i;
    memset(&in, 0, sizeof in);
    for (i = 0; i < 4; i++) {
        in.IM[i] = 10.0f + (float)i;
    }
    for (i = 0; i < 6; i++) {
        in.d[i] = 0.5f;
    }
    in.en = 1.0f;
    sup_init(&s);
    sup_step(&in, &s, &out);
    for (i = 0; i < 4; i++) {
        CHECK(s.imf[i] == in.IM[i]); /* seeded then filtered toward itself */
    }
    /* en = 0: outputs zeroed, filters re-seed to the CURRENT inputs */
    in.en = 0.0f;
    in.IM[0] = 99.0f;
    sup_step(&in, &s, &out);
    CHECK(out.rv[0] == 0.0f && out.rv[1] == 0.0f && out.rv[2] == 0.0f);
    CHECK(out.beta == 0.0f && out.stress == 0.0f);
    CHECK(s.b == 0.0f);
    CHECK(s.imf[0] == 99.0f);
    /* re-enable: filtering resumes from the re-seeded state */
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
    for (i = 0; i < 4; i++) {
        in.IM[i] = 10.0f; /* equal: dl = 0, rv = 0 */
    }
    in.en = 1.0f;
    sup_init(&s);
    /* stress = 1.0 (duty 0.95 -> 0.45/0.45): b += Ts3*KB*(1-0.9) per step */
    for (i = 0; i < 6; i++) {
        in.d[i] = 0.95f;
    }
    sup_step(&in, &s, &out);
    CHECK_NEAR(out.stress, 1.0, 1e-6);
    CHECK_NEAR(out.beta, 1e-3 * 60.0 * (1.0 - 0.9), 1e-6);
    sup_step(&in, &s, &out);
    CHECK_NEAR(out.beta, 2.0 * 1e-3 * 60.0 * (1.0 - 0.9), 1e-6);
    /* hold band: stress = 0.8 (duty 0.86 -> 0.36/0.45) leaves b untouched */
    b_held = out.beta;
    for (i = 0; i < 6; i++) {
        in.d[i] = 0.86f;
    }
    sup_step(&in, &s, &out);
    CHECK_NEAR(out.stress, 0.8, 1e-6);
    CHECK(out.beta == b_held);
    sup_step(&in, &s, &out);
    CHECK(out.beta == b_held);
    /* release: stress = 0 (duty 0.5) drains b, clamped at 0 */
    for (i = 0; i < 6; i++) {
        in.d[i] = 0.5f;
    }
    sup_step(&in, &s, &out);
    CHECK_NEAR(out.beta, b_held - 1e-3 * 6.0 * 0.7, 1e-6);
    for (i = 0; i < 100; i++) {
        sup_step(&in, &s, &out);
    }
    CHECK(out.beta == 0.0f);
    /* attack to the BMAX = 4 ceiling */
    for (i = 0; i < 6; i++) {
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
    in.IM[0] = 0.0f;
    in.IM[1] = 20.0f; /* dl = [20, 0, 20, 20]: dl(2)-dl(1) = -20 */
    in.IM[2] = 0.0f;
    in.IM[3] = 0.0f;
    for (i = 0; i < 6; i++) {
        in.d[i] = 0.95f; /* stress 1.0: pump b to BMAX */
    }
    sup_init(&s);
    for (i = 0; i < 1000; i++) {
        sup_step(&in, &s, &out);
    }
    CHECK(out.beta == 4.0f);
    CHECK(out.rv[0] == -30.0f); /* 4*(-20) clamped to -RVMAX */
    CHECK(out.rv[1] == 30.0f);  /* 4*(+20) clamped to +RVMAX */
    CHECK(out.rv[2] == 0.0f);
}

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
    for (i = 0; i < 19; i++) {
        mppt_step(&in, &s, &out);
        CHECK(out.Iref == 12.0f);
        CHECK(out.Pav == 0.0f);
        CHECK(out.state == 0.0f);
    }
    mppt_step(&in, &s, &out); /* window 1 boundary: boot perturb */
    CHECK(out.Iref == 12.25f);
    CHECK(out.Pav == 500.0f);
    CHECK(out.state == 1.0f);
    for (i = 0; i < 19; i++) {
        mppt_step(&in, &s, &out);
        CHECK(out.Iref == 12.25f); /* held between windows */
    }
    mppt_step(&in, &s, &out); /* window 2: dP = 0, deadband */
    CHECK(out.Iref == 12.25f);
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
    for (i = 0; i < 20; i++) {
        mppt_step(&in, &s, &out); /* window 1: boot, iref 12.25, Pprev 500 */
    }
    iref_after_boot = out.Iref;
    in.Istr = 5.2f; /* P = 520: dP = +20 -> step = clamp(0.2), dirn stays +1 */
    for (i = 0; i < 20; i++) {
        mppt_step(&in, &s, &out);
    }
    CHECK_NEAR(out.Iref, iref_after_boot + 0.2f, 1e-5);
    CHECK(out.state == 1.0f);
    CHECK(out.Iref > iref_after_boot);
    in.Istr = 5.0f; /* P back to 500: dP = -20 -> direction REVERSAL */
    for (i = 0; i < 20; i++) {
        mppt_step(&in, &s, &out);
    }
    CHECK_NEAR(out.Iref, iref_after_boot, 1e-5); /* stepped back down */
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
    for (i = 0; i < 20; i++) {
        mppt_step(&in, &s, &out); /* window 1: boot */
    }
    iref_held = out.Iref;
    in.beta = 0.5f; /* governor moved: next boundary holds and re-arms boot */
    for (i = 0; i < 20; i++) {
        mppt_step(&in, &s, &out);
    }
    CHECK(out.Iref == iref_held);
    CHECK(out.state == 0.0f);
    /* beta steady again: boot perturb fires on the following window */
    for (i = 0; i < 20; i++) {
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
    for (i = 0; i < 30; i++) {
        mppt_step(&in, &s, &out); /* past boot: iref 12.25 */
    }
    CHECK(out.Iref == 12.25f);
    in.en = 0.0f;
    in.Vstr = 90.0f;
    mppt_step(&in, &s, &out);
    CHECK(out.Iref == 12.0f);           /* back to IREF0 */
    CHECK(out.Pav == 90.0f * 5.0f);     /* quirk: instantaneous power */
    CHECK(out.state == 0.0f);
    in.en = 1.0f;
    in.Vstr = 100.0f;
    /* window realigns to the re-enable instant: boot fires 20 calls later */
    for (i = 0; i < 19; i++) {
        mppt_step(&in, &s, &out);
        CHECK(out.Iref == 12.0f);
    }
    mppt_step(&in, &s, &out);
    CHECK(out.Iref == 12.25f);
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
    /* monotonically rising power, dP = +200 each window: step clamps at SMAX=1,
     * iref climbs 1 A/window into the IMAX = 14.5 ceiling */
    for (w = 0; w < 12; w++) {
        in.Istr = 5.0f + 2.0f * (float)w;
        for (i = 0; i < 20; i++) {
            mppt_step(&in, &s, &out);
        }
    }
    CHECK(out.Iref == 14.5f);
    /* one falling window flips dirn to -1 (P&O reversal), then rising power
     * with dirn = -1 walks iref down 1 A/window into the IMIN = 5 floor */
    in.Istr = 25.0f; /* P drops 2700 -> 2500 */
    for (i = 0; i < 20; i++) {
        mppt_step(&in, &s, &out);
    }
    CHECK(s.dirn == -1.0f);
    CHECK(out.Iref == 13.5f);
    for (w = 0; w < 12; w++) {
        in.Istr = 26.0f + 1.0f * (float)w; /* dP = +100 each window */
        for (i = 0; i < 20; i++) {
            mppt_step(&in, &s, &out);
        }
    }
    CHECK(out.Iref == 5.0f);
}

static void test_stack_delays_and_decimation(void)
{
    stack_state_t st;
    stack_in_t in;
    stack_out_t out;
    ctrl_state_t cs;
    long tick;
    int i;
    memset(&in, 0, sizeof in);
    for (i = 0; i < 4; i++) {
        in.VM[i] = 38.0f;
        in.IM[i] = 12.0f; /* equal modules: supervisor rv stays 0 */
    }
    in.Vstr = 152.0f;
    in.Istr = 11.0f;
    in.Vref[0] = 0.5f;
    in.en_sup = 1.0f;
    in.en_mppt = 1.0f;
    stack_init(&st);
    ctrl_init(&cs);
    for (tick = 0; tick < 460; tick++) {
        ctrl_in_t ci;
        ctrl_out_t co;
        stack_step(&in, &st, &out);
        /* rv path: delayed sup rv (= 0 here) + Vref must reach the controller */
        for (i = 0; i < 4; i++) {
            ci.VM[i] = in.VM[i];
        }
        for (i = 0; i < 6; i++) {
            ci.IL[i] = in.IL[i];
        }
        ci.rv[0] = 0.5f;
        ci.rv[1] = 0.0f;
        ci.rv[2] = 0.0f;
        ctrl_step(&ci, &cs, &co);
        for (i = 0; i < 6; i++) {
            CHECK(out.d[i] == co.d[i]);
        }
        /* Iref unit delay: IC = IREF0 for the whole first 1 ms frame; the boot
         * perturb lands at boundary tick 380 (MPPT call #20) and appears on
         * the DELAYED output exactly one frame later, at tick 400 */
        if (tick < 400) {
            CHECK(out.Iref_dly == 12.0f);
        } else {
            CHECK(out.Iref_dly == 12.25f);
        }
        if (tick < 380) {
            CHECK(out.Iref == 12.0f);
        } else {
            CHECK(out.Iref == 12.25f);
        }
        /* MPPT state only advances at 1 ms boundaries (20:1 decimation) */
        if (tick >= 380 && tick < 400) {
            CHECK(out.mppt_state == 1.0f);
        }
        if (tick < 380) {
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
    for (i = 0; i < 4; i++) {
        in.VM[i] = 38.0f;
        in.IM[i] = 10.0f + 2.0f * (float)i; /* unequal: nonzero dl */
    }
    in.Vstr = 152.0f;
    in.Istr = 11.0f;
    in.en_sup = 0.0f;
    in.en_mppt = 0.0f;
    stack_init(&st);
    for (tick = 0; tick < 100; tick++) {
        stack_step(&in, &st, &out);
        CHECK(out.beta == 0.0f && out.stress == 0.0f);
        CHECK(out.rv[0] == 0.0f && out.rv[1] == 0.0f && out.rv[2] == 0.0f);
        CHECK(out.Iref == 12.0f);
        CHECK(out.mppt_state == 0.0f);
    }
}

static void test_stack_vs_double_ref(void)
{
    stack_state_t fs;
    refstack_t rs;
    double emax_d = 0.0, emax_rv = 0.0, emax_beta = 0.0, emax_iref = 0.0;
    long state_mismatch = 0, tick;
    const long NTICK = 40000; /* 2 s at 50 us */
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
        for (i = 0; i < 6; i++) {
            e = fabs((double)fo.d[i] - ro.d[i]);
            emax_d = (e > emax_d) ? e : emax_d;
        }
        for (i = 0; i < 3; i++) {
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
           (double)NTICK * 50e-6);
    printf("    max err  duty %.3e  rv %.3e  beta %.3e  Iref %.3e  state mismatches %ld\n",
           emax_d, emax_rv, emax_beta, emax_iref, state_mismatch);
    CHECK(emax_d < 1e-3); /* golden gates (rule-6 drift evidence) */
    CHECK(emax_rv < 1e-2);
    CHECK(emax_beta < 1e-2);
    CHECK(emax_iref < 1e-2);
    CHECK(state_mismatch == 0);
}

int main(void)
{
    printf("shuffler stack unit tests, %s, accum=%s\n", PARAMS_VERSION,
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
