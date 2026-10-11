/*
 * shuffler_supervisor.h - supervisory feasibility governor (SUP_TS3 tick)
 *
 * C99 port of shuffler_string_supervisor.m, generalised to N_MOD: filters
 * module currents and differential shuffler currents, forms a stress index
 * from filtered |id| and duty excursion, integrates the governor gain beta
 * with hysteresis, and emits the voltage-difference relaxation references.
 *
 * Module currents may be ABSOLUTE (Simulink plant) or RELATIVE (hardware,
 * reconstructed by shuffler_recon.h up to a common offset): the deficit
 * dl = max(imf) - imf cancels any common offset.
 *
 * Pure portable C99: no I/O, no allocation, float32 arithmetic only.
 * Precondition: finite inputs (NaN handling differs from MATLAB's max()).
 */
#ifndef SHUFFLER_SUPERVISOR_H
#define SHUFFLER_SUPERVISOR_H

#include <stdint.h>

#include "params.h"

typedef struct {
    float b;            /* governor gain beta (MATLAB persistent b) */
    float imf[N_MOD];   /* filtered module currents (MATLAB persistent imf) */
    float idf[N_SHUF];  /* filtered differential currents (MATLAB persistent idf) */
    uint8_t seeded;     /* 0 until the first step seeds imf/idf from live inputs */
} sup_state_t;

typedef struct {
    float VM[N_MOD]; /* module voltages (unused by the reference algorithm) */
    float IM[N_MOD]; /* module currents IM1..IMn [A] (absolute or relative) */
    float IL[N_LEG]; /* inductor currents {ILA1, ILB1, ILA2, ILB2, ...} [A] */
    float d[N_LEG];  /* applied duties {dA1, dB1, dA2, dB2, ...} */
    float en;        /* enable; en == 0 resets state and zeroes outputs */
} sup_in_t;

typedef struct {
    float rv[N_SHUF]; /* relaxation references rv1.. [V], clamped to +/-RVMAX */
    float beta;       /* governor gain */
    float stress;     /* stress index (0 when en == 0) */
} sup_out_t;

/* Reset to the not-yet-seeded state; filters seed from inputs on the first step. */
void sup_init(sup_state_t *state);

/* One supervisor step (SUP_TS3). */
void sup_step(const sup_in_t *in, sup_state_t *state, sup_out_t *out);

#endif /* SHUFFLER_SUPERVISOR_H */
