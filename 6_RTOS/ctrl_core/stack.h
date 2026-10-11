/*
 * stack.h - full control stack scheduler (call stack_step() every CTRL_TS)
 *
 * Owns everything the Simulink model keeps OUTSIDE the three algorithm blocks:
 *   - the STACK_DECIM:1 decimation (controller at CTRL_TS; supervisor + MPPT
 *     at SUP_TS3),
 *   - supervisor-before-MPPT order within a slow tick,
 *   - the one-sample (SUP_TS3) unit delays on rv (IC = 0) and Iref (IC = IREF0),
 *   - the rv + Vref summation feeding the controller,
 *   - optionally (STACK_RECON_IM) the module-current reconstruction that
 *     replaces the unmeasured IM inputs on hardware.
 *
 * Timing model (matches Simulink single-tasking execution at shared steps):
 * ticks 0, DECIM, 2*DECIM, ... are the slow boundaries. At a boundary the
 * rv/Iref unit-delay OUTPUTS are latched first, then the controller runs,
 * then the supervisor (sampling the duties computed at this same tick), then
 * the MPPT, and finally the delays store this boundary's rv/Iref.
 *
 * Pure portable C99: no I/O, no allocation, float32 arithmetic only.
 */
#ifndef SHUFFLER_STACK_H
#define SHUFFLER_STACK_H

#include <stdint.h>

#include "params.h"
#include "shuffler_ctrl.h"
#include "shuffler_mppt.h"
#include "shuffler_supervisor.h"

/* 1 = supervisor samples the duties computed at the SAME boundary tick. */
#ifndef STACK_SUP_DUTY_SAME_TICK
#define STACK_SUP_DUTY_SAME_TICK 1
#endif

/* 1 = ignore in->IM and feed the supervisor reconstructed (relative) module
 *     currents from IL and the applied duties (hardware configuration).
 * 0 = use in->IM as given (Simulink plant / golden replay). */
#ifndef STACK_RECON_IM
#define STACK_RECON_IM 0
#endif

typedef struct {
    ctrl_state_t ctrl;
    sup_state_t sup;
    mppt_state_t mppt;
    uint8_t tick;           /* 0..STACK_DECIM-1 position within the slow frame */
    float rv_dly[N_SHUF];   /* rv unit-delay register (next boundary's output) */
    float iref_dly;         /* Iref unit-delay register */
    float rv_out[N_SHUF];   /* rv unit-delay output held for the current frame */
    float iref_out;         /* Iref unit-delay output held for the current frame */
    float d_last[N_LEG];    /* previous tick duties (STACK_SUP_DUTY_SAME_TICK=0) */
    /* slow-rate telemetry, updated at boundaries and held (ZOH) in between */
    float rv_now[N_SHUF];   /* supervisor raw rv (pre-delay) */
    float beta;
    float stress;
    float iref_raw;
    float pav;
    float mppt_state;
    float im_recon[N_MOD];  /* last reconstructed module currents (STACK_RECON_IM) */
} stack_state_t;

typedef struct {
    float VM[N_MOD];    /* module voltages [V] */
    float IM[N_MOD];    /* module currents [A] (ignored when STACK_RECON_IM) */
    float IL[N_LEG];    /* inductor currents {ILA1, ILB1, ILA2, ILB2, ...} [A] */
    float Vstr;         /* string voltage [V] */
    float Istr;         /* string current [A] (MPPT only) */
    float Vref[N_SHUF]; /* manual reference offsets summed onto the delayed rv */
    float en_sup;       /* supervisor enable */
    float en_mppt;      /* MPPT enable (0 on hardware: the load does string MPPT) */
} stack_in_t;

typedef struct {
    float d[N_LEG];     /* duties {dA1, dB1, dA2, dB2, ...}, every tick */
    float rv[N_SHUF];   /* supervisor raw rv (pre-delay), slow rate, held */
    float beta;
    float stress;
    float Iref;         /* MPPT raw Iref (pre-delay), held */
    float Iref_dly;     /* Iref after the unit delay (the load reference) */
    float Pav;
    float mppt_state;
    float IM[N_MOD];    /* module currents as seen by the supervisor (recon or input) */
} stack_out_t;

/* Reset the whole stack: module states, decimation phase, delay ICs. */
void stack_init(stack_state_t *state);

/* One CTRL_TS stack step (tick 0 immediately after stack_init() is t = 0). */
void stack_step(const stack_in_t *in, stack_state_t *state, stack_out_t *out);

#endif /* SHUFFLER_STACK_H */
