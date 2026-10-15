/**
 * app.h - shuffler application: state machine, control ISR, periodic tasks
 *
 * Scheduler-agnostic: app_init() once, app_ctrl_isr() from the HRTIM control
 * tick (10 kHz), app_tick_1ms() from SysTick, and the task functions from a
 * cooperative loop (app_poll()) or, later, from FreeRTOS threads with the
 * same periods.
 */
#ifndef APP_H
#define APP_H

#include <stdbool.h>
#include <stdint.h>

#include "params.h"   /* N_MOD / N_LEG from the shared control core */

typedef enum { ST_BOOT = 0, ST_SELFTEST, ST_IDLE, ST_SOFTSTART, ST_RUN, ST_STOP, ST_FAULT } app_state_t;
typedef enum { MODE_IDLE = 0, MODE_OL, MODE_CL, MODE_OL1, MODE_CL1, MODE_OL2, MODE_CL2, MODE_COUNT } app_mode_t;

/* fault bitmask (telemetry.md) */
#define FLT_OC_LATCH   0x001U
#define FLT_OC_HW      0x002U
#define FLT_ESTOP      0x004U
#define FLT_OV         0x008U
#define FLT_UV         0x010U
#define FLT_ZEROCAL    0x020U
#define FLT_INA        0x040U
#define FLT_OVERTEMP   0x080U
#define FLT_WDG_RESET  0x100U
#define FLT_SOFT_ESTOP 0x200U
#define FLT_STRING_OV  0x400U   /* sum of module voltages (or e-load readback) above vstr_ov */
#define FLT_COMMS_WDG  0x800U   /* closed loop with no command / C,PING for wdg_s seconds */
#define FLT_VSTR_STALE 0x1000U  /* vm1_src = VSTR_PI and the Pi stopped pushing vstr_pi (> 2 s) */

#define APP_SOFTSTART_MS   150U    /* duty ramp from the pre-bias d0 = Vbot/(Vtop+Vbot) to the mode's duty */
#define APP_VM_OV_V        30.0f   /* per-module over-voltage envelope */
#define APP_VM_UV_V        3.0f    /* per-module under-voltage while running */
#define APP_TEMP_MAX_C     85.0f   /* INA die / Pi-reported heatsink limit */
#define APP_VSTR_OV_V      85.0f   /* string over-voltage (3 x KAUSSP80 Voc = 75.2 V) */
#define APP_DUTY_SLEW      0.01f   /* closed-loop duty slew limit per 100 us tick */
#define APP_COMMS_WDG_S    5.0f    /* closed loop stops after this long without a command (0 = off) */
/* run-time values of the limits above live in params_rt (prt.*); these are the boot defaults */
#define APP_USE_IWDG       1

/* snapshot handed to telemetry (written by the ISR / tasks, copied with IRQs masked) */
typedef struct {
  uint32_t ms;
  app_state_t state;
  app_mode_t  mode;        /* running / requested mode */
  uint32_t    faults;
  float VM[N_MOD];         /* module voltages [V], NAN when not readable */
  float IL[N_LEG];         /* inductor currents [A] */
  float d[N_LEG];          /* applied duties */
  float rv[N_SHUF];
  float beta, stress;
  float IMr[N_MOD];        /* reconstructed module currents (relative) */
  float Tdie[3];           /* INA die temperatures [C] */
  uint8_t vm_valid;        /* bit k = VM[k] readable */
  uint8_t legs;            /* enabled legs mask */
  float kscale;            /* gain scale of the active controller gain set */
  uint16_t pset;           /* gain-set counter, +1 on every C,APPLY swap */
} app_snapshot_t;

void app_init(void);
void app_poll(void);                   /* cooperative loop body (never returns while superloop) */
void app_tick_1ms(void);               /* from SysTick */
void app_ctrl_isr(void);               /* from the HRTIM control tick */
void app_estop_isr(void);              /* from the E-stop EXTI */

/* periodic tasks (also callable from RTOS threads) */
void app_task_sense_v(void);           /* 1 kHz: INA239 round-robin -> VM */
void app_task_safety(void);            /* 100 Hz: envelopes, watchdog, state machine housekeeping */
void app_task_telemetry(void);         /* 50 Hz */
void app_task_cmd(void);               /* as fast as the loop: parse received lines */

/* requests from the command parser (return false + reason when refused) */
bool app_req_mode(app_mode_t m, const char **why);
/* Open-loop bench test cases (the Pi is not needed):
 *   0 = IC initialisation check (INA239 x3, hall sensors x4, E-stop, bus), no switching
 *   1 = bottom shuffler only (S2, legs 2-3)  -> MODE_OL2
 *   2 = top shuffler only    (S1, legs 0-1)  -> MODE_OL1
 *   3 = both shufflers                       -> MODE_OL
 * 1..3 only select the mode; switching starts with app_req_enable(true) (C,EN,1 or B1). */
bool app_req_test(int n, const char **why);
int  app_test_case(void);              /* last selected case, -1 = none */
bool app_req_enable(bool on, const char **why);
bool app_req_duty(uint8_t leg, float d, const char **why);
bool app_req_vref(const float *rv, const char **why);
bool app_req_sup_enable(bool on);
void app_req_soft_estop(void);
bool app_req_clear(const char **why);

void app_get_snapshot(app_snapshot_t *out);
uint32_t app_ms(void);
bool app_running(void);                /* SOFTSTART or RUN */
void app_note_rx(void);                /* a valid command line arrived (comms watchdog) */
const char *app_state_name(app_state_t s);
const char *app_mode_name(app_mode_t m);
uint32_t app_faults(void);

#endif /* APP_H */
