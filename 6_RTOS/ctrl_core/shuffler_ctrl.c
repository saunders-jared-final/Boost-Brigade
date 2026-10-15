/*
 * shuffler_ctrl.c - inner MIMO duty controller (CTRL_TS tick)
 *
 * Port of shuffler_string_ctrl.m. Structure and operation order follow the
 * MATLAB reference line by line; only the matrix-vector products are spelled
 * out as loops. Channel layout of y/e/u: [0, N_SHUF) voltage differences,
 * [N_SHUF, N_Y) common-mode shuffler currents.
 */
#include "shuffler_ctrl.h"

#ifdef CTRL_RUNTIME_GAINS
ctrl_gains_t ctrl_gains = {CTRL_M_INIT, CTRL_MP_INIT, CTRL_MINV_INIT, CTRL_A, CTRL_DMIN, CTRL_DMAX, 0u};
#define ctrl_M        ctrl_gains.M
#define ctrl_Mp       ctrl_gains.Mp
#define ctrl_Minv     ctrl_gains.Minv
#define CTRL_A_NOW    ctrl_gains.a
#define CTRL_DMIN_NOW ctrl_gains.dmin
#define CTRL_DMAX_NOW ctrl_gains.dmax
#else
MAT_CONST ctrl_M[N_Y][N_Y] = CTRL_M_INIT;
MAT_CONST ctrl_Mp[N_Y][N_Y] = CTRL_MP_INIT;
MAT_CONST ctrl_Minv[N_Y][N_Y] = CTRL_MINV_INIT;
#define CTRL_A_NOW    CTRL_A
#define CTRL_DMIN_NOW CTRL_DMIN
#define CTRL_DMAX_NOW CTRL_DMAX
#endif

/* MATLAB min(max(x, lo), hi): NaN maps to lo */
static float clamp_f(float x, float lo, float hi)
{
    float y = (x > lo) ? x : lo;
    return (y < hi) ? y : hi;
}

void ctrl_init(ctrl_state_t *state)
{
    uint8_t i;
#ifdef CTRL_RUNTIME_GAINS
    uint8_t j;
#endif
    for (i = 0u; i < (uint8_t)N_Y; i++) {
        state->xi[i] = (ctrl_accum_t)0;
        state->y_f[i] = 0.0f;
    }
#ifdef CTRL_RUNTIME_GAINS
    for (j = 0u; j < (uint8_t)CTRL_MA_MAX; j++) {
        for (i = 0u; i < (uint8_t)N_Y; i++) {
            state->ma_buf[j][i] = 0.0f;
        }
    }
    state->ma_idx = 0u;
    state->ma_cnt = 0u;
#endif
}

void ctrl_step(const ctrl_in_t *in, ctrl_state_t *state, ctrl_out_t *out)
{
    float y[N_Y];
    float e[N_Y];
    float u_act[N_Y];
    ctrl_accum_t xi_try[N_Y];
    ctrl_accum_t mpe[N_Y];
    ctrl_accum_t u[N_Y];
    uint8_t i;
    uint8_t j;

    /* y = [VM1-VM2, ..., VM(n-1)-VMn, ic1, ..., ic(n-1)], ic = per-shuffler A+B sum */
    for (i = 0u; i < (uint8_t)N_SHUF; i++) {
        y[i] = in->VM[i] - in->VM[i + 1u];
        y[(uint8_t)N_SHUF + i] = in->IL[2u * i] + in->IL[2u * i + 1u];
    }

    /* y_f = y_f + a*(y - y_f) */
    for (i = 0u; i < (uint8_t)N_Y; i++) {
        state->y_f[i] = state->y_f[i] + CTRL_A_NOW * (y[i] - state->y_f[i]);
    }
#ifdef CTRL_RUNTIME_GAINS
    /* optional moving average over the last ma_n ticks (replaces the IIR output);
     * the ring buffer is filled every tick in either mode */
    for (i = 0u; i < (uint8_t)N_Y; i++) {
        state->ma_buf[state->ma_idx][i] = y[i];
    }
    state->ma_idx = (uint8_t)((state->ma_idx + 1u) % CTRL_MA_MAX);
    if (state->ma_cnt < (uint8_t)CTRL_MA_MAX) {
        state->ma_cnt++;
    }
    if (ctrl_gains.ma_n > 0u) {
        uint8_t n = (ctrl_gains.ma_n < state->ma_cnt) ? ctrl_gains.ma_n : state->ma_cnt;
        uint8_t k;
        for (i = 0u; i < (uint8_t)N_Y; i++) {
            float s = 0.0f;
            for (k = 1u; k <= n; k++) {
                s += state->ma_buf[(uint8_t)((state->ma_idx + CTRL_MA_MAX - k) % CTRL_MA_MAX)][i];
            }
            state->y_f[i] = s / (float)n;
        }
    }
#endif

    /* e = r - y_f, r = [rv, 0] */
    for (i = 0u; i < (uint8_t)N_SHUF; i++) {
        e[i] = in->rv[i] - state->y_f[i];
        e[(uint8_t)N_SHUF + i] = 0.0f - state->y_f[(uint8_t)N_SHUF + i];
    }

    /* xi_try = xi + Ts*e */
    for (i = 0u; i < (uint8_t)N_Y; i++) {
        xi_try[i] = state->xi[i] + (ctrl_accum_t)CTRL_TS * (ctrl_accum_t)e[i];
    }

    /* mpe = Mp*e (reused in the anti-windup recompute) */
    for (i = 0u; i < (uint8_t)N_Y; i++) {
        ctrl_accum_t acc = (ctrl_accum_t)0;
        for (j = 0u; j < (uint8_t)N_Y; j++) {
            acc += (ctrl_accum_t)MAT_RD(ctrl_Mp, i, j) * (ctrl_accum_t)e[j];
        }
        mpe[i] = acc;
    }

    /* u = Mp*e + M*xi_try: products rounded separately then added, like MATLAB */
    for (i = 0u; i < (uint8_t)N_Y; i++) {
        ctrl_accum_t acc = (ctrl_accum_t)0;
        for (j = 0u; j < (uint8_t)N_Y; j++) {
            acc += (ctrl_accum_t)MAT_RD(ctrl_M, i, j) * xi_try[j];
        }
        u[i] = mpe[i] + acc;
    }

    /* duty mapping + clamp, then actually-applied u for the anti-windup path */
    for (i = 0u; i < (uint8_t)N_SHUF; i++) {
        float uc = (float)u[i];
        float ud = (float)u[(uint8_t)N_SHUF + i];
        float dA = clamp_f(0.5f + 0.5f * (uc + ud), CTRL_DMIN_NOW, CTRL_DMAX_NOW);
        float dB = clamp_f(0.5f + 0.5f * (uc - ud), CTRL_DMIN_NOW, CTRL_DMAX_NOW);
        out->d[2u * i] = dA;
        out->d[2u * i + 1u] = dB;
        u_act[i] = (dA + dB) - 1.0f;
        u_act[(uint8_t)N_SHUF + i] = dA - dB;
    }

    /* anti-windup: xi = Minv*(u_act - Mp*e), recomputed EVERY step (reference quirk) */
    for (i = 0u; i < (uint8_t)N_Y; i++) {
        ctrl_accum_t acc = (ctrl_accum_t)0;
        for (j = 0u; j < (uint8_t)N_Y; j++) {
            acc += (ctrl_accum_t)MAT_RD(ctrl_Minv, i, j) * ((ctrl_accum_t)u_act[j] - mpe[j]);
        }
        state->xi[i] = acc;
    }
}

#ifdef CTRL_RUNTIME_GAINS
void ctrl_rebase(ctrl_state_t *state, const float d[N_LEG])
{
    float u_act[N_Y];
    uint8_t i;
    uint8_t j;

    for (i = 0u; i < (uint8_t)N_SHUF; i++) {
        u_act[i] = (d[2u * i] + d[2u * i + 1u]) - 1.0f;
        u_act[(uint8_t)N_SHUF + i] = d[2u * i] - d[2u * i + 1u];
    }
    for (i = 0u; i < (uint8_t)N_Y; i++) {
        ctrl_accum_t acc = (ctrl_accum_t)0;
        for (j = 0u; j < (uint8_t)N_Y; j++) {
            acc += (ctrl_accum_t)ctrl_Minv[i][j] * (ctrl_accum_t)u_act[j];
        }
        state->xi[i] = acc;
    }
}
#endif
