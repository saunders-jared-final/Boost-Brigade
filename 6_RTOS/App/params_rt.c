/**
 * params_rt.c - run-time parameter table (see params_rt.h)
 */
#include "params_rt.h"

#include <math.h>
#include <string.h>

#include "app.h"
#include "sensors.h"
#include "shuffler_hw.h"
#include "shuffler_supervisor.h"

#ifndef CTRL_RUNTIME_GAINS
#error "params_rt.c needs CTRL_RUNTIME_GAINS (6_RTOS/CMakeLists.txt)"
#endif

/* params.h written by an older generator (MATLAB export_params.m) lacks these: derive them */
#ifndef CTRL_FC_LPF
#define CTRL_FC_LPF (CTRL_A / ((1.0f - CTRL_A) * 6.28318531f * CTRL_TS))
#endif

prt_t prt;
volatile uint32_t prt_vstr_pi_ms = 0U;
volatile uint16_t prt_pset = 0U;
volatile float prt_kscale_active = 1.0f;

static const float s_M0[N_Y][N_Y] = CTRL_M_INIT;
#ifndef CTRL_KP_RATIO_V
static const float s_Mp0[N_Y][N_Y] = CTRL_MP_INIT;
#endif

static ctrl_gains_t s_pending;
static float s_pending_k = 1.0f;
static volatile uint8_t s_swap = 0U;
static uint8_t s_dirty = 0U;

typedef struct {
  char name[12];
  float *p;
  float lo, hi, def;
  uint8_t cls;
  uint8_t hook;
} prm_t;

enum { H_NONE = 0, H_SUP, H_VREF, H_HALL, H_OC, H_VSTR_PI };

#define N_PRM_MAX 64
static prm_t s_tab[N_PRM_MAX];
static int s_n = 0;

static void add(const char *name, float *p, float lo, float hi, uint8_t cls, uint8_t hook)
{
  prm_t *e;
  if (s_n >= N_PRM_MAX) return;
  e = &s_tab[s_n++];
  strncpy(e->name, name, sizeof e->name - 1U);
  e->name[sizeof e->name - 1U] = '\0';
  e->p = p;
  e->lo = lo;
  e->hi = hi;
  e->def = *p;
  e->cls = cls;
  e->hook = hook;
}

static prm_t *find(const char *name)
{
  for (int i = 0; i < s_n; i++)
  {
    if (strcmp(s_tab[i].name, name) == 0) return &s_tab[i];
  }
  return NULL;
}

/* ---------------------------------------------------------------- hooks --- */
static void run_hook(const prm_t *e)
{
  int i;
  switch (e->hook)
  {
    case H_SUP:
      sup_rt.i_rated = prt.sup_i_rated;
      sup_rt.s_hi = prt.sup_s_hi;
      sup_rt.s_lo = prt.sup_s_lo;
      (void)app_req_sup_enable(prt.sup_en > 0.5f);
      break;
    case H_VREF:
    {
      const char *why;
      (void)app_req_vref(prt.vref, &why);   /* bounds already checked against the same SUP_RVMAX */
      break;
    }
    case H_HALL:
      for (i = 0; i < N_LEG; i++) Sensors_SetCal((Sense_Channel)i, prt.hall_mva[i], (int16_t)prt.hall_zero[i]);
      break;
    case H_OC:
      Sensors_SetOcLimit(prt.oc_a);
      break;
    case H_VSTR_PI:
      prt_vstr_pi_ms = app_ms() ? app_ms() : 1U;
      break;
    default:
      break;
  }
}

/* -------------------------------------------------------------- gain set --- */
/* In-place Gauss-Jordan with partial pivoting on a copy; false if (near) singular. */
static bool inv_n(const float A[N_Y][N_Y], float X[N_Y][N_Y])
{
  float a[N_Y][2 * N_Y];
  float amax = 0.0f;
  int i, j, k;
  for (i = 0; i < N_Y; i++)
  {
    for (j = 0; j < N_Y; j++)
    {
      a[i][j] = A[i][j];
      a[i][N_Y + j] = (i == j) ? 1.0f : 0.0f;
      if (fabsf(A[i][j]) > amax) amax = fabsf(A[i][j]);
    }
  }
  if (!(amax > 0.0f) || !isfinite(amax)) return false;
  for (k = 0; k < N_Y; k++)
  {
    int p = k;
    for (i = k + 1; i < N_Y; i++) if (fabsf(a[i][k]) > fabsf(a[p][k])) p = i;
    if (fabsf(a[p][k]) < 1e-6f * amax) return false;
    if (p != k)
    {
      for (j = 0; j < 2 * N_Y; j++) { float t = a[k][j]; a[k][j] = a[p][j]; a[p][j] = t; }
    }
    float piv = a[k][k];
    for (j = 0; j < 2 * N_Y; j++) a[k][j] /= piv;
    for (i = 0; i < N_Y; i++)
    {
      if (i == k) continue;
      float f = a[i][k];
      if (f == 0.0f) continue;
      for (j = 0; j < 2 * N_Y; j++) a[i][j] -= f * a[k][j];
    }
  }
  for (i = 0; i < N_Y; i++) for (j = 0; j < N_Y; j++) X[i][j] = a[i][N_Y + j];
  /* residual check */
  for (i = 0; i < N_Y; i++)
  {
    for (j = 0; j < N_Y; j++)
    {
      float s = 0.0f;
      for (k = 0; k < N_Y; k++) s += A[i][k] * X[k][j];
      if (fabsf(s - ((i == j) ? 1.0f : 0.0f)) > 1e-3f || !isfinite(s)) return false;
    }
  }
  return true;
}

static bool build_gains(ctrl_gains_t *g, const char **why)
{
  int i, j;
  float Me[N_Y][N_Y];
  if (prt.dmin >= prt.dmax) { *why = "dmin must be < dmax"; return false; }
  for (i = 0; i < N_Y; i++)
  {
    for (j = 0; j < N_Y; j++)
    {
      if (!isfinite(prt.M[i][j])) { *why = "M not finite"; return false; }
      Me[i][j] = prt.kscale * prt.M[i][j];
    }
  }
  if (!inv_n(Me, g->Minv)) { *why = "M singular or ill-conditioned"; return false; }
  for (i = 0; i < N_Y; i++)
  {
    for (j = 0; j < N_Y; j++)
    {
      float kp = (j < N_SHUF) ? prt.kp_v : prt.kp_i;
      g->M[i][j] = Me[i][j];
      g->Mp[i][j] = Me[i][j] * kp;
    }
  }
  {
    float w = 6.28318531f * prt.fc_lpf * CTRL_TS;
    g->a = w / (1.0f + w);
  }
  g->ma_n = (uint8_t)(prt.filt_ma + 0.5f);
  g->dmin = (prt.dmin < HW_DUTY_MIN) ? HW_DUTY_MIN : prt.dmin;
  g->dmax = (prt.dmax > HW_DUTY_MAX) ? HW_DUTY_MAX : prt.dmax;
  return true;
}

/* ------------------------------------------------------------------ init --- */
void prt_init(void)
{
  int i, j;
  char nm[12];

  prt.kscale = PRT_KSCALE_DEFAULT;
#ifdef CTRL_KP_RATIO_V
  prt.kp_v = CTRL_KP_RATIO_V;
  prt.kp_i = CTRL_KP_RATIO_I;
#else
  prt.kp_v = s_Mp0[0][0] / s_M0[0][0];
  prt.kp_i = s_Mp0[N_SHUF][N_SHUF] / s_M0[N_SHUF][N_SHUF];
#endif
  prt.fc_lpf = CTRL_FC_LPF;
  prt.filt_ma = 0.0f;
  prt.dmin = CTRL_DMIN;
  prt.dmax = CTRL_DMAX;
  memcpy(prt.M, s_M0, sizeof prt.M);
  prt.sup_en = 1.0f;
  prt.sup_i_rated = SUP_I_RATED;
  prt.sup_s_hi = SUP_S_HI;
  prt.sup_s_lo = SUP_S_LO;
  for (i = 0; i < N_SHUF; i++) prt.vref[i] = 0.0f;
  for (i = 0; i < N_LEG; i++)
  {
    prt.hall_mva[i] = Sensors_Cal_mVperA((Sense_Channel)i);
    prt.hall_zero[i] = (float)Sensors_Cal_Zero((Sense_Channel)i);
  }
  prt.oc_a = Sensors_OcLimit();
  prt.vm_ov = APP_VM_OV_V;
  prt.vm_uv = APP_VM_UV_V;
  prt.vstr_ov = APP_VSTR_OV_V;
  prt.vm1_src = (float)VM1_SRC_VSTR_PI;   /* U10 (CS3) is unreliable on the Version 0 board: VM1 = DL3021 readback - U11 */
  prt.vstr_param = 70.0f;
  prt.vstr_pi = 0.0f;
  prt.vm1_prot = 0.0f;
  prt.slew = APP_DUTY_SLEW;
  prt.wdg_s = APP_COMMS_WDG_S;

  s_n = 0;
  /* staged: the gain set */
  add("kscale", &prt.kscale, 0.05f, 1.0f, PRM_STAGED, H_NONE);
  add("kp_v", &prt.kp_v, 0.0f, 1e-2f, PRM_STAGED, H_NONE);
  add("kp_i", &prt.kp_i, 0.0f, 1e-2f, PRM_STAGED, H_NONE);
  add("fc_lpf", &prt.fc_lpf, 100.0f, 4000.0f, PRM_STAGED, H_NONE);
  add("filt_ma", &prt.filt_ma, 0.0f, (float)CTRL_MA_MAX, PRM_STAGED, H_NONE);
  add("dmin", &prt.dmin, HW_DUTY_MIN, 0.45f, PRM_STAGED, H_NONE);
  add("dmax", &prt.dmax, 0.55f, HW_DUTY_MAX, PRM_STAGED, H_NONE);
  for (i = 0; i < N_Y; i++)
  {
    for (j = 0; j < N_Y; j++)
    {
      nm[0] = 'm'; nm[1] = (char)('0' + i); nm[2] = (char)('0' + j); nm[3] = '\0';
      add(nm, &prt.M[i][j], -1000.0f, 1000.0f, PRM_STAGED, H_NONE);
    }
  }
  /* live */
  add("sup_en", &prt.sup_en, 0.0f, 1.0f, PRM_LIVE, H_SUP);
  add("sup_i_rated", &prt.sup_i_rated, 1.0f, 12.0f, PRM_LIVE, H_SUP);
  add("sup_s_hi", &prt.sup_s_hi, 0.3f, 1.0f, PRM_LIVE, H_SUP);
  add("sup_s_lo", &prt.sup_s_lo, 0.1f, 0.95f, PRM_LIVE, H_SUP);
  add("vref1", &prt.vref[0], -SUP_RVMAX, SUP_RVMAX, PRM_LIVE, H_VREF);
  add("vref2", &prt.vref[1], -SUP_RVMAX, SUP_RVMAX, PRM_LIVE, H_VREF);
  add("hall_mva0", &prt.hall_mva[0], -400.0f, 400.0f, PRM_LIVE, H_HALL);
  add("hall_mva1", &prt.hall_mva[1], -400.0f, 400.0f, PRM_LIVE, H_HALL);
  add("hall_mva2", &prt.hall_mva[2], -400.0f, 400.0f, PRM_LIVE, H_HALL);
  add("hall_mva3", &prt.hall_mva[3], -400.0f, 400.0f, PRM_LIVE, H_HALL);
  add("oc_a", &prt.oc_a, 0.5f, SENSE_OC_LIMIT_A, PRM_LIVE, H_OC);
  add("vm_ov", &prt.vm_ov, 5.0f, 32.0f, PRM_LIVE, H_NONE);
  add("vm_uv", &prt.vm_uv, 0.0f, 20.0f, PRM_LIVE, H_NONE);
  add("vstr_ov", &prt.vstr_ov, 10.0f, 96.0f, PRM_LIVE, H_NONE);
  add("vstr_param", &prt.vstr_param, 0.0f, 150.0f, PRM_LIVE, H_NONE);
  add("vstr_pi", &prt.vstr_pi, 0.0f, 150.0f, PRM_LIVE, H_VSTR_PI);
  add("vm1_prot", &prt.vm1_prot, 0.0f, 1.0f, PRM_LIVE, H_NONE);
  add("slew", &prt.slew, 0.0005f, 0.2f, PRM_LIVE, H_NONE);
  add("wdg_s", &prt.wdg_s, 0.0f, 60.0f, PRM_LIVE, H_NONE);
  /* idle only */
  add("hall_zero0", &prt.hall_zero[0], 1800.0f, 2300.0f, PRM_IDLE, H_HALL);
  add("hall_zero1", &prt.hall_zero[1], 1800.0f, 2300.0f, PRM_IDLE, H_HALL);
  add("hall_zero2", &prt.hall_zero[2], 1800.0f, 2300.0f, PRM_IDLE, H_HALL);
  add("hall_zero3", &prt.hall_zero[3], 1800.0f, 2300.0f, PRM_IDLE, H_HALL);
  add("vm1_src", &prt.vm1_src, 0.0f, 2.0f, PRM_IDLE, H_NONE);

  sup_rt.i_rated = prt.sup_i_rated;
  sup_rt.s_hi = prt.sup_s_hi;
  sup_rt.s_lo = prt.sup_s_lo;
  {
    const char *why;
    if (build_gains(&s_pending, &why))
    {
      ctrl_gains = s_pending;     /* not switching yet: load directly */
      prt_kscale_active = prt.kscale;
    }
  }
  s_dirty = 0U;
}

/* -------------------------------------------------------------- commands --- */
bool prt_set(const char *name, float v, bool running, const char **why)
{
  prm_t *e = find(name);
  if (!e) { *why = "unknown parameter"; return false; }
  if (!isfinite(v)) { *why = "not a number"; return false; }
  if (v < e->lo || v > e->hi) { *why = "out of range (C,LIST shows bounds)"; return false; }
  if (e->cls == PRM_IDLE && running) { *why = "stop first (idle-only parameter)"; return false; }
  if (e->hook == H_HALL && strncmp(name, "hall_mva", 8) == 0 && fabsf(v) < 10.0f) { *why = "|mV/A| must be >= 10"; return false; }
  if (strcmp(name, "vm1_src") == 0 || strcmp(name, "vm1_prot") == 0) v = floorf(v + 0.5f);
  *e->p = v;
  if (e->cls == PRM_STAGED) s_dirty = 1U;
  run_hook(e);
  return true;
}

bool prt_setm(const float *v, int n, const char **why)
{
  int i;
  if (n != N_Y * N_Y) { *why = "need 16 values (row-major M)"; return false; }
  for (i = 0; i < n; i++)
  {
    if (!isfinite(v[i]) || v[i] < -1000.0f || v[i] > 1000.0f) { *why = "M entry out of range (+-1000)"; return false; }
  }
  for (i = 0; i < n; i++) prt.M[i / N_Y][i % N_Y] = v[i];
  s_dirty = 1U;
  return true;
}

bool prt_get(const char *name, float *v)
{
  prm_t *e = find(name);
  if (!e) return false;
  *v = *e->p;
  return true;
}

bool prt_apply(const char **why)
{
  ctrl_gains_t g;
  if (s_swap) { *why = "previous apply still pending"; return false; }
  if (!build_gains(&g, why)) return false;
  __disable_irq();
  s_pending = g;
  s_pending_k = prt.kscale;
  s_swap = 1U;
  __enable_irq();
  s_dirty = 0U;
  return true;
}

bool prt_revert(bool running, const char **why)
{
  int i;
  if (running) { *why = "stop first (lower kscale + C,APPLY to back off while running)"; return false; }
  for (i = 0; i < s_n; i++)
  {
    *s_tab[i].p = s_tab[i].def;
  }
  for (i = 0; i < s_n; i++)
  {
    if (s_tab[i].hook != H_NONE && s_tab[i].hook != H_VSTR_PI) run_hook(&s_tab[i]);
  }
  prt_vstr_pi_ms = 0U;
  return prt_apply(why);
}

bool prt_staged_dirty(void)
{
  return s_dirty != 0U;
}

void prt_list(prt_list_cb cb)
{
  for (int i = 0; i < s_n; i++)
  {
    cb(s_tab[i].name, *s_tab[i].p, s_tab[i].lo, s_tab[i].hi, (prm_class_t)s_tab[i].cls);
  }
}

/* ------------------------------------------------------------------- ISR --- */
void prt_isr_service(ctrl_state_t *ctrl, const float d_applied[N_LEG])
{
  if (!s_swap) return;
  ctrl_gains = s_pending;
  ctrl_rebase(ctrl, d_applied);
  prt_kscale_active = s_pending_k;
  prt_pset++;
  s_swap = 0U;
}
