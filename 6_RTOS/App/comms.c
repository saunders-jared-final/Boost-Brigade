/**
 * comms.c - telemetry frames and command parser (see 0_Documentation/telemetry.md)
 *
 * TX is blocking on the BSP COM UART (a 170-byte frame is ~1.8 ms at 921600
 * baud, 50 Hz -> ~9 % of the main loop). RX is one byte per interrupt into a
 * ring buffer; lines are parsed in the main loop.
 */
#include "comms.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "app.h"
#include "ina2x9.h"
#include "main.h"
#include "params_rt.h"
#include "sensors.h"
#include "shuffler_hw.h"

#define RX_RING 512
#define LINE_MAX 256   /* C,SETM carries 16 floats */
#define MAX_FIELDS 24

static volatile uint8_t s_ring[RX_RING];
static volatile uint16_t s_head, s_tail;
static uint8_t s_rx_byte;
static char s_line[LINE_MAX];
static uint16_t s_line_len;

/* newlib-nano printf has no float support: format to 4 significant-ish digits */
static char *fmt_f(char *buf, float x)
{
  if (isnan(x)) { strcpy(buf, "nan"); return buf; }
  float a = fabsf(x);
  int32_t scaled;
  if (a < 10.0f)       { scaled = (int32_t)(a * 1000.0f + 0.5f); snprintf(buf, 16, "%s%ld.%03ld", x < 0 ? "-" : "", (long)(scaled / 1000), (long)(scaled % 1000)); }
  else if (a < 100.0f) { scaled = (int32_t)(a * 100.0f + 0.5f);  snprintf(buf, 16, "%s%ld.%02ld", x < 0 ? "-" : "", (long)(scaled / 100), (long)(scaled % 100)); }
  else                 { scaled = (int32_t)(a * 10.0f + 0.5f);   snprintf(buf, 16, "%s%ld.%01ld", x < 0 ? "-" : "", (long)(scaled / 10), (long)(scaled % 10)); }
  return buf;
}

char *comms_fmt(char *buf, float x) { return fmt_f(buf, x); }

/* 6 significant digits with exponent (C,GET / C,LIST): -2.52252e+01. buf >= 24 bytes. */
static char *fmt_g6(char *buf, float x)
{
  int e = 0;
  float a;
  int32_t m;
  if (isnan(x)) { strcpy(buf, "nan"); return buf; }
  if (isinf(x)) { strcpy(buf, x < 0 ? "-inf" : "inf"); return buf; }
  if (x == 0.0f) { strcpy(buf, "0"); return buf; }
  a = fabsf(x);
  while (a >= 10.0f) { a *= 0.1f; e++; }
  while (a < 1.0f)   { a *= 10.0f; e--; }
  m = (int32_t)(a * 100000.0f + 0.5f);
  if (m >= 1000000) { m /= 10; e++; }
  if (e > 99) e = 99;
  if (e < -99) e = -99;
  snprintf(buf, 24, "%s%ld.%05lde%c%02d", x < 0 ? "-" : "", (long)(m / 100000), (long)(m % 100000), e < 0 ? '-' : '+',
           (int)(e < 0 ? -e : e));
  return buf;
}

static void tx(const char *s)
{
  (void)HAL_UART_Transmit(&hcom_uart[COM1], (const uint8_t *)s, (uint16_t)strlen(s), 100);
}

void comms_note(const char *line)
{
  tx("# ");
  tx(line);
  tx("\r\n");
}

void comms_init(void)
{
  s_head = s_tail = 0U;
  s_line_len = 0U;
  HAL_NVIC_SetPriority(LPUART1_IRQn, 6, 0);
  HAL_NVIC_EnableIRQ(LPUART1_IRQn);
  (void)HAL_UART_Receive_IT(&hcom_uart[COM1], &s_rx_byte, 1);
}

void comms_rx_irq_byte(uint8_t b)
{
  uint16_t next = (uint16_t)((s_head + 1U) % RX_RING);
  if (next != s_tail) { s_ring[s_head] = b; s_head = next; }
}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
  if (huart == &hcom_uart[COM1])
  {
    comms_rx_irq_byte(s_rx_byte);
    (void)HAL_UART_Receive_IT(&hcom_uart[COM1], &s_rx_byte, 1);
  }
}

void HAL_UART_ErrorCallback(UART_HandleTypeDef *huart)
{
  if (huart == &hcom_uart[COM1])
  {
    (void)HAL_UART_Receive_IT(&hcom_uart[COM1], &s_rx_byte, 1);
  }
}

void comms_banner(void)
{
  char b[160];
  snprintf(b, sizeof b, "\r\n# %s params=%s N_MOD=%d Ts=%gus pwm=%luHz proto=%d\r\n", COMMS_FW_VERSION, PARAMS_VERSION,
           (int)N_MOD, (double)CTRL_TS * 1e6, (unsigned long)HW_PWM_HZ, COMMS_PROTOCOL_VERSION);
  tx(b);
  for (uint8_t i = 0; i < INA_COUNT; i++)
  {
    const INA_Dev *d = INA_Get(i);
    snprintf(b, sizeof b, "# INA CS%u: %s (MFR 0x%04X, DEV 0x%04X)\r\n", (unsigned)(i + 1U), INA_KindName(d->kind),
             (unsigned)d->mfr_id, (unsigned)d->dev_id);
    tx(b);
  }
  if (INA_BusBlocked()) tx("# WARNING: SPI bus held by the U13 isolator (reversed channels): INA read-out disabled\r\n");
  for (int ch = 0; ch < SENSE_COUNT; ch++)
  {
    snprintf(b, sizeof b, "# hall %s: gain %d mV/A zero-cal %s\r\n", Sensors_Name((Sense_Channel)ch),
             (int)Sensors_Cal_mVperA((Sense_Channel)ch), Sensors_ZeroOk((Sense_Channel)ch) ? "ok" : "IMPLAUSIBLE");
    tx(b);
  }
}

void comms_send_telemetry(void)
{
  app_snapshot_t s;
  char b[256], f[16];
  int n, i;
  app_get_snapshot(&s);
  n = snprintf(b, sizeof b, "T,%lu,%s", (unsigned long)s.ms,
               (s.state == ST_RUN) ? "" : app_state_name(s.state));
  if (s.state == ST_RUN) n += snprintf(b + n, sizeof b - (size_t)n, "RUN_%s", app_mode_name(s.mode));
  n += snprintf(b + n, sizeof b - (size_t)n, ",%lx", (unsigned long)s.faults);
  for (i = 0; i < N_MOD; i++) n += snprintf(b + n, sizeof b - (size_t)n, ",%s", fmt_f(f, s.VM[i]));
  for (i = 0; i < N_LEG; i++) n += snprintf(b + n, sizeof b - (size_t)n, ",%s", fmt_f(f, s.IL[i]));
  for (i = 0; i < N_LEG; i++) n += snprintf(b + n, sizeof b - (size_t)n, ",%s", fmt_f(f, s.d[i]));
  for (i = 0; i < N_SHUF; i++) n += snprintf(b + n, sizeof b - (size_t)n, ",%s", fmt_f(f, s.rv[i]));
  n += snprintf(b + n, sizeof b - (size_t)n, ",%s", fmt_f(f, s.beta));
  n += snprintf(b + n, sizeof b - (size_t)n, ",%s", fmt_f(f, s.stress));
  for (i = 0; i < N_MOD - 1; i++) n += snprintf(b + n, sizeof b - (size_t)n, ",%s", fmt_f(f, s.IMr[i]));
  for (i = 0; i < 3; i++) n += snprintf(b + n, sizeof b - (size_t)n, ",%s", fmt_f(f, s.Tdie[i]));
  n += snprintf(b + n, sizeof b - (size_t)n, ",%s,%u", fmt_f(f, s.kscale), (unsigned)s.pset);
  n += snprintf(b + n, sizeof b - (size_t)n, ",%s\n", PARAMS_VERSION);
  (void)n;
  tx(b);
}

void comms_send_status(void)
{
  app_snapshot_t s;
  char b[128];
  app_get_snapshot(&s);
  snprintf(b, sizeof b, "S,%lu,%s,%lx,%s,%s,%s\n", (unsigned long)s.ms, app_state_name(s.state),
           (unsigned long)s.faults, app_mode_name(s.mode), COMMS_FW_VERSION, PARAMS_VERSION);
  tx(b);
}

void comms_send_fault(void)
{
  char b[128], f[16];
  uint32_t ms = 0U;
  const char *vm_name = "-";
  float vm_v = 0.0f;
  app_snapshot_t s;
  app_get_snapshot(&s);
  ms = s.ms;
  if (s.faults & FLT_OC_LATCH)
  {
    snprintf(b, sizeof b, "F,%lu,%lx,%s,%s,%u\n", (unsigned long)ms, (unsigned long)s.faults,
             Sensors_Name(Sensors_FaultChannel()), fmt_f(f, Sensors_FaultCurrent_A()), (unsigned)Sensors_FaultRaw());
  }
  else if ((s.faults & (FLT_OV | FLT_UV | FLT_STRING_OV)) && app_fault_vm(&vm_name, &vm_v))
  {
    snprintf(b, sizeof b, "F,%lu,%lx,%s,%s,0\n", (unsigned long)ms, (unsigned long)s.faults, vm_name, fmt_f(f, vm_v));
  }
  else
  {
    snprintf(b, sizeof b, "F,%lu,%lx,-,0,0\n", (unsigned long)ms, (unsigned long)s.faults);
  }
  tx(b);
}

/* ------------------------------------------------------------- commands --- */
static void answer(const char *cmd, int ok, const char *why)
{
  char b[128];
  snprintf(b, sizeof b, "A,%s,%s,%s\n", cmd, ok ? "OK" : "ERR", why ? why : "");
  tx(b);
}

static int split(char *line, char **f, int maxf)
{
  int n = 0;
  char *p = line;
  while (n < maxf && p)
  {
    f[n++] = p;
    p = strchr(p, ',');
    if (p) *p++ = '\0';
  }
  return n;
}

static void list_cb(const char *name, float v, float lo, float hi, prm_class_t cls)
{
  static const char *const cn[] = {"LIVE", "IDLE", "STAGED"};
  char b[112], fv[24], fl[24], fh[24];
  snprintf(b, sizeof b, "P,%s,%s,%s,%s,%s\n", name, fmt_g6(fv, v), fmt_g6(fl, lo), fmt_g6(fh, hi), cn[cls]);
  tx(b);
}

static void handle_line(char *line)
{
  char *f[MAX_FIELDS];
  int n = split(line, f, MAX_FIELDS);
  const char *why = NULL;
  if (n < 2 || strcmp(f[0], "C") != 0) { answer("?", 0, "expected C,<cmd>,..."); return; }
  const char *cmd = f[1];
  app_note_rx();   /* any well-formed command feeds the closed-loop comms watchdog */
  if (strcmp(cmd, "MODE") == 0 && n >= 3)
  {
    app_mode_t m = MODE_COUNT;
    for (int k = 0; k < MODE_COUNT; k++) if (strcmp(f[2], app_mode_name((app_mode_t)k)) == 0) m = (app_mode_t)k;
    answer(cmd, m != MODE_COUNT && app_req_mode(m, &why), why ? why : (m == MODE_COUNT ? "unknown mode" : NULL));
  }
  else if (strcmp(cmd, "TEST") == 0 && n >= 3)
  {
    /* C,TEST,<0..3>: 0 = IC init check, 1 = bottom shuffler (S2), 2 = top shuffler (S1), 3 = both */
    answer(cmd, app_req_test(atoi(f[2]), &why), why);
  }
  else if (strcmp(cmd, "EN") == 0 && n >= 3)
  {
    answer(cmd, app_req_enable(atoi(f[2]) != 0, &why), why);
  }
  else if (strcmp(cmd, "DUTY") == 0 && n >= 4)
  {
    answer(cmd, app_req_duty((uint8_t)atoi(f[2]), (float)atof(f[3]), &why), why);
  }
  else if (strcmp(cmd, "DUTYS") == 0 && n >= 2 + N_LEG)
  {
    int ok = 1;
    for (int i = 0; i < N_LEG && ok; i++) ok = app_req_duty((uint8_t)i, (float)atof(f[2 + i]), &why);
    answer(cmd, ok, why);
  }
  else if (strcmp(cmd, "VREF") == 0 && n >= 2 + N_SHUF)
  {
    float rv[N_SHUF];
    for (int i = 0; i < N_SHUF; i++) rv[i] = (float)atof(f[2 + i]);
    answer(cmd, app_req_vref(rv, &why), why);
  }
  else if (strcmp(cmd, "SUP") == 0 && n >= 3)
  {
    answer(cmd, app_req_sup_enable(atoi(f[2]) != 0), NULL);
  }
  else if (strcmp(cmd, "GAIN") == 0)
  {
    answer(cmd, 0, "use C,SET / C,SETM / C,APPLY");
  }
  else if (strcmp(cmd, "SET") == 0 && n >= 4)
  {
    /* C,SET,<name>,<value> */
    char *end = NULL;
    float v = strtof(f[3], &end);
    if (end == f[3]) { answer(cmd, 0, "bad number"); return; }
    answer(cmd, prt_set(f[2], v, app_running(), &why), why);
  }
  else if (strcmp(cmd, "SETM") == 0)
  {
    /* C,SETM,<m00>,<m01>,...,<m33> : base M row-major, staged until C,APPLY */
    float v[N_Y * N_Y];
    int k;
    if (n != 2 + N_Y * N_Y) { answer(cmd, 0, "need 16 values"); return; }
    for (k = 0; k < N_Y * N_Y; k++) v[k] = strtof(f[2 + k], NULL);
    answer(cmd, prt_setm(v, N_Y * N_Y, &why), why);
  }
  else if (strcmp(cmd, "GET") == 0 && n >= 3)
  {
    float v;
    char b[64], fv[24];
    if (!prt_get(f[2], &v)) { answer(cmd, 0, "unknown parameter"); return; }
    snprintf(b, sizeof b, "P,%s,%s\n", f[2], fmt_g6(fv, v));
    tx(b);
    answer(cmd, 1, NULL);
  }
  else if (strcmp(cmd, "LIST") == 0)
  {
    prt_list(list_cb);
    answer(cmd, 1, prt_staged_dirty() ? "staged changes pending, C,APPLY" : NULL);
  }
  else if (strcmp(cmd, "APPLY") == 0)
  {
    answer(cmd, prt_apply(&why), why);
  }
  else if (strcmp(cmd, "REVERT") == 0)
  {
    answer(cmd, prt_revert(app_running(), &why), why);
  }
  else if (strcmp(cmd, "ESTOP") == 0)
  {
    app_req_soft_estop();
    answer(cmd, 1, NULL);
  }
  else if (strcmp(cmd, "CLEAR") == 0)
  {
    answer(cmd, app_req_clear(&why), why);
  }
  else if (strcmp(cmd, "CAL") == 0 && n >= 5)
  {
    /* C,CAL,<ch 0..3>,<mV/A>,<zero code or 0> : bench calibration of a hall channel */
    /* routed through the parameter table so C,LIST shows it (same bounds) */
    char nm[12];
    int ch = atoi(f[2]);
    int ok = (ch >= 0 && ch < SENSE_COUNT);
    if (ok) { snprintf(nm, sizeof nm, "hall_mva%d", ch); ok = prt_set(nm, (float)atof(f[3]), app_running(), &why); }
    if (ok && atoi(f[4]) > 0) { snprintf(nm, sizeof nm, "hall_zero%d", ch); ok = prt_set(nm, (float)atoi(f[4]), app_running(), &why); }
    answer(cmd, ok, ok ? NULL : (why ? why : "channel 0..3"));
  }
  else if (strcmp(cmd, "PING") == 0)
  {
    comms_send_status();
    answer(cmd, 1, NULL);
  }
  else
  {
    answer(cmd, 0, "unknown command");
  }
}

void comms_poll_rx(void)
{
  while (s_tail != s_head)
  {
    char c = (char)s_ring[s_tail];
    s_tail = (uint16_t)((s_tail + 1U) % RX_RING);
    if (c == '\n' || c == '\r')
    {
      if (s_line_len > 0U)
      {
        s_line[s_line_len] = '\0';
        handle_line(s_line);
        s_line_len = 0U;
      }
    }
    else if (s_line_len < LINE_MAX - 1U)
    {
      s_line[s_line_len++] = c;
    }
    else
    {
      s_line_len = 0U;   /* overflow: drop the line */
    }
  }
}
