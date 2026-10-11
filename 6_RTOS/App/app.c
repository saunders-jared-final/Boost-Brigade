/**
 * app.c - shuffler application (see app.h)
 *
 * Safety path never depends on the scheduler: the over-current latch and the
 * E-stop disable the HRTIM outputs inside their interrupts; the state machine
 * only reports and gates re-enabling.
 */
#include "app.h"

#include <math.h>
#include <string.h>

#include "comms.h"
#include "ina2x9.h"
#include "main.h"
#include "sensors.h"
#include "shuffler_hw.h"
#include "stack.h"

#if N_LEG != HW_N_LEG
#error "control core N_LEG must match the four hardware legs"
#endif

/* ---------------------------------------------------------------- state --- */
static volatile app_state_t s_state = ST_BOOT;
static volatile app_mode_t  s_mode = MODE_IDLE;      /* requested / running mode */
static volatile uint32_t    s_faults = 0U;
static volatile uint32_t    s_ms = 0U;
static volatile uint32_t    s_state_since_ms = 0U;
static volatile uint8_t     s_cmd_enable = 0U;

static volatile float s_vm[N_MOD];
static volatile uint8_t s_vm_valid = 0U;
static volatile float s_tdie[3];
static float s_vm_isr[N_MOD];

static float s_ol_duty[N_LEG] = {0.5f, 0.5f, 0.5f, 0.5f};
static float s_vref[N_SHUF];
static uint8_t s_sup_en = 1U;

static stack_state_t s_stack;
static stack_out_t   s_stack_out;
static float s_d_applied[N_LEG] = {0.5f, 0.5f, 0.5f, 0.5f};
static float s_il[N_LEG];
static float s_imr[N_MOD];

static volatile uint8_t s_flag_1ms = 0U;
static uint32_t s_telemetry_div, s_safety_div, s_status_div;
static app_state_t s_last_reported = ST_BOOT;
static uint8_t s_fault_reported = 0U;

static const char *const s_state_names[] = {"BOOT", "SELFTEST", "IDLE", "SOFTSTART", "RUN", "STOP", "FAULT"};
static const char *const s_mode_names[]  = {"IDLE", "OL", "CL", "OL1", "CL1", "OL2", "CL2"};

const char *app_state_name(app_state_t s) { return (s <= ST_FAULT) ? s_state_names[s] : "?"; }
const char *app_mode_name(app_mode_t m)   { return (m < MODE_COUNT) ? s_mode_names[m] : "?"; }
uint32_t app_faults(void) { return s_faults; }

static uint8_t mode_legs(app_mode_t m)
{
  switch (m)
  {
    case MODE_OL: case MODE_CL:   return HW_LEGS_ALL;
    case MODE_OL1: case MODE_CL1: return HW_LEGS_S1;
    case MODE_OL2: case MODE_CL2: return HW_LEGS_S2;
    default: return 0U;
  }
}
static bool mode_closed(app_mode_t m) { return m == MODE_CL || m == MODE_CL1 || m == MODE_CL2; }

static void set_state(app_state_t s)
{
  s_state = s;
  s_state_since_ms = s_ms;
}

/* any context: outputs off, latch the fault, state FAULT */
static void trip(uint32_t code)
{
  hw_outputs_off();
  s_faults |= code;
  s_cmd_enable = 0U;
  set_state(ST_FAULT);
}

/* ------------------------------------------------------------- watchdog --- */
static void iwdg_start(void)
{
#if APP_USE_IWDG
  /* LSI ~32 kHz / 32 = 1 kHz; reload 2000 -> 2 s. LSI starts with the IWDG. */
  DBGMCU->APB1FZR1 |= DBGMCU_APB1FZR1_DBG_IWDG_STOP;   /* freeze while halted in the debugger */
  IWDG->KR  = 0xCCCCU;
  IWDG->KR  = 0x5555U;
  IWDG->PR  = 3U;        /* /32 */
  IWDG->RLR = 2000U;
  while (IWDG->SR != 0U) {}
  IWDG->KR  = 0xAAAAU;
#endif
}
static inline void iwdg_kick(void)
{
#if APP_USE_IWDG
  IWDG->KR = 0xAAAAU;
#endif
}

/* ---------------------------------------------------------------- estop --- */
#define ESTOP_GPIO_Port GPIOC
#define ESTOP_Pin       GPIO_PIN_0      /* CN7-38, active low, internal pull-up; button to GND */

static void estop_init(void)
{
  GPIO_InitTypeDef g = {0};
  __HAL_RCC_GPIOC_CLK_ENABLE();
  g.Pin = ESTOP_Pin;
  g.Mode = GPIO_MODE_IT_FALLING;
  g.Pull = GPIO_PULLUP;
  HAL_GPIO_Init(ESTOP_GPIO_Port, &g);
  HAL_NVIC_SetPriority(EXTI0_IRQn, 0, 0);
  HAL_NVIC_EnableIRQ(EXTI0_IRQn);
}
static bool estop_pressed(void)
{
  return HAL_GPIO_ReadPin(ESTOP_GPIO_Port, ESTOP_Pin) == GPIO_PIN_RESET;
}

void app_estop_isr(void)
{
  trip(FLT_ESTOP);
}

/* ----------------------------------------------------------------- init --- */
void app_init(void)
{
  uint32_t boot_faults = 0U;
  int i;

  if (RCC->CSR & RCC_CSR_IWDGRSTF) boot_faults |= FLT_WDG_RESET;
  RCC->CSR |= RCC_CSR_RMVF;

  for (i = 0; i < N_MOD; i++) { s_vm[i] = NAN; s_vm_isr[i] = 0.0f; s_imr[i] = 0.0f; }
  for (i = 0; i < N_SHUF; i++) s_vref[i] = 0.0f;
  stack_init(&s_stack);
  estop_init();

  set_state(ST_SELFTEST);
  comms_init();
  comms_banner();

  /* self test: sensor zero calibration plausibility, INA bus */
  for (i = 0; i < SENSE_COUNT; i++)
  {
    if (!Sensors_ZeroOk((Sense_Channel)i)) boot_faults |= FLT_ZEROCAL;
  }
  if (INA_BusBlocked()) boot_faults |= FLT_INA;
  app_task_sense_v();
  s_faults = boot_faults;
  set_state((boot_faults & (FLT_ZEROCAL | FLT_INA)) ? ST_FAULT : ST_IDLE);
  if (s_state == ST_FAULT) hw_outputs_off();
  comms_send_status();
  iwdg_start();
}

/* ------------------------------------------------------------ control --- */
/* 10 kHz, from the HRTIM master repetition interrupt */
void app_ctrl_isr(void)
{
  stack_in_t in;
  app_state_t st = s_state;
  app_mode_t  md = s_mode;
  uint8_t legs = mode_legs(md);
  int i;

  Sensors_Tick();                       /* reads last conversions, OC latch, starts next */
  for (i = 0; i < N_LEG; i++) s_il[i] = Sensors_Current_A((Sense_Channel)i);
  if (Sensors_FaultLatched() && !(s_faults & FLT_OC_LATCH))
  {
    trip(FLT_OC_LATCH);
    st = ST_FAULT;
  }

  /* module voltages: latest task snapshot (written at 1 kHz) */
  for (i = 0; i < N_MOD; i++) s_vm_isr[i] = (float)s_vm[i];

  if (st == ST_SOFTSTART)
  {
    for (i = 0; i < N_LEG; i++) s_d_applied[i] = 0.5f;
    stack_init(&s_stack);               /* closed loop starts fresh when RUN begins */
  }
  else if (st == ST_RUN && mode_closed(md))
  {
    for (i = 0; i < N_MOD; i++) in.VM[i] = isnan(s_vm_isr[i]) ? 0.0f : s_vm_isr[i];
    for (i = 0; i < N_LEG; i++) in.IL[i] = s_il[i];
    /* single-converter modes: blind the controller to the inactive shuffler
     * (zero its voltage-difference and current channels -> zero error) */
    if (!(legs & HW_LEGS_S1)) { in.VM[0] = in.VM[1]; in.IL[0] = 0.0f; in.IL[1] = 0.0f; }
    if (!(legs & HW_LEGS_S2)) { in.VM[2] = in.VM[1]; in.IL[2] = 0.0f; in.IL[3] = 0.0f; }
    for (i = 0; i < N_MOD; i++) in.IM[i] = 0.0f;   /* STACK_RECON_IM reconstructs these */
    in.Vstr = in.VM[0] + in.VM[1] + in.VM[2];
    in.Istr = 0.0f;
    for (i = 0; i < N_SHUF; i++) in.Vref[i] = s_vref[i];
    in.en_sup = s_sup_en ? 1.0f : 0.0f;
    in.en_mppt = 0.0f;                  /* the load (EcoFlow) does string MPPT */
    stack_step(&in, &s_stack, &s_stack_out);
    for (i = 0; i < N_LEG; i++) s_d_applied[i] = s_stack_out.d[i];
    for (i = 0; i < N_MOD; i++) s_imr[i] = s_stack_out.IM[i];
  }
  else if (st == ST_RUN)
  {
    for (i = 0; i < N_LEG; i++) s_d_applied[i] = s_ol_duty[i];
  }
  else
  {
    for (i = 0; i < N_LEG; i++) s_d_applied[i] = 0.5f;
  }
  for (i = 0; i < N_LEG; i++)
  {
    if (!(legs & (1U << i))) s_d_applied[i] = 0.5f;   /* inactive legs parked (outputs are off anyway) */
    hw_set_duty((uint8_t)i, s_d_applied[i]);
  }
}

/* ----------------------------------------------------------- 1 ms tick --- */
void app_tick_1ms(void)
{
  s_ms++;
  s_flag_1ms = 1U;
}

/* --------------------------------------------------------------- tasks --- */
void app_task_sense_v(void)
{
  float v[INA_COUNT];
  uint8_t ok = 0U, i;
  INA_Poll();
  for (i = 0; i < INA_COUNT; i++)
  {
    const INA_Dev *d = INA_Get(i);
    if (d->kind == INA_239 || d->kind == INA_229) { v[i] = (float)d->vbus_mV * 1e-3f; ok |= (uint8_t)(1U << i); s_tdie[i] = (float)d->temp_C; }
    else { v[i] = NAN; s_tdie[i] = NAN; }
  }
  /* index 0 = CS1 (U12, PV3+ to GND), 1 = CS2 (U11, PV2+ to GND), 2 = CS3 (U10, PV1+ to PV3+) */
  float vm3 = v[0];
  float vm2 = v[1] - v[0];
  float vm1 = v[2] - vm2;
  __disable_irq();
  s_vm[2] = vm3;  s_vm[1] = vm2;  s_vm[0] = vm1;
  s_vm_valid = (uint8_t)(((ok & 1U) ? 4U : 0U) | (((ok & 3U) == 3U) ? 2U : 0U) | (((ok & 7U) == 7U) ? 1U : 0U));
  __enable_irq();
}

static bool vm_ok_for(app_mode_t m)
{
  uint8_t need = 0U;
  if (!mode_closed(m)) return true;
  if (mode_legs(m) & HW_LEGS_S1) need |= 0x3U;   /* VM1, VM2 */
  if (mode_legs(m) & HW_LEGS_S2) need |= 0x6U;   /* VM2, VM3 */
  return (s_vm_valid & need) == need;
}

void app_task_safety(void)
{
  app_state_t st = s_state;
  int i;

  iwdg_kick();

  if (st == ST_RUN || st == ST_SOFTSTART)
  {
    if (estop_pressed()) trip(FLT_ESTOP);
    for (i = 0; i < N_MOD; i++)
    {
      float v = (float)s_vm[i];
      if (!isnan(v) && v > APP_VM_OV_V) { trip(FLT_OV); break; }
      if (!isnan(v) && v < APP_VM_UV_V && mode_closed(s_mode) && (s_vm_valid & (1U << i))) { trip(FLT_UV); break; }
    }
    for (i = 0; i < 3; i++)
    {
      if (!isnan((float)s_tdie[i]) && (float)s_tdie[i] > APP_TEMP_MAX_C) { trip(FLT_OVERTEMP); break; }
    }
    if (mode_closed(s_mode) && !vm_ok_for(s_mode)) trip(FLT_INA);
  }

  switch (s_state)
  {
    case ST_IDLE:
      if (s_cmd_enable && s_mode != MODE_IDLE)
      {
        for (i = 0; i < N_LEG; i++) hw_set_duty((uint8_t)i, 0.5f);
        hw_pins_to_hrtim();
        hw_legs_enable(mode_legs(s_mode));
        set_state(ST_SOFTSTART);
      }
      break;
    case ST_SOFTSTART:
      if (!s_cmd_enable) { set_state(ST_STOP); break; }
      if ((s_ms - s_state_since_ms) >= APP_SOFTSTART_MS) set_state(ST_RUN);
      break;
    case ST_RUN:
      if (!s_cmd_enable || s_mode == MODE_IDLE) set_state(ST_STOP);
      break;
    case ST_STOP:
      hw_legs_enable(0U);
      for (i = 0; i < N_LEG; i++) hw_set_duty((uint8_t)i, 0.5f);
      s_cmd_enable = 0U;
      set_state(ST_IDLE);
      break;
    case ST_FAULT:
      hw_outputs_off();   /* belt and braces, every 10 ms */
      break;
    default:
      break;
  }

  if (s_state != s_last_reported)
  {
    s_last_reported = s_state;
    comms_send_status();
  }
  if (s_state == ST_FAULT && !s_fault_reported)
  {
    s_fault_reported = 1U;
    comms_send_fault();
  }
}

void app_task_telemetry(void)
{
  comms_send_telemetry();
}

void app_task_cmd(void)
{
  comms_poll_rx();
}

void app_poll(void)
{
  if (!s_flag_1ms) return;
  s_flag_1ms = 0U;
  app_task_sense_v();
  if (++s_safety_div >= 10U)   { s_safety_div = 0U;   app_task_safety(); }
  if (++s_telemetry_div >= 20U){ s_telemetry_div = 0U; app_task_telemetry(); }
  if (++s_status_div >= 1000U) { s_status_div = 0U;    comms_send_status(); }
  app_task_cmd();
}

/* ------------------------------------------------------------ requests --- */
bool app_req_mode(app_mode_t m, const char **why)
{
  if (m >= MODE_COUNT) { *why = "bad mode"; return false; }
  if (s_state == ST_FAULT) { *why = "faulted, send C,CLEAR"; return false; }
  if (!vm_ok_for(m)) { *why = "module voltages not readable for this mode"; return false; }
  if (s_state == ST_RUN || s_state == ST_SOFTSTART)
  {
    /* live mode change: only between modes with the same legs; otherwise stop first */
    if (mode_legs(m) != mode_legs(s_mode)) { *why = "stop first (different legs)"; return false; }
    if (mode_closed(m) && !mode_closed(s_mode)) stack_init(&s_stack);
  }
  s_mode = m;
  if (m == MODE_IDLE) s_cmd_enable = 0U;
  return true;
}

bool app_req_enable(bool on, const char **why)
{
  if (on)
  {
    if (s_state == ST_FAULT) { *why = "faulted, send C,CLEAR"; return false; }
    if (s_mode == MODE_IDLE) { *why = "select a mode first"; return false; }
    if (estop_pressed()) { *why = "E-stop pressed"; return false; }
    if (!vm_ok_for(s_mode)) { *why = "module voltages not readable"; return false; }
    s_cmd_enable = 1U;
  }
  else
  {
    s_cmd_enable = 0U;
  }
  return true;
}

bool app_req_duty(uint8_t leg, float d, const char **why)
{
  if (leg >= N_LEG) { *why = "leg 0..3"; return false; }
  if (d < HW_DUTY_MIN || d > HW_DUTY_MAX) { *why = "duty out of range"; return false; }
  if (mode_closed(s_mode) && s_state == ST_RUN) { *why = "closed loop owns the duties"; return false; }
  s_ol_duty[leg] = d;
  return true;
}

bool app_req_vref(const float *rv, const char **why)
{
  int i;
  for (i = 0; i < N_SHUF; i++)
  {
    if (rv[i] < -SUP_RVMAX || rv[i] > SUP_RVMAX) { *why = "vref out of range"; return false; }
  }
  for (i = 0; i < N_SHUF; i++) s_vref[i] = rv[i];
  return true;
}

bool app_req_sup_enable(bool on)
{
  s_sup_en = on ? 1U : 0U;
  return true;
}

void app_req_soft_estop(void)
{
  trip(FLT_SOFT_ESTOP);
}

bool app_req_clear(const char **why)
{
  if (s_state != ST_FAULT) { *why = "not faulted"; return false; }
  if (estop_pressed()) { *why = "E-stop still pressed"; return false; }
  hw_outputs_off();
  Sensors_ClearFault();
  s_faults = 0U;
  s_fault_reported = 0U;
  s_cmd_enable = 0U;
  s_mode = MODE_IDLE;
  app_task_sense_v();
  if (INA_BusBlocked()) s_faults |= FLT_INA;
  set_state(ST_IDLE);
  return true;
}

void app_get_snapshot(app_snapshot_t *o)
{
  int i;
  __disable_irq();
  o->ms = s_ms;
  o->state = s_state;
  o->mode = s_mode;
  o->faults = s_faults;
  for (i = 0; i < N_MOD; i++) { o->VM[i] = (float)s_vm[i]; o->IMr[i] = s_imr[i]; }
  for (i = 0; i < N_LEG; i++) { o->IL[i] = s_il[i]; o->d[i] = s_d_applied[i]; }
  for (i = 0; i < N_SHUF; i++) o->rv[i] = s_stack_out.rv[i];
  o->beta = s_stack_out.beta;
  o->stress = s_stack_out.stress;
  for (i = 0; i < 3; i++) o->Tdie[i] = (float)s_tdie[i];
  o->vm_valid = s_vm_valid;
  o->legs = hw_legs_enabled();
  __enable_irq();
}
