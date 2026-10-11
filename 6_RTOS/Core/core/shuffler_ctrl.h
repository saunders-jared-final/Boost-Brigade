/*
 * shuffler_ctrl.h - inner MIMO duty controller (50 us tick)
 *
 * Bit-faithful C99 port of shuffler_string_ctrl.m: decoupling-PI on the three
 * module-voltage differences and three common-mode shuffler currents, with the
 * anti-windup integrator recompute through Minv every step (as in the MATLAB
 * reference - do not "optimise" it away).
 *
 * Pure portable C99: no I/O, no allocation, float32 arithmetic only.
 */
#ifndef SHUFFLER_CTRL_H
#define SHUFFLER_CTRL_H

#include <stdint.h>

/*
 * MAT_CONST / MAT_RD: declaration and element-read hooks for the constant
 * matrices, so a later AVR build can move them to flash without touching the
 * algorithm code. PROGMEM/pgm_read_float live in <avr/pgmspace.h>, which this
 * portable header must not include - the AVR build supplies it alongside the
 * overrides:
 *     -include avr/pgmspace.h
 *     -DMAT_CONST='static const PROGMEM float'
 *     -DMAT_RD(m,r,c)='pgm_read_float(&(m)[r][c])'
 */
#ifndef MAT_CONST
#define MAT_CONST static const float
#endif
#ifndef MAT_RD
#define MAT_RD(m, r, c) ((m)[r][c])
#endif

/*
 * Integrator accumulator type - escape hatch for design rule 6 (float32
 * stagnation of xi += Ts*e at the 24-bit mantissa limit). Default is float so
 * SIL and AVR PIL compute identically. ONLY if golden-vector replay shows
 * drift/stagnation, build host/ARM with -DSHUF_ACCUM_DOUBLE and document the
 * deviation (AVR stays float either way: its double is 32-bit).
 */
#ifdef SHUF_ACCUM_DOUBLE
typedef double ctrl_accum_t;
#else
typedef float ctrl_accum_t;
#endif

typedef struct {
    ctrl_accum_t xi[6]; /* integrator state (MATLAB persistent xi) */
    float y_f[6];       /* filtered measurement vector (MATLAB persistent y_f) */
} ctrl_state_t;

typedef struct {
    float VM[4]; /* module voltages VM1..VM4 [V] */
    float IL[6]; /* inductor currents {ILA1, ILB1, ILA2, ILB2, ILA3, ILB3} [A] */
    float rv[3]; /* voltage-difference references rv1..rv3 [V] */
} ctrl_in_t;

typedef struct {
    float d[6]; /* duty cycles {dA1, dB1, dA2, dB2, dA3, dB3}, clamped to [0.05, 0.95] */
} ctrl_out_t;

/* Zero the controller state (equivalent to the MATLAB persistent-empty init). */
void ctrl_init(ctrl_state_t *state);

/* One 50 us control step. */
void ctrl_step(const ctrl_in_t *in, ctrl_state_t *state, ctrl_out_t *out);

#endif /* SHUFFLER_CTRL_H */
