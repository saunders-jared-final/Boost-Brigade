/*
 * sil_wrappers.c - flat entry points for Simulink C Caller blocks (SIL)
 *
 * Single-instance state in file statics; auto-initializes on the first step
 * after load or after sil_reset(), so seeding-from-first-inputs matches the
 * MATLAB persistent-empty semantics.
 */
#include "sil_wrappers.h"

#include <stdint.h>

#include "shuffler_ctrl.h"
#include "shuffler_mppt.h"
#include "shuffler_supervisor.h"

static ctrl_state_t g_ctrl;
static sup_state_t g_sup;
static mppt_state_t g_mppt;
static uint8_t g_ctrl_ready = 0u;
static uint8_t g_sup_ready = 0u;
static uint8_t g_mppt_ready = 0u;

void sil_ctrl_step(const float VM[4], const float IL[6], const float rv[3], float *dA1,
                   float *dB1, float *dA2, float *dB2, float *dA3, float *dB3)
{
    ctrl_in_t in;
    ctrl_out_t out;
    uint8_t i;

    if (g_ctrl_ready == 0u) {
        ctrl_init(&g_ctrl);
        g_ctrl_ready = 1u;
    }
    for (i = 0u; i < 4u; i++) {
        in.VM[i] = VM[i];
    }
    for (i = 0u; i < 6u; i++) {
        in.IL[i] = IL[i];
    }
    for (i = 0u; i < 3u; i++) {
        in.rv[i] = rv[i];
    }
    ctrl_step(&in, &g_ctrl, &out);
    *dA1 = out.d[0];
    *dB1 = out.d[1];
    *dA2 = out.d[2];
    *dB2 = out.d[3];
    *dA3 = out.d[4];
    *dB3 = out.d[5];
}

void sil_supervisor_step(const float VM[4], const float IM[4], const float IL[6], float dA1,
                         float dB1, float dA2, float dB2, float dA3, float dB3, float en,
                         float *rv1, float *rv2, float *rv3, float *beta, float *stress)
{
    sup_in_t in;
    sup_out_t out;
    uint8_t i;

    if (g_sup_ready == 0u) {
        sup_init(&g_sup);
        g_sup_ready = 1u;
    }
    for (i = 0u; i < 4u; i++) {
        in.VM[i] = VM[i];
        in.IM[i] = IM[i];
    }
    for (i = 0u; i < 6u; i++) {
        in.IL[i] = IL[i];
    }
    in.d[0] = dA1;
    in.d[1] = dB1;
    in.d[2] = dA2;
    in.d[3] = dB2;
    in.d[4] = dA3;
    in.d[5] = dB3;
    in.en = en;
    sup_step(&in, &g_sup, &out);
    *rv1 = out.rv[0];
    *rv2 = out.rv[1];
    *rv3 = out.rv[2];
    *beta = out.beta;
    *stress = out.stress;
}

void sil_mppt_step(float Vstr, float Istr, float beta, float en, float *Iref, float *Pav,
                   float *state)
{
    mppt_in_t in;
    mppt_out_t out;

    if (g_mppt_ready == 0u) {
        mppt_init(&g_mppt);
        g_mppt_ready = 1u;
    }
    in.Vstr = Vstr;
    in.Istr = Istr;
    in.beta = beta;
    in.en = en;
    mppt_step(&in, &g_mppt, &out);
    *Iref = out.Iref;
    *Pav = out.Pav;
    *state = out.state;
}

void sil_reset(void)
{
    g_ctrl_ready = 0u;
    g_sup_ready = 0u;
    g_mppt_ready = 0u;
}

float sil_reset_pass(float u)
{
    sil_reset();
    return u;
}
