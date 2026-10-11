/*
 * shuffler_supervisor.h - supervisory feasibility governor (1 ms tick)
 *
 * Bit-faithful C99 port of shuffler_string_supervisor.m: filters module
 * currents and differential shuffler currents, forms a stress index from
 * filtered |id| and duty excursion, integrates the governor gain beta with
 * hysteresis, and emits the voltage-difference relaxation references rv1..rv3.
 *
 * Pure portable C99: no I/O, no allocation, float32 arithmetic only.
 *
 * Precondition: finite inputs. The vector max reductions here keep a NaN once
 * it lands in the accumulator, where MATLAB's max() omits NaN - with a NaN
 * measurement input the two implementations diverge (C can emit rv = -RVMAX).
 * The clamped controller duties can never produce NaN; only a broken
 * plant/sensor feed could, and that case is out of the fidelity contract.
 */
#ifndef SHUFFLER_SUPERVISOR_H
#define SHUFFLER_SUPERVISOR_H

#include <stdint.h>

typedef struct {
    float b;        /* governor gain beta (MATLAB persistent b) */
    float imf[4];   /* filtered module currents (MATLAB persistent imf) */
    float idf[3];   /* filtered differential currents (MATLAB persistent idf) */
    uint8_t seeded; /* 0 until the first step seeds imf/idf from live inputs,
                     * mirroring the MATLAB persistent-empty init */
} sup_state_t;

typedef struct {
    float VM[4]; /* module voltages VM1..VM4 [V] (unused by the reference
                  * algorithm - kept for signature fidelity) */
    float IM[4]; /* module currents IM1..IM4 [A] */
    float IL[6]; /* inductor currents {ILA1, ILB1, ILA2, ILB2, ILA3, ILB3} [A] */
    float d[6];  /* applied duties {dA1, dB1, dA2, dB2, dA3, dB3} */
    float en;    /* enable; en == 0 resets state and zeroes outputs */
} sup_in_t;

typedef struct {
    float rv[3];  /* relaxation references rv1..rv3 [V], clamped to +/-RVMAX */
    float beta;   /* governor gain */
    float stress; /* stress index (0 when en == 0) */
} sup_out_t;

/* Reset to the not-yet-seeded state; filters seed from inputs on the first step. */
void sup_init(sup_state_t *state);

/* One 1 ms supervisor step. */
void sup_step(const sup_in_t *in, sup_state_t *state, sup_out_t *out);

#endif /* SHUFFLER_SUPERVISOR_H */
