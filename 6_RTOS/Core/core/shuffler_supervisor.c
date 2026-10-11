/*
 * shuffler_supervisor.c - supervisory feasibility governor (1 ms tick)
 *
 * Port of shuffler_string_supervisor.m, line for line. VM inputs are accepted
 * but unused, exactly as in the reference.
 */
#include "shuffler_supervisor.h"

#include <math.h>

#include "params.h"

/* MATLAB min(max(x, lo), hi) */
static float clamp_f(float x, float lo, float hi)
{
    float y = (x > lo) ? x : lo;
    return (y < hi) ? y : hi;
}

void sup_init(sup_state_t *state)
{
    uint8_t i;
    state->b = 0.0f;
    for (i = 0u; i < 4u; i++) {
        state->imf[i] = 0.0f;
    }
    for (i = 0u; i < 3u; i++) {
        state->idf[i] = 0.0f;
    }
    state->seeded = 0u;
}

void sup_step(const sup_in_t *in, sup_state_t *state, sup_out_t *out)
{
    float id[3];
    float dl[4];
    float imax;
    float sid;
    float sdu;
    float stress;
    uint8_t i;

    /* id = per-shuffler A-B differential currents */
    id[0] = in->IL[0] - in->IL[1];
    id[1] = in->IL[2] - in->IL[3];
    id[2] = in->IL[4] - in->IL[5];

    /* first-call seeding, mirroring the MATLAB persistent-empty init */
    if (state->seeded == 0u) {
        state->b = 0.0f;
        for (i = 0u; i < 4u; i++) {
            state->imf[i] = in->IM[i];
        }
        for (i = 0u; i < 3u; i++) {
            state->idf[i] = id[i];
        }
        state->seeded = 1u;
    }

    if (in->en == 0.0f) {
        state->b = 0.0f;
        for (i = 0u; i < 4u; i++) {
            state->imf[i] = in->IM[i];
        }
        for (i = 0u; i < 3u; i++) {
            state->idf[i] = id[i];
        }
        out->rv[0] = 0.0f;
        out->rv[1] = 0.0f;
        out->rv[2] = 0.0f;
        out->beta = 0.0f;
        out->stress = 0.0f;
        return;
    }

    /* imf = imf + (Ts3/TF)*(im - imf);  dl = max(imf) - imf */
    for (i = 0u; i < 4u; i++) {
        state->imf[i] = state->imf[i] + SUP_ALPHA * (in->IM[i] - state->imf[i]);
    }
    imax = state->imf[0];
    for (i = 1u; i < 4u; i++) {
        imax = (state->imf[i] > imax) ? state->imf[i] : imax;
    }
    for (i = 0u; i < 4u; i++) {
        dl[i] = imax - state->imf[i];
    }

    /* idf = idf + (Ts3/TF)*(idm - idf) */
    for (i = 0u; i < 3u; i++) {
        state->idf[i] = state->idf[i] + SUP_ALPHA * (id[i] - state->idf[i]);
    }

    /* stress = max( max|idf|/I_RATED , max|d - 0.5|/0.45 ) */
    sid = fabsf(state->idf[0]);
    for (i = 1u; i < 3u; i++) {
        float t = fabsf(state->idf[i]);
        sid = (t > sid) ? t : sid;
    }
    sdu = fabsf(in->d[0] - 0.5f);
    for (i = 1u; i < 6u; i++) {
        float t = fabsf(in->d[i] - 0.5f);
        sdu = (t > sdu) ? t : sdu;
    }
    sid = sid / SUP_I_RATED;
    sdu = sdu / 0.45f;
    stress = (sid > sdu) ? sid : sdu;

    /* beta integrator with hysteresis hold band [S_LO, S_HI] */
    if (stress > SUP_S_HI) {
        state->b = state->b + SUP_TS3 * SUP_KB * (stress - SUP_S_HI);
    } else if (stress < SUP_S_LO) {
        state->b = state->b - SUP_TS3 * SUP_KREL * (SUP_S_LO - stress);
    }
    state->b = clamp_f(state->b, 0.0f, SUP_BMAX);

    /* rv = b*(dl(2:4) - dl(1:3)), clamped to +/-RVMAX */
    for (i = 0u; i < 3u; i++) {
        float rv = state->b * (dl[i + 1u] - dl[i]);
        out->rv[i] = clamp_f(rv, -SUP_RVMAX, SUP_RVMAX);
    }
    out->beta = state->b;
    out->stress = stress;
}
