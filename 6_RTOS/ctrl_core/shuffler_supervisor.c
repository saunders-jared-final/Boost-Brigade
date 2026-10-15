/*
 * shuffler_supervisor.c - supervisory feasibility governor (SUP_TS3 tick)
 *
 * Port of shuffler_string_supervisor.m, line for line. VM inputs are accepted
 * but unused, exactly as in the reference.
 */
#include "shuffler_supervisor.h"

#ifdef CTRL_RUNTIME_GAINS
sup_rt_t sup_rt = {SUP_I_RATED, SUP_S_HI, SUP_S_LO};
#define SUP_I_RATED_NOW sup_rt.i_rated
#define SUP_S_HI_NOW    sup_rt.s_hi
#define SUP_S_LO_NOW    sup_rt.s_lo
#else
#define SUP_I_RATED_NOW SUP_I_RATED
#define SUP_S_HI_NOW    SUP_S_HI
#define SUP_S_LO_NOW    SUP_S_LO
#endif

#include <math.h>

/* MATLAB min(max(x, lo), hi) */
static float clamp_f(float x, float lo, float hi)
{
    float y = (x > lo) ? x : lo;
    return (y < hi) ? y : hi;
}

static void seed(const sup_in_t *in, const float *id, sup_state_t *state)
{
    uint8_t i;
    state->b = 0.0f;
    for (i = 0u; i < (uint8_t)N_MOD; i++) {
        state->imf[i] = in->IM[i];
    }
    for (i = 0u; i < (uint8_t)N_SHUF; i++) {
        state->idf[i] = id[i];
    }
}

void sup_init(sup_state_t *state)
{
    uint8_t i;
    state->b = 0.0f;
    for (i = 0u; i < (uint8_t)N_MOD; i++) {
        state->imf[i] = 0.0f;
    }
    for (i = 0u; i < (uint8_t)N_SHUF; i++) {
        state->idf[i] = 0.0f;
    }
    state->seeded = 0u;
}

void sup_step(const sup_in_t *in, sup_state_t *state, sup_out_t *out)
{
    float id[N_SHUF];
    float dl[N_MOD];
    float imax;
    float sid;
    float sdu;
    float stress;
    uint8_t i;

    /* id = per-shuffler A-B differential currents */
    for (i = 0u; i < (uint8_t)N_SHUF; i++) {
        id[i] = in->IL[2u * i] - in->IL[2u * i + 1u];
    }

    /* first-call seeding, mirroring the MATLAB persistent-empty init */
    if (state->seeded == 0u) {
        seed(in, id, state);
        state->seeded = 1u;
    }

    if (in->en == 0.0f) {
        seed(in, id, state);
        for (i = 0u; i < (uint8_t)N_SHUF; i++) {
            out->rv[i] = 0.0f;
        }
        out->beta = 0.0f;
        out->stress = 0.0f;
        return;
    }

    /* imf = imf + (Ts3/TF)*(im - imf);  dl = max(imf) - imf */
    for (i = 0u; i < (uint8_t)N_MOD; i++) {
        state->imf[i] = state->imf[i] + SUP_ALPHA * (in->IM[i] - state->imf[i]);
    }
    imax = state->imf[0];
    for (i = 1u; i < (uint8_t)N_MOD; i++) {
        imax = (state->imf[i] > imax) ? state->imf[i] : imax;
    }
    for (i = 0u; i < (uint8_t)N_MOD; i++) {
        dl[i] = imax - state->imf[i];
    }

    /* idf = idf + (Ts3/TF)*(idm - idf) */
    for (i = 0u; i < (uint8_t)N_SHUF; i++) {
        state->idf[i] = state->idf[i] + SUP_ALPHA * (id[i] - state->idf[i]);
    }

    /* stress = max( max|idf|/I_RATED , max|d - 0.5|/0.45 ) */
    sid = fabsf(state->idf[0]);
    for (i = 1u; i < (uint8_t)N_SHUF; i++) {
        float t = fabsf(state->idf[i]);
        sid = (t > sid) ? t : sid;
    }
    sdu = fabsf(in->d[0] - 0.5f);
    for (i = 1u; i < (uint8_t)N_LEG; i++) {
        float t = fabsf(in->d[i] - 0.5f);
        sdu = (t > sdu) ? t : sdu;
    }
    sid = sid / SUP_I_RATED_NOW;
    sdu = sdu / 0.45f;
    stress = (sid > sdu) ? sid : sdu;

    /* beta integrator with hysteresis hold band [S_LO, S_HI] */
    if (stress > SUP_S_HI_NOW) {
        state->b = state->b + SUP_TS3 * SUP_KB * (stress - SUP_S_HI_NOW);
    } else if (stress < SUP_S_LO_NOW) {
        state->b = state->b - SUP_TS3 * SUP_KREL * (SUP_S_LO_NOW - stress);
    }
    state->b = clamp_f(state->b, 0.0f, SUP_BMAX);

    /* rv = b*(dl(2:n) - dl(1:n-1)), clamped to +/-RVMAX */
    for (i = 0u; i < (uint8_t)N_SHUF; i++) {
        float rv = state->b * (dl[i + 1u] - dl[i]);
        out->rv[i] = clamp_f(rv, -SUP_RVMAX, SUP_RVMAX);
    }
    out->beta = state->b;
    out->stress = stress;
}
