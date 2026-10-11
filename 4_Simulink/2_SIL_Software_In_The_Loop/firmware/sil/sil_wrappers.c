/*
 * sil_wrappers.c - flat entry points for Simulink C Caller blocks (SIL)
 */
#include "sil_wrappers.h"

#include <stdint.h>

#include "shuffler_ctrl.h"
#include "shuffler_mppt.h"
#include "shuffler_recon.h"
#include "shuffler_supervisor.h"

static ctrl_state_t g_ctrl;
static sup_state_t g_sup;
static mppt_state_t g_mppt;
static uint8_t g_ctrl_ready = 0u;
static uint8_t g_sup_ready = 0u;
static uint8_t g_mppt_ready = 0u;

void sil_ctrl_step(const float VM[N_MOD], const float IL[N_LEG], const float rv[N_SHUF],
                   float d[N_LEG])
{
    ctrl_in_t in;
    ctrl_out_t out;
    uint8_t i;

    if (g_ctrl_ready == 0u) {
        ctrl_init(&g_ctrl);
        g_ctrl_ready = 1u;
    }
    for (i = 0u; i < (uint8_t)N_MOD; i++) {
        in.VM[i] = VM[i];
    }
    for (i = 0u; i < (uint8_t)N_LEG; i++) {
        in.IL[i] = IL[i];
    }
    for (i = 0u; i < (uint8_t)N_SHUF; i++) {
        in.rv[i] = rv[i];
    }
    ctrl_step(&in, &g_ctrl, &out);
    for (i = 0u; i < (uint8_t)N_LEG; i++) {
        d[i] = out.d[i];
    }
}

void sil_supervisor_step(const float VM[N_MOD], const float IM[N_MOD], const float IL[N_LEG],
                         const float d[N_LEG], float en, float rv[N_SHUF], float *beta,
                         float *stress)
{
    sup_in_t in;
    sup_out_t out;
    uint8_t i;

    if (g_sup_ready == 0u) {
        sup_init(&g_sup);
        g_sup_ready = 1u;
    }
    for (i = 0u; i < (uint8_t)N_MOD; i++) {
        in.VM[i] = VM[i];
        in.IM[i] = IM[i];
    }
    for (i = 0u; i < (uint8_t)N_LEG; i++) {
        in.IL[i] = IL[i];
        in.d[i] = d[i];
    }
    in.en = en;
    sup_step(&in, &g_sup, &out);
    for (i = 0u; i < (uint8_t)N_SHUF; i++) {
        rv[i] = out.rv[i];
    }
    *beta = out.beta;
    *stress = out.stress;
}

void sil_recon_step(const float IL[N_LEG], const float d[N_LEG], float IM[N_MOD])
{
    recon_module_currents(IL, d, IM);
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
