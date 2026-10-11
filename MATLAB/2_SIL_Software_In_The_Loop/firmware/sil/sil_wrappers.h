/*
 * sil_wrappers.h - flat entry points for Simulink C Caller blocks (SIL)
 *
 * One entry point per MATLAB Function block, with the block's exact port
 * signature (arrays + scalars only). State is held in file statics - single
 * instance per function, exactly like MATLAB persistent variables.
 *
 * These wrappers implement ONLY the three algorithm blocks. The rv/Iref unit
 * delays and the Vref summation stay in the Simulink model for SIL (they are
 * replicated in core/stack.c for standalone use only).
 *
 * sil_reset() clears all three states; the next step of each block re-seeds
 * from its live inputs (the MATLAB 'clear functions' equivalent). Call it at
 * simulation start - see INSTRUCTIONS.md.
 */
#ifndef SIL_WRAPPERS_H
#define SIL_WRAPPERS_H

/* Inner controller, 50 us tick. Mirrors:
 * [dA1,dB1,dA2,dB2,dA3,dB3] = shuffler_string_ctrl(VM, IL, rv) */
void sil_ctrl_step(const float VM[4], const float IL[6], const float rv[3], float *dA1,
                   float *dB1, float *dA2, float *dB2, float *dA3, float *dB3);

/* Supervisor / feasibility governor, 1 ms tick. Mirrors:
 * [rv1,rv2,rv3,beta,stress] = shuffler_string_supervisor(VM, IM, IL,
 *     dA1,dB1,dA2,dB2,dA3,dB3, en) */
void sil_supervisor_step(const float VM[4], const float IM[4], const float IL[6], float dA1,
                         float dB1, float dA2, float dB2, float dA3, float dB3, float en,
                         float *rv1, float *rv2, float *rv3, float *beta, float *stress);

/* MPPT, 1 ms tick. Mirrors:
 * [Iref,Pav,state] = shuffler_string_mppt(Vstr, Istr, beta, en) */
void sil_mppt_step(float Vstr, float Istr, float beta, float en, float *Iref, float *Pav,
                   float *state);

/* Reset all three block states (re-seed on next step). */
void sil_reset(void);

/* sil_reset() variant usable where Simulink needs a ported block (e.g. inside
 * an Initialize Function subsystem): resets everything, passes u through. */
float sil_reset_pass(float u);

#endif /* SIL_WRAPPERS_H */
