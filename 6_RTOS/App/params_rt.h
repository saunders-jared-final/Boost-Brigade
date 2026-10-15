/**
 * params_rt.h - run-time parameter table (C,SET / C,GET / C,LIST / C,APPLY / C,REVERT)
 *
 * Every tunable has a name, bounds, a default (params.h / app.h / sensors.h at
 * boot) and an apply class:
 *   LIVE   takes effect on the next use, any state
 *   IDLE   refused while switching (SOFTSTART / RUN)
 *   STAGED controller gain set: collected, validated and swapped on C,APPLY
 *          at a control-tick boundary, with a bumpless integrator rebase
 *          (ctrl_rebase: xi = Minv*u_act, so the duties do not jump)
 * Effective gains: M_eff = kscale*M, Mp = M_eff*diag(kp_v x N_SHUF, kp_i x N_SHUF),
 * Minv = inv(M_eff) computed on the MCU (Gauss-Jordan, partial pivoting,
 * rejected if singular or |M*Minv - I| > 1e-3). kscale scales the whole PI
 * (both P and I) and therefore the closed-loop bandwidth.
 */
#ifndef PARAMS_RT_H
#define PARAMS_RT_H

#include <stdbool.h>
#include <stdint.h>

#include "shuffler_ctrl.h"   /* params.h, ctrl_state_t */

typedef enum { PRM_LIVE = 0, PRM_IDLE = 1, PRM_STAGED = 2 } prm_class_t;

/* vm1_src: where VM1 (top module) comes from */
#define VM1_SRC_INA        0   /* U10 (CS3) - VM2 */
#define VM1_SRC_VSTR_PARAM 1   /* vstr_param - VM2 - VM3 (DL3021 in CV: its setpoint) */
#define VM1_SRC_VSTR_PI    2   /* vstr_pi - VM2 - VM3 (DL3021 readback pushed by the Pi) */

#define PRT_KSCALE_DEFAULT 0.3f    /* boot with 30 % of the identified gains */
#define PRT_VSTR_PI_STALE_MS 2000U

typedef struct {
  /* staged (C,APPLY) */
  float kscale, kp_v, kp_i, fc_lpf, dmin, dmax;
  float M[N_Y][N_Y];
  /* live */
  float sup_en, sup_i_rated, sup_s_hi, sup_s_lo;
  float vref[N_SHUF];
  float hall_mva[N_LEG];
  float oc_a, vm_ov, vm_uv, vstr_ov;
  float vstr_param, vstr_pi;
  float slew, wdg_s;
  /* idle-only */
  float hall_zero[N_LEG];
  float vm1_src;
} prt_t;

extern prt_t prt;                     /* current values (staged entries: the pending set) */
extern volatile uint32_t prt_vstr_pi_ms;   /* app_ms() when vstr_pi was last written, 0 = never */
extern volatile uint16_t prt_pset;    /* incremented on every gain swap; in every T frame */
extern volatile float prt_kscale_active;   /* kscale of the gain set the controller is using */

/* Boot: defaults from params.h and the drivers, compute and load the gain set. After Sensors_ZeroCal(). */
void prt_init(void);

/* Command back-ends. running = switching (SOFTSTART/RUN). Return false + reason when refused. */
bool prt_set(const char *name, float v, bool running, const char **why);
bool prt_setm(const float *v, int n, const char **why);    /* n = N_Y*N_Y row-major base M (staged) */
bool prt_get(const char *name, float *v);
bool prt_apply(const char **why);                          /* validate staged set, swap at next tick */
bool prt_revert(bool running, const char **why);           /* every parameter back to its boot default */
bool prt_staged_dirty(void);

/* C,LIST: one call per entry, in table order. */
typedef void (*prt_list_cb)(const char *name, float v, float lo, float hi, prm_class_t cls);
void prt_list(prt_list_cb cb);

/* Control ISR, at the start of every tick: performs a pending swap, then ctrl_rebase(ctrl, d). */
void prt_isr_service(ctrl_state_t *ctrl, const float d_applied[N_LEG]);

#endif /* PARAMS_RT_H */
