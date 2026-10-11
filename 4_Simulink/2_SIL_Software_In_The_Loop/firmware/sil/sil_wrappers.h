/*
 * sil_wrappers.h - flat entry points for Simulink C Caller blocks (SIL)
 *
 * One entry point per algorithm block, array ports sized by params.h
 * (N_MOD / N_SHUF / N_LEG). State is held in file statics - single instance
 * per function, exactly like MATLAB persistent variables.
 *
 * These wrappers implement ONLY the algorithm blocks. The rv/Iref unit delays
 * and the Vref summation stay in the Simulink model for SIL (they are
 * replicated in core/stack.c for standalone use only).
 *
 * sil_reset() clears all states; the next step of each block re-seeds from
 * its live inputs. Call it from an Initialize Function block (INSTRUCTIONS.md).
 */
#ifndef SIL_WRAPPERS_H
#define SIL_WRAPPERS_H

#include "params.h"

/* Inner controller, CTRL_TS tick: d = shuffler_string_ctrl(VM, IL, rv) */
void sil_ctrl_step(const float VM[N_MOD], const float IL[N_LEG], const float rv[N_SHUF],
                   float d[N_LEG]);

/* Supervisor, SUP_TS3 tick: [rv,beta,stress] = shuffler_string_supervisor(VM, IM, IL, d, en) */
void sil_supervisor_step(const float VM[N_MOD], const float IM[N_MOD], const float IL[N_LEG],
                         const float d[N_LEG], float en, float rv[N_SHUF], float *beta,
                         float *stress);

/* Module-current reconstruction (stateless): IM_rel = recon(IL, d), IM_rel[N_MOD-1] = 0 */
void sil_recon_step(const float IL[N_LEG], const float d[N_LEG], float IM[N_MOD]);

/* MPPT, SUP_TS3 tick: [Iref,Pav,state] = shuffler_string_mppt(Vstr, Istr, beta, en) */
void sil_mppt_step(float Vstr, float Istr, float beta, float en, float *Iref, float *Pav,
                   float *state);

/* Reset all block states (re-seed on next step). */
void sil_reset(void);

/* sil_reset() variant for an Initialize Function subsystem: resets, passes u through. */
float sil_reset_pass(float u);

#endif /* SIL_WRAPPERS_H */
