/*
 * shuffler_ctrl.c - inner MIMO duty controller (50 us tick)
 *
 * Port of shuffler_string_ctrl.m. Structure and operation order follow the
 * MATLAB reference line by line; only the matrix-vector products are spelled
 * out as loops. All arithmetic is float32 unless SHUF_ACCUM_DOUBLE widens the
 * integrator chain (see shuffler_ctrl.h).
 */
#include "shuffler_ctrl.h"

#include "params.h"

MAT_CONST ctrl_M[6][6] = CTRL_M_INIT;
MAT_CONST ctrl_Mp[6][6] = CTRL_MP_INIT;
MAT_CONST ctrl_Minv[6][6] = CTRL_MINV_INIT;

/* MATLAB min(max(x, lo), hi): NaN maps to lo, matching MATLAB's NaN-omitting
 * min/max for the second-operand-constant usage here. */
static float clamp_f(float x, float lo, float hi)
{
    float y = (x > lo) ? x : lo;
    return (y < hi) ? y : hi;
}

void ctrl_init(ctrl_state_t *state)
{
    uint8_t i;
    for (i = 0u; i < 6u; i++) {
        state->xi[i] = (ctrl_accum_t)0;
        state->y_f[i] = 0.0f;
    }
}

void ctrl_step(const ctrl_in_t *in, ctrl_state_t *state, ctrl_out_t *out)
{
    float y[6];
    float e[6];
    float u_act[6];
    float dAs[3];
    float dBs[3];
    ctrl_accum_t xi_try[6];
    ctrl_accum_t mpe[6];
    ctrl_accum_t u[6];
    uint8_t i;
    uint8_t j;

    /* y = [VM1-VM2; VM2-VM3; VM3-VM4; ic1; ic2; ic3], ic = per-shuffler A+B sum */
    y[0] = in->VM[0] - in->VM[1];
    y[1] = in->VM[1] - in->VM[2];
    y[2] = in->VM[2] - in->VM[3];
    y[3] = in->IL[0] + in->IL[1];
    y[4] = in->IL[2] + in->IL[3];
    y[5] = in->IL[4] + in->IL[5];

    /* y_f = y_f + a*(y - y_f) */
    for (i = 0u; i < 6u; i++) {
        state->y_f[i] = state->y_f[i] + CTRL_A * (y[i] - state->y_f[i]);
    }

    /* e = r - y_f, r = [rv1; rv2; rv3; 0; 0; 0] */
    e[0] = in->rv[0] - state->y_f[0];
    e[1] = in->rv[1] - state->y_f[1];
    e[2] = in->rv[2] - state->y_f[2];
    e[3] = 0.0f - state->y_f[3];
    e[4] = 0.0f - state->y_f[4];
    e[5] = 0.0f - state->y_f[5];

    /* xi_try = xi + Ts*e */
    for (i = 0u; i < 6u; i++) {
        xi_try[i] = state->xi[i] + (ctrl_accum_t)CTRL_TS * (ctrl_accum_t)e[i];
    }

    /* mpe = Mp*e (also reused below in the anti-windup recompute) */
    for (i = 0u; i < 6u; i++) {
        ctrl_accum_t acc = (ctrl_accum_t)0;
        for (j = 0u; j < 6u; j++) {
            acc += (ctrl_accum_t)MAT_RD(ctrl_Mp, i, j) * (ctrl_accum_t)e[j];
        }
        mpe[i] = acc;
    }

    /* u = Mp*e + M*xi_try: the two matrix-vector products are rounded
     * separately and then added, exactly like the MATLAB expression */
    for (i = 0u; i < 6u; i++) {
        ctrl_accum_t acc = (ctrl_accum_t)0;
        for (j = 0u; j < 6u; j++) {
            acc += (ctrl_accum_t)MAT_RD(ctrl_M, i, j) * xi_try[j];
        }
        u[i] = mpe[i] + acc;
    }

    /* duty mapping + clamp, then actually-applied u for the anti-windup path */
    for (i = 0u; i < 3u; i++) {
        float uc = (float)u[i];
        float ud = (float)u[i + 3u];
        float dA = 0.5f + 0.5f * (uc + ud);
        float dB = 0.5f + 0.5f * (uc - ud);
        dAs[i] = clamp_f(dA, CTRL_DMIN, CTRL_DMAX);
        dBs[i] = clamp_f(dB, CTRL_DMIN, CTRL_DMAX);
        u_act[i] = (dAs[i] + dBs[i]) - 1.0f;
        u_act[i + 3u] = dAs[i] - dBs[i];
    }

    /* anti-windup: xi = Minv*(u_act - Mp*e), recomputed EVERY step (reference quirk) */
    for (i = 0u; i < 6u; i++) {
        ctrl_accum_t acc = (ctrl_accum_t)0;
        for (j = 0u; j < 6u; j++) {
            acc += (ctrl_accum_t)MAT_RD(ctrl_Minv, i, j) * ((ctrl_accum_t)u_act[j] - mpe[j]);
        }
        state->xi[i] = acc;
    }

    out->d[0] = dAs[0];
    out->d[1] = dBs[0];
    out->d[2] = dAs[1];
    out->d[3] = dBs[1];
    out->d[4] = dAs[2];
    out->d[5] = dBs[2];
}
