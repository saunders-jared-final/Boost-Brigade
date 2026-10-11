/*
 * shuffler_mppt.h - adaptive-step P&O MPPT (1 ms tick, 20 ms perturb window)
 *
 * Bit-faithful C99 port of shuffler_string_mppt.m. Preserved reference quirks:
 *   - Pav is the PREVIOUS window's average power between window boundaries;
 *   - while en == 0, Pav is the instantaneous Vstr*Istr;
 *   - a beta change > BTOL between windows re-arms the boot perturb and holds
 *     iref for that window (state code 0);
 *   - the perturb window realigns to the re-enable instant after en == 0.
 *
 * Pure portable C99: no I/O, no allocation, float32 arithmetic only.
 */
#ifndef SHUFFLER_MPPT_H
#define SHUFFLER_MPPT_H

#include <stdint.h>

typedef struct {
    float iref;     /* string current reference (MATLAB persistent iref) */
    float dirn;     /* perturb direction, +1/-1 (MATLAB persistent dirn) */
    float Pprev;    /* previous window average power (MATLAB persistent Pprev) */
    float acc;      /* in-window power accumulator (MATLAB persistent acc) */
    uint8_t n;      /* in-window tick count (MATLAB persistent n) */
    uint8_t boot;   /* boot-perturb pending flag (MATLAB persistent boot) */
    float b0;       /* beta seen at the last window boundary (MATLAB persistent b0) */
    uint8_t st;     /* last state code: 0 hold, 1 perturb, 2 deadband (MATLAB persistent st) */
    uint8_t seeded; /* 0 until the first step seeds b0 from the live beta input,
                     * mirroring the MATLAB persistent-empty init */
} mppt_state_t;

typedef struct {
    float Vstr; /* string voltage [V] */
    float Istr; /* string current [A] */
    float beta; /* governor gain from the supervisor (same 1 ms tick) */
    float en;   /* enable; en == 0 resets state and outputs Iref = IREF0 */
} mppt_in_t;

typedef struct {
    float Iref;  /* string current reference [A], clamped to [IMIN, IMAX] */
    float Pav;   /* previous window average power [W] (Vstr*Istr while en == 0) */
    float state; /* state code 0/1/2 (float to mirror the Simulink signal) */
} mppt_out_t;

/* Reset to the not-yet-seeded state; b0 seeds from the beta input on the first step. */
void mppt_init(mppt_state_t *state);

/* One 1 ms MPPT step. */
void mppt_step(const mppt_in_t *in, mppt_state_t *state, mppt_out_t *out);

#endif /* SHUFFLER_MPPT_H */
