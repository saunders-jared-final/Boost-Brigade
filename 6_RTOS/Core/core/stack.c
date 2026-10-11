/*
 * stack.c - full control stack scheduler (50 us tick)
 *
 * See stack.h for the timing model. This file adds no control mathematics of
 * its own beyond the rv + Vref summation; it only sequences the three modules
 * and replicates the model-side unit delays.
 */
#include "stack.h"

#include "params.h"

void stack_init(stack_state_t *state)
{
    uint8_t i;
    ctrl_init(&state->ctrl);
    sup_init(&state->sup);
    mppt_init(&state->mppt);
    state->tick = 0u;
    for (i = 0u; i < 3u; i++) {
        state->rv_dly[i] = STACK_RV_DLY_IC;
        state->rv_out[i] = STACK_RV_DLY_IC;
        state->rv_now[i] = 0.0f;
    }
    state->iref_dly = STACK_IREF_DLY_IC;
    state->iref_out = STACK_IREF_DLY_IC;
    for (i = 0u; i < 6u; i++) {
        state->d_last[i] = 0.0f; /* Simulink delay-block default IC */
    }
    state->beta = 0.0f;
    state->stress = 0.0f;
    state->iref_raw = MPPT_IREF0;
    state->pav = 0.0f;
    state->mppt_state = 0.0f;
}

void stack_step(const stack_in_t *in, stack_state_t *state, stack_out_t *out)
{
    ctrl_in_t ci;
    ctrl_out_t co;
    uint8_t boundary = (state->tick == 0u) ? 1u : 0u;
    uint8_t i;

    /* 1 ms boundary: latch the unit-delay outputs (previous boundary's inputs) */
    if (boundary != 0u) {
        for (i = 0u; i < 3u; i++) {
            state->rv_out[i] = state->rv_dly[i];
        }
        state->iref_out = state->iref_dly;
    }

    /* controller, every tick: rv input = delayed supervisor rv + Vref offsets */
    for (i = 0u; i < 4u; i++) {
        ci.VM[i] = in->VM[i];
    }
    for (i = 0u; i < 6u; i++) {
        ci.IL[i] = in->IL[i];
    }
    for (i = 0u; i < 3u; i++) {
        ci.rv[i] = state->rv_out[i] + in->Vref[i];
    }
    ctrl_step(&ci, &state->ctrl, &co);

    /* 1 ms boundary: supervisor first, then MPPT with the fresh beta */
    if (boundary != 0u) {
        sup_in_t si;
        sup_out_t so;
        mppt_in_t mi;
        mppt_out_t mo;

        for (i = 0u; i < 4u; i++) {
            si.VM[i] = in->VM[i];
            si.IM[i] = in->IM[i];
        }
        for (i = 0u; i < 6u; i++) {
            si.IL[i] = in->IL[i];
        }
#if STACK_SUP_DUTY_SAME_TICK
        for (i = 0u; i < 6u; i++) {
            si.d[i] = co.d[i];
        }
#else
        for (i = 0u; i < 6u; i++) {
            si.d[i] = state->d_last[i];
        }
#endif
        si.en = in->en_sup;
        sup_step(&si, &state->sup, &so);

        mi.Vstr = in->Vstr;
        mi.Istr = in->Istr;
        mi.beta = so.beta;
        mi.en = in->en_mppt;
        mppt_step(&mi, &state->mppt, &mo);

        /* store this boundary's rv/Iref into the unit delays for the next one */
        for (i = 0u; i < 3u; i++) {
            state->rv_dly[i] = so.rv[i];
            state->rv_now[i] = so.rv[i];
        }
        state->iref_dly = mo.Iref;
        state->beta = so.beta;
        state->stress = so.stress;
        state->iref_raw = mo.Iref;
        state->pav = mo.Pav;
        state->mppt_state = mo.state;
    }

    for (i = 0u; i < 6u; i++) {
        state->d_last[i] = co.d[i];
    }
    state->tick = state->tick + 1u;
    if (state->tick >= (uint8_t)STACK_DECIM) {
        state->tick = 0u;
    }

    for (i = 0u; i < 6u; i++) {
        out->d[i] = co.d[i];
    }
    for (i = 0u; i < 3u; i++) {
        out->rv[i] = state->rv_now[i];
    }
    out->beta = state->beta;
    out->stress = state->stress;
    out->Iref = state->iref_raw;
    out->Iref_dly = state->iref_out;
    out->Pav = state->pav;
    out->mppt_state = state->mppt_state;
}
