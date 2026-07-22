/*
 * stack.h - full control stack scheduler (call stack_step() every 50 us)
 *
 * Owns everything the Simulink model keeps OUTSIDE the three algorithm blocks:
 *   - the 20:1 decimation (controller at 50 us; supervisor + MPPT at 1 ms),
 *   - supervisor-before-MPPT order within a 1 ms tick (MPPT consumes the
 *     fresh beta from the same tick),
 *   - the one-sample (1 ms) unit delays on rv1..rv3 (IC = 0) and on Iref
 *     (IC = IREF0),
 *   - the rv1..rv3 + Vref1..Vref3 summation feeding the controller.
 *
 * Timing model (matches Simulink single-tasking execution at shared steps):
 * ticks 0, 20, 40, ... are the 1 ms boundaries. At a boundary the rv/Iref
 * unit-delay OUTPUTS are latched first (previous boundary's inputs), then the
 * controller runs, then the supervisor (sampling the duties computed at this
 * same tick - see STACK_SUP_DUTY_SAME_TICK), then the MPPT, and finally the
 * delays store this boundary's rv/Iref for the next one.
 *
 * Pure portable C99: no I/O, no allocation, float32 arithmetic only.
 */
#ifndef SHUFFLER_STACK_H
#define SHUFFLER_STACK_H

#include <stdint.h>

#include "shuffler_ctrl.h"
#include "shuffler_mppt.h"
#include "shuffler_supervisor.h"

/*
 * 1 = the supervisor samples the duties computed at the SAME 1 ms boundary
 *     tick (Simulink single-tasking sorted order with a direct / ZOH
 *     rate-transition duty path - the expected model wiring).
 * 0 = the supervisor samples the duties of the PREVIOUS 50 us tick (model has
 *     a delayed 1/z rate transition on the duty path). Flip only if golden
 *     replay shows beta/stress consistently off by one duty step.
 */
#ifndef STACK_SUP_DUTY_SAME_TICK
#define STACK_SUP_DUTY_SAME_TICK 1
#endif

typedef struct {
    ctrl_state_t ctrl;
    sup_state_t sup;
    mppt_state_t mppt;
    uint8_t tick;     /* 0..STACK_DECIM-1 position within the 1 ms frame */
    float rv_dly[3];  /* rv unit-delay register (next boundary's output) */
    float iref_dly;   /* Iref unit-delay register (next boundary's output) */
    float rv_out[3];  /* rv unit-delay output held for the current frame */
    float iref_out;   /* Iref unit-delay output held for the current frame */
    float d_last[6];  /* previous 50 us tick duties (STACK_SUP_DUTY_SAME_TICK=0) */
    /* slow-rate telemetry, updated at boundaries and held (ZOH) in between */
    float rv_now[3];  /* supervisor raw rv (pre-delay) */
    float beta;
    float stress;
    float iref_raw;   /* MPPT raw Iref (pre-delay) */
    float pav;
    float mppt_state;
} stack_state_t;

typedef struct {
    float VM[4];   /* module voltages VM1..VM4 [V] */
    float IM[4];   /* module currents IM1..IM4 [A] */
    float IL[6];   /* inductor currents {ILA1, ILB1, ILA2, ILB2, ILA3, ILB3} [A] */
    float Vstr;    /* string voltage [V] */
    float Istr;    /* string current [A] */
    float Vref[3]; /* manual reference offsets summed onto the delayed rv */
    float en_sup;  /* supervisor enable (model default 1) */
    float en_mppt; /* MPPT enable (model default 1) */
} stack_in_t;

typedef struct {
    float d[6];       /* duties {dA1, dB1, dA2, dB2, dA3, dB3}, every tick */
    float rv[3];      /* supervisor raw rv1..rv3 (pre-delay), 1 ms rate, held */
    float beta;       /* supervisor beta, held */
    float stress;     /* supervisor stress, held */
    float Iref;       /* MPPT raw Iref (pre-delay), held */
    float Iref_dly;   /* Iref after the 1 ms unit delay (the load reference) */
    float Pav;        /* MPPT Pav, held */
    float mppt_state; /* MPPT state code, held */
} stack_out_t;

/* Reset the whole stack: module states, decimation phase, delay ICs. */
void stack_init(stack_state_t *state);

/* One 50 us stack step (tick 0 immediately after stack_init() is t = 0). */
void stack_step(const stack_in_t *in, stack_state_t *state, stack_out_t *out);

#endif /* SHUFFLER_STACK_H */
