/*
 * shuffler_ctrl.h - inner MIMO duty controller (CTRL_TS tick)
 *
 * C99 port of shuffler_string_ctrl.m, generalised to N_MOD modules /
 * N_SHUF shufflers (params.h): decoupling-PI on the N_SHUF module-voltage
 * differences and N_SHUF common-mode shuffler currents, with the anti-windup
 * integrator recompute through Minv every step (as in the MATLAB reference -
 * do not "optimise" it away).
 *
 * Pure portable C99: no I/O, no allocation, float32 arithmetic only.
 */
#ifndef SHUFFLER_CTRL_H
#define SHUFFLER_CTRL_H

#include <stdint.h>

#include "params.h"

/*
 * MAT_CONST / MAT_RD: declaration and element-read hooks for the constant
 * matrices, so a flash-resident build (AVR PROGMEM) can be made without
 * touching the algorithm code.
 */
#ifndef MAT_CONST
#define MAT_CONST static const float
#endif
#ifndef MAT_RD
#define MAT_RD(m, r, c) ((m)[r][c])
#endif

/*
 * Integrator accumulator type - escape hatch for float32 stagnation of
 * xi += Ts*e at the 24-bit mantissa limit. Default float so SIL, QSPICE DLL
 * and firmware compute identically; measured drift is well inside the gates.
 */
#ifdef SHUF_ACCUM_DOUBLE
typedef double ctrl_accum_t;
#else
typedef float ctrl_accum_t;
#endif

typedef struct {
    ctrl_accum_t xi[N_Y]; /* integrator state (MATLAB persistent xi) */
    float y_f[N_Y];       /* filtered measurement vector (MATLAB persistent y_f) */
} ctrl_state_t;

typedef struct {
    float VM[N_MOD];  /* module voltages VM1..VMn [V] */
    float IL[N_LEG];  /* inductor currents {ILA1, ILB1, ILA2, ILB2, ...} [A] */
    float rv[N_SHUF]; /* voltage-difference references rv1..rv(n-1) [V] */
} ctrl_in_t;

typedef struct {
    float d[N_LEG]; /* duty cycles {dA1, dB1, dA2, dB2, ...}, clamped to [DMIN, DMAX] */
} ctrl_out_t;

#ifdef CTRL_RUNTIME_GAINS
/*
 * Firmware-only: the gain set lives in RAM so it can be changed at run time
 * (6_RTOS/App/params_rt.c). Initialised from params.h, so a build that never
 * writes it computes exactly what the const build computes. Writers swap the
 * whole set between two ctrl_step() calls and then call ctrl_rebase().
 */
typedef struct {
    float M[N_Y][N_Y];
    float Mp[N_Y][N_Y];
    float Minv[N_Y][N_Y];
    float a;     /* measurement LPF coefficient (CTRL_A) */
    float dmin;  /* duty clamp (CTRL_DMIN / CTRL_DMAX) */
    float dmax;
} ctrl_gains_t;

extern ctrl_gains_t ctrl_gains;

/* Bumpless re-initialisation after a gain swap: integrator state set so that,
 * at zero error, the controller reproduces the duties d currently applied
 * (xi = Minv * u_act, the anti-windup relation with e = 0). */
void ctrl_rebase(ctrl_state_t *state, const float d[N_LEG]);
#endif

/* Zero the controller state (equivalent to the MATLAB persistent-empty init). */
void ctrl_init(ctrl_state_t *state);

/* One control step (CTRL_TS). */
void ctrl_step(const ctrl_in_t *in, ctrl_state_t *state, ctrl_out_t *out);

#endif /* SHUFFLER_CTRL_H */
