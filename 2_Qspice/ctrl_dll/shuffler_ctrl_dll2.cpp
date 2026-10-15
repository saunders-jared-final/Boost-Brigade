// shuffler_ctrl_dll2.cpp - QSPICE C-block for the S10 stages (200 kHz, Gate 4): the firmware control
// stack (6_RTOS/ctrl_core, built with CTRL_RUNTIME_GAINS like the STM32) plus test inputs for gain
// scale, gain-matrix choice, measurement filter, sensor sampling, sensor noise and the VM1 source.
// S9 keeps using shuffler_ctrl_dll.dll (pins unchanged).
//
// Build: build_dll2.bat -> shuffler_ctrl_dll2.dll (copied to PCB_Baseline/stages/)
//
// Pins (order = data[] index), all doubles; the test inputs are constant V-sources from .params:
//   in  0..2   PV1P PV2P PV3P     string node voltages (INA239: U12 = PV3P, U11 = PV2P, U10 = PV1P-PV3P)
//   in  3..6   HSA1 HSB1 HSA2 HSB2 hall outputs (1.65 V + S*I, A 100 mV/A into / B 25 mV/A out of the midpoint)
//   in  7      CTRL_EN            0 = open loop, controller held in reset; 1 = closed loop
//   in  8..9   VREF1 VREF2        manual voltage-difference references [V]
//   in  10     KSCALE             gain scale (firmware kscale): M_eff = KSCALE*M
//   in  11     MSEL               0 = params.h M (as flashed), 1 = QSPICE S9i M (100 kHz),
//                                 2 = M from ctrl_M2.txt next to the netlist (16 numbers, row-major)
//   in  12     FILT               0 = first-order IIR at FC; 1..8 = moving average over FILT ticks (filt_ma)
//   in  13     FC                 IIR corner [Hz] (fc_lpf)
//   in  14     NOISE              sensor noise level: 0 off, 1 = the 13 Oct bench telemetry std
//                                 (ILA 0.10 A, ILB 0.38 A, VM 0.03 V) + fixed hall zero offsets; 0.22 ~ /sqrt(20)
//   in  15     SAMP               hall sampling: 0 = continuous average over the tick (ideal comb),
//                                 1 = firmware fw-0.3.0: point samples at PER/8 + k*PER/4 (4 per PWM period,
//                                 80 per tick at 200 kHz), averaged; 2 = old firmware: 4 samples 2.47 us apart
//                                 at the end of the tick (software-started oversampling)
//   in  16     KBERR              B-phase hall gain as fitted / as assumed by the firmware (4 = B4 part read as B1)
//   in  17     FSWP               PWM frequency [Hz] (sets the SAMP=1 instants; ramp A starts at t = 0)
//   in  18     VM1SRC             0 = INA (U10), 1 = VSTRP - VM2 - VM3 (DL3021 CV setpoint)
//   in  19     VSTRP              string voltage for VM1SRC = 1 [V]
//   out 20..23 DA1 DB1 DA2 DB2    duties
//   out 24..25 RV1 RV2            supervisor relaxation references
//   out 26..27 BETA STRESS        supervisor governor gain / stress index
//   out 28..29 IM1R IM2R          reconstructed module currents relative to module 3
#include <malloc.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

extern "C" {
#include "params.h"
#include "shuffler_ctrl.h"
#include "stack.h"
}

union uData
{
   bool b; char c; unsigned char uc; short s; unsigned short us; int i; unsigned int ui;
   float f; double d; long long int i64; unsigned long long int ui64; char *str; unsigned char *bytes;
};

extern "C" __declspec(dllexport) int (*Display)(const char *format, ...) = 0;
extern "C" __declspec(dllexport) const double *DegreesC = 0;

int __stdcall DllMain(void *module, unsigned int reason, void *reserved) { return 1; }

#define N_IN        20
#define O_OUT       20
#define INA_TS      1e-3
#define INA_LSB     0.003125
#define ADC_FS      3.3
#define ADC_CODES   4095.0
#define HALL_ZERO   1.65
#define OLD_OS_DT   2.47e-6
#define MAX_SAMP    256
static const double HALL_S[4] = {100.0, 25.0, 100.0, 25.0};      /* firmware assumption, mV/A */
static const double NOISE_A[4] = {0.10, 0.38, 0.10, 0.38};        /* bench std per telemetry sample [A] */
static const double NOISE_VM = 0.03;                              /* bench std of a VM reading [V] */
static const double ZERO_OFS[4] = {3, -3, 2, -2};                 /* hall zero error [ADC counts] with NOISE */

/* MSEL 1: QSPICE S9i identification (sps-params-2.20261011-1634-3mod-qspice) */
static const double M_QSPICE[N_Y][N_Y] = {
   {-25.225200769285795, -0.5383336747139033, 1.9472174297760971, 0.24809218131397714},
   {-0.2731997022059976, -24.9973347924922, -0.47058685192446037, -2.0916221056669455},
   {0.06891369716425018, -0.017599500289516966, 9.999262036019218, 1.1798954339009425},
   {-0.030047097706939536, 0.10121284023898012, 1.8667818879669547, 11.873823232627536}};
static const float M_FLASH[N_Y][N_Y] = CTRL_M_INIT;

struct sCTRL
{
   stack_state_t st, st_prev;
   stack_out_t out, out_prev;
   long k, k_prev;
   int have_prev;
   long kvm;
   double vm[3];
   double t_last, in_last[7];
   double acc_hs[4], t0_hs;      /* SAMP 0: hall integral over the tick */
   double acc_pv[3], t0_pv;
   double hs_avg[4], pv_avg[3];
   double sum_s[4]; int n_s;     /* SAMP 1/2: point-sample sum over the tick */
   double next_ts;               /* SAMP 1: next sample instant */
   int have_last;
   int vm_valid;
   double gkey[5];               /* KSCALE MSEL FILT FC (+valid) the gains were built for */
   double M2[N_Y][N_Y]; int have_M2;
   unsigned long long rng;
   int noise_init;
};

static double quant(double v, double lsb) { return floor(v / lsb + 0.5) * lsb; }

static double gauss(struct sCTRL *s)
{  /* Box-Muller on a 64-bit LCG: reproducible run to run */
   double u1, u2;
   s->rng = s->rng * 6364136223846793005ULL + 1442695040888963407ULL;
   u1 = ((s->rng >> 11) + 1.0) / 9007199254740993.0;
   s->rng = s->rng * 6364136223846793005ULL + 1442695040888963407ULL;
   u2 = (s->rng >> 11) / 9007199254740992.0;
   return sqrt(-2.0 * log(u1)) * cos(6.283185307179586 * u2);
}

static float hall_amps(double v, double S_mVperA, double zero_ofs_counts)
{
   double code = floor(v / ADC_FS * ADC_CODES + 0.5) + zero_ofs_counts;
   if (code < 0) code = 0;
   if (code > ADC_CODES) code = ADC_CODES;
   return (float)((code * ADC_FS / ADC_CODES - HALL_ZERO) * 1000.0 / S_mVperA);
}

static void idle_outputs(stack_out_t *o)
{
   memset(o, 0, sizeof *o);
   for (int n = 0; n < N_LEG; n++) o->d[n] = 0.5f;
}

static int inv4(double A[N_Y][N_Y], double R[N_Y][N_Y])
{  /* Gauss-Jordan with partial pivoting (params_rt.c inv_n in double) */
   double a[N_Y][2 * N_Y];
   int i, j, c, p;
   for (i = 0; i < N_Y; i++)
      for (j = 0; j < 2 * N_Y; j++) a[i][j] = (j < N_Y) ? A[i][j] : (j - N_Y == i ? 1.0 : 0.0);
   for (c = 0; c < N_Y; c++)
   {
      p = c;
      for (i = c + 1; i < N_Y; i++) if (fabs(a[i][c]) > fabs(a[p][c])) p = i;
      if (fabs(a[p][c]) < 1e-12) return 0;
      if (p != c) for (j = 0; j < 2 * N_Y; j++) { double t = a[c][j]; a[c][j] = a[p][j]; a[p][j] = t; }
      double piv = a[c][c];
      for (j = 0; j < 2 * N_Y; j++) a[c][j] /= piv;
      for (i = 0; i < N_Y; i++)
         if (i != c) { double f = a[i][c]; for (j = 0; j < 2 * N_Y; j++) a[i][j] -= f * a[c][j]; }
   }
   for (i = 0; i < N_Y; i++) for (j = 0; j < N_Y; j++) R[i][j] = a[i][N_Y + j];
   return 1;
}

static void load_M2(struct sCTRL *s)
{
   FILE *f = fopen("ctrl_M2.txt", "r");
   s->have_M2 = 0;
   if (!f) return;
   int n = 0;
   for (int i = 0; i < N_Y; i++)
      for (int j = 0; j < N_Y; j++)
         if (fscanf(f, "%lf", &s->M2[i][j]) == 1) n++;
   fclose(f);
   s->have_M2 = (n == N_Y * N_Y);
}

/* ctrl_gains from the test inputs, with the params_rt.c arithmetic */
static void build_gains(struct sCTRL *s, double kscale, double msel, double filt, double fc)
{
   if (s->gkey[4] == 1.0 && s->gkey[0] == kscale && s->gkey[1] == msel && s->gkey[2] == filt && s->gkey[3] == fc) return;
   double Me[N_Y][N_Y], Mi[N_Y][N_Y];
   int sel = (int)floor(msel + 0.5);
   if (sel == 2 && !s->have_M2)
   {
      if (Display) Display("shuffler_ctrl_dll2: MSEL=2 but ctrl_M2.txt missing/short - using the params.h M\n");
      sel = 0;
   }
   for (int i = 0; i < N_Y; i++)
      for (int j = 0; j < N_Y; j++)
         Me[i][j] = kscale * (sel == 1 ? M_QSPICE[i][j] : sel == 2 ? s->M2[i][j] : (double)M_FLASH[i][j]);
   if (!inv4(Me, Mi))
   {
      if (Display) Display("shuffler_ctrl_dll2: M singular - gains unchanged\n");
      return;
   }
   for (int i = 0; i < N_Y; i++)
      for (int j = 0; j < N_Y; j++)
      {
         double kp = (j < N_SHUF) ? CTRL_KP_RATIO_V : CTRL_KP_RATIO_I;
         ctrl_gains.M[i][j] = (float)Me[i][j];
         ctrl_gains.Mp[i][j] = (float)(Me[i][j] * kp);
         ctrl_gains.Minv[i][j] = (float)Mi[i][j];
      }
   double w = 6.283185307179586 * fc * CTRL_TS;
   ctrl_gains.a = (float)(w / (1.0 + w));
   int ma = (int)floor(filt + 0.5);
   ctrl_gains.ma_n = (unsigned char)(ma < 0 ? 0 : ma > (int)CTRL_MA_MAX ? (int)CTRL_MA_MAX : ma);
   ctrl_gains.dmin = CTRL_DMIN;
   ctrl_gains.dmax = CTRL_DMAX;
   s->gkey[0] = kscale; s->gkey[1] = msel; s->gkey[2] = filt; s->gkey[3] = fc; s->gkey[4] = 1.0;
   if (Display) Display("shuffler_ctrl_dll2: gains KSCALE=%g MSEL=%d FILT=%d FC=%g (M00=%g, M22=%g)\n",
                        kscale, sel, (int)ctrl_gains.ma_n, fc, Me[0][0], Me[2][2]);
}

/* hall input as the ADC sees it: KBERR scales the B-phase deviation from mid-rail */
static double hall_seen(const double *hs, int n, double kberr)
{
   return (n & 1) ? HALL_ZERO + kberr * (hs[n] - HALL_ZERO) : hs[n];
}

extern "C" __declspec(dllexport) void shuffler_ctrl_dll2(struct sCTRL **opaque, double t, union uData *data)
{
   if (!*opaque)
   {
      *opaque = (struct sCTRL *)calloc(sizeof(struct sCTRL), 1);
      stack_init(&(*opaque)->st);
      idle_outputs(&(*opaque)->out);
      (*opaque)->k = -1;
      (*opaque)->kvm = -1;
      (*opaque)->rng = 0x5DEECE66DULL;
      load_M2(*opaque);
   }
   struct sCTRL *inst = *opaque;
   const double in_now[7] = {data[0].d, data[1].d, data[2].d, data[3].d, data[4].d, data[5].d, data[6].d};
   const double en = data[7].d, vref1 = data[8].d, vref2 = data[9].d;
   const double kscale = data[10].d, msel = data[11].d, filt = data[12].d, fc = data[13].d;
   const double noise = data[14].d, samp = data[15].d, kberr = data[16].d, fsw = data[17].d;
   const double vm1src = data[18].d, vstrp = data[19].d;
   const int smode = (int)floor(samp + 0.5);
   const double tsw = (fsw > 1.0) ? 1.0 / fsw : 5e-6;
   int n;

   if (!inst->have_last || t < inst->t_last)
   {
      for (n = 0; n < 7; n++) inst->in_last[n] = in_now[n];
      inst->t_last = t;
      inst->have_last = 1;
      if (t < inst->t0_hs) { inst->t0_hs = t; for (n = 0; n < 4; n++) inst->acc_hs[n] = 0; inst->n_s = 0; for (n = 0; n < 4; n++) inst->sum_s[n] = 0; }
      if (t < inst->t0_pv) { inst->t0_pv = t; for (n = 0; n < 3; n++) inst->acc_pv[n] = 0; }
      if (smode == 1 && (inst->next_ts <= 0.0 || t < inst->next_ts - tsw)) inst->next_ts = (floor(t / (tsw / 4)) + 0.5) * (tsw / 4);
   }
   else if (t > inst->t_last)
   {
      double dt = t - inst->t_last;
      for (n = 0; n < 3; n++) inst->acc_pv[n] += 0.5 * (inst->in_last[n] + in_now[n]) * dt;
      for (n = 0; n < 4; n++) inst->acc_hs[n] += 0.5 * (inst->in_last[3 + n] + in_now[3 + n]) * dt;
      if (smode == 1)
      {  /* firmware comb: every PER/4, offset PER/8, linear interpolation between solver points */
         while (inst->next_ts <= t && inst->n_s < MAX_SAMP)
         {
            double f = (inst->next_ts - inst->t_last) / dt;
            if (f < 0) f = 0;
            for (n = 0; n < 4; n++) inst->sum_s[n] += inst->in_last[3 + n] + f * (in_now[3 + n] - inst->in_last[3 + n]);
            inst->n_s++;
            inst->next_ts += tsw / 4;
         }
      }
      else if (smode == 2)
      {
         while (inst->next_ts <= t && inst->n_s < 4)
         {
            double f = (inst->next_ts - inst->t_last) / dt;
            if (f < 0) f = 0;
            for (n = 0; n < 4; n++) inst->sum_s[n] += inst->in_last[3 + n] + f * (in_now[3 + n] - inst->in_last[3 + n]);
            inst->n_s++;
            inst->next_ts += OLD_OS_DT;
         }
      }
      for (n = 0; n < 7; n++) inst->in_last[n] = in_now[n];
      inst->t_last = t;
   }

   long kvm = (long)floor(t / INA_TS + 1e-9);
   long k = (long)floor(t / CTRL_TS + 1e-9);
   if (k < inst->k)
   {
      if (inst->have_prev && k == inst->k - 1)
      {
         inst->st = inst->st_prev;
         inst->out = inst->out_prev;
         inst->have_prev = 0;
      }
      inst->k = k;
   }
   if (k > inst->k)
   {
      double span = t - inst->t0_hs;
      if (smode == 1 && inst->n_s > 0)
         for (n = 0; n < 4; n++) inst->hs_avg[n] = inst->sum_s[n] / inst->n_s;
      else if (smode == 2 && inst->n_s > 0)
         for (n = 0; n < 4; n++) inst->hs_avg[n] = inst->sum_s[n] / inst->n_s;
      else
         for (n = 0; n < 4; n++) inst->hs_avg[n] = (span > 1e-12) ? inst->acc_hs[n] / span : in_now[3 + n];
      for (n = 0; n < 4; n++) { inst->acc_hs[n] = 0; inst->sum_s[n] = 0; }
      inst->n_s = 0;
      inst->t0_hs = t;
      if (smode == 2)
      {  /* old firmware: software-started burst right after the tick ISR, 4 samples 2.47 us apart,
          * converted during this tick and used at the next one (as before fw-0.3.0) */
         for (n = 0; n < 4; n++) inst->sum_s[n] = in_now[3 + n];
         inst->n_s = 1;
         inst->next_ts = t + OLD_OS_DT;
      }
      span = t - inst->t0_pv;
      int pv_ok = span > 1e-12;     /* no INA reading from a zero-length interval (t = 0 with uic: the node
                                     * voltages are not yet the .ic values, and the reading is held 1 ms) */
      for (n = 0; n < 3; n++) inst->pv_avg[n] = pv_ok ? inst->acc_pv[n] / span : in_now[n];
      for (n = 0; n < 3; n++) inst->acc_pv[n] = 0;
      inst->t0_pv = t;
      if (pv_ok && (kvm != inst->kvm || !inst->vm_valid))
      {
         inst->vm_valid = 1;
         double u12 = inst->pv_avg[2], u11 = inst->pv_avg[1], u10 = inst->pv_avg[0] - inst->pv_avg[2];
         if (noise > 0)
         {  /* VM std NOISE_VM on the differences the firmware forms -> per-reading std / sqrt(2) */
            u12 += noise * NOISE_VM / 1.41421356 * gauss(inst);
            u11 += noise * NOISE_VM / 1.41421356 * gauss(inst);
            u10 += noise * NOISE_VM / 1.41421356 * gauss(inst);
         }
         u12 = quant(u12, INA_LSB); u11 = quant(u11, INA_LSB); u10 = quant(u10, INA_LSB);
         inst->vm[2] = u12;
         inst->vm[1] = u11 - u12;
         inst->vm[0] = (vm1src > 0.5) ? vstrp - inst->vm[1] - inst->vm[2] : u10 - inst->vm[1];
         inst->kvm = kvm;
      }
   }
   while (k > inst->k)
   {
      if (inst->k >= 0)
      {
         inst->st_prev = inst->st;
         inst->out_prev = inst->out;
         inst->have_prev = 1;
      }
      build_gains(inst, kscale, msel, filt, fc);
      if (en > 0.5)
      {
         stack_in_t in;
         memset(&in, 0, sizeof in);
         for (n = 0; n < 3; n++) in.VM[n] = (float)inst->vm[n];
         for (n = 0; n < 4; n++)
         {
            double v = hall_seen(inst->hs_avg, n, kberr);
            double zofs = 0;
            if (noise > 0)
            {
               v += noise * NOISE_A[n] * HALL_S[n] * 1e-3 * gauss(inst);
               zofs = ZERO_OFS[n];
            }
            in.IL[n] = hall_amps(v, HALL_S[n], zofs);
         }
         in.Vstr = in.VM[0] + in.VM[1] + in.VM[2];
         in.Istr = 0.0f;
         in.Vref[0] = (float)vref1;
         in.Vref[1] = (float)vref2;
         in.en_sup = 1.0f;
         in.en_mppt = 0.0f;
         stack_step(&in, &inst->st, &inst->out);
      }
      else
      {
         stack_init(&inst->st);
         idle_outputs(&inst->out);
      }
      inst->k++;
   }

   for (n = 0; n < 4; n++) data[O_OUT + n].d = inst->out.d[n];
   data[O_OUT + 4].d = inst->out.rv[0];
   data[O_OUT + 5].d = inst->out.rv[1];
   data[O_OUT + 6].d = inst->out.beta;
   data[O_OUT + 7].d = inst->out.stress;
   data[O_OUT + 8].d = inst->out.IM[0];
   data[O_OUT + 9].d = inst->out.IM[1];
}

extern "C" __declspec(dllexport) double MaxExtStepSize(struct sCTRL *inst)
{
   return CTRL_TS;
}

extern "C" __declspec(dllexport) void Trunc(struct sCTRL *inst, double t, union uData *data, double *timestep)
{
   if (!inst) return;
   double tn = (double)(inst->k + 1) * CTRL_TS;
   double dt = tn - t;
   if (dt > 1e-13 && *timestep > dt) *timestep = dt;
}

extern "C" __declspec(dllexport) void Destroy(struct sCTRL *inst)
{
   free(inst);
}
