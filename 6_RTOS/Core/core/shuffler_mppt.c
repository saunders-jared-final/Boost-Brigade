/*
 * shuffler_mppt.c - adaptive-step P&O MPPT (1 ms tick)
 *
 * Port of shuffler_string_mppt.m, line for line.
 */
#include "shuffler_mppt.h"

#include <math.h>

#include "params.h"

/* MATLAB min(max(x, lo), hi) */
static float clamp_f(float x, float lo, float hi)
{
    float y = (x > lo) ? x : lo;
    return (y < hi) ? y : hi;
}

void mppt_init(mppt_state_t *state)
{
    state->iref = MPPT_IREF0;
    state->dirn = 1.0f;
    state->Pprev = 0.0f;
    state->acc = 0.0f;
    state->n = 0u;
    state->boot = 1u;
    state->b0 = 0.0f; /* seeded from the live beta input on the first step */
    state->st = 0u;
    state->seeded = 0u;
}

void mppt_step(const mppt_in_t *in, mppt_state_t *state, mppt_out_t *out)
{
    /* first-call seeding, mirroring the MATLAB persistent-empty init */
    if (state->seeded == 0u) {
        state->b0 = in->beta;
        state->seeded = 1u;
    }

    if (in->en == 0.0f) {
        state->iref = MPPT_IREF0;
        state->dirn = 1.0f;
        state->Pprev = 0.0f;
        state->acc = 0.0f;
        state->n = 0u;
        state->boot = 1u;
        state->b0 = in->beta;
        state->st = 0u;
        out->Iref = state->iref;
        out->Pav = in->Vstr * in->Istr; /* reference quirk: instantaneous power */
        out->state = 0.0f;
        return;
    }

    state->acc = state->acc + in->Vstr * in->Istr;
    state->n = state->n + 1u;

    if (state->n >= (uint8_t)MPPT_N) {
        float Pw = state->acc / (float)MPPT_N;
        uint8_t govActive;
        state->acc = 0.0f;
        state->n = 0u;

        govActive = (fabsf(in->beta - state->b0) > MPPT_BTOL) ? 1u : 0u;
        state->b0 = in->beta;

        if (govActive != 0u) {
            /* governor moved: hold iref, re-arm boot perturb */
            state->boot = 1u;
            state->st = 0u;
        } else if (state->boot != 0u) {
            state->Pprev = Pw;
            state->boot = 0u;
            state->iref = state->iref + state->dirn * MPPT_S0;
            state->st = 1u;
        } else {
            float dP = Pw - state->Pprev;
            if (dP > MPPT_DB) {
                float step = clamp_f(MPPT_KA * fabsf(dP), MPPT_SMIN, MPPT_SMAX);
                state->iref = state->iref + state->dirn * step;
                state->st = 1u;
            } else if (dP < -MPPT_DB) {
                float step;
                state->dirn = -state->dirn;
                step = clamp_f(MPPT_KA * fabsf(dP), MPPT_SMIN, MPPT_SMAX);
                state->iref = state->iref + state->dirn * step;
                state->st = 1u;
            } else {
                state->st = 2u;
            }
            state->Pprev = Pw;
        }
        state->iref = clamp_f(state->iref, MPPT_IMIN, MPPT_IMAX);
    }

    out->Iref = state->iref;
    out->Pav = state->Pprev;
    out->state = (float)state->st;
}
