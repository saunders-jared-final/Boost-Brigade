// shuffler_ctrl_dll.cpp - QSPICE C-block around the firmware control stack (6_RTOS/ctrl_core)
//
// Build (Digital Mars C++ bundled with QSPICE):  build_dll.bat   -> shuffler_ctrl_dll.dll
// The DLL must sit next to the schematic/netlist that uses it (copied into PCB_Baseline/stages/).
//
// Pins (order = data[] index), all doubles:
//   in  0..2  PV1P PV2P PV3P     string node voltages (the INA239 bus inputs: U12 = PV3P, U11 = PV2P, U10 = PV1P-PV3P)
//   in  3..6  HSA1 HSB1 HSA2 HSB2 hall sensor output voltages (1.65 V + S*I; A: 100 mV/A into the midpoint,
//                                 B: 25 mV/A OUT of the midpoint as mounted = the control stack convention)
//   in  7     CTRL_EN             0 = open loop at 0.5 duty (controller held in reset), 1 = closed loop
//   in  8..9  VREF1 VREF2         manual voltage-difference references [V]
//   out 10..13 DA1 DB1 DA2 DB2    duties 0..1 (held between control ticks)
//   out 14..15 RV1 RV2            supervisor relaxation references
//   out 16..17 BETA STRESS        supervisor governor gain / stress index
//   out 18..19 IM1R IM2R          reconstructed module currents relative to module 3
//
// Sampling: the control tick is CTRL_TS (params.h, 100 us); the solver is forced to land on every
// tick by Trunc(). Like the firmware ADC (4x oversampling across one PWM period) the hall inputs
// are AVERAGED over the tick interval (trapezoidal integration of every solver point), then
// quantised to the 12-bit / 3.3 V ADC; a point sample at the tick instant would alias the
// (large) phase ripple into a bias, since the tick is phase-locked to the PWM. Module voltages
// are sampled at the INA239 poll rate (1 kHz) as the average over the last control-tick interval
// (the 84 us conversion the firmware configures) and quantised to 3.125 mV. A one-level
// state history lets a rejected solver step (time going backwards by one tick) be replayed.
#include <malloc.h>
#include <math.h>
#include <string.h>

extern "C" {
#include "params.h"
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

#define INA_TS      1e-3
#define INA_LSB     0.003125
#define ADC_FS      3.3
#define ADC_CODES   4095.0
#define HALL_ZERO   1.65
static const double HALL_S[4] = {100.0, 25.0, 100.0, 25.0};   /* mV/A; the B sources already carry the reversed (out-of-midpoint) orientation */

struct sCTRL
{
   stack_state_t st, st_prev;
   stack_out_t out, out_prev;
   long k, k_prev;
   int have_prev;
   long kvm;
   double vm[3];
   /* running averages: inputs integrated between solver calls */
   double t_last, in_last[7];
   double acc_hs[4], t0_hs;      /* hall voltages over the current tick interval */
   double acc_pv[3], t0_pv;      /* string node voltages over the current INA interval */
   double hs_avg[4], pv_avg[3];
   int have_last;
};

static double quant(double v, double lsb) { return floor(v / lsb + 0.5) * lsb; }

static float hall_amps(double v, double S_mVperA)
{
   double code = floor(v / ADC_FS * ADC_CODES + 0.5);
   if (code < 0) code = 0;
   if (code > ADC_CODES) code = ADC_CODES;
   return (float)((code * ADC_FS / ADC_CODES - HALL_ZERO) * 1000.0 / S_mVperA);
}

static void idle_outputs(stack_out_t *o)
{
   memset(o, 0, sizeof *o);
   for (int n = 0; n < N_LEG; n++) o->d[n] = 0.5f;
}

extern "C" __declspec(dllexport) void shuffler_ctrl_dll(struct sCTRL **opaque, double t, union uData *data)
{
   if (!*opaque)
   {
      *opaque = (struct sCTRL *)calloc(sizeof(struct sCTRL), 1);
      stack_init(&(*opaque)->st);
      idle_outputs(&(*opaque)->out);
      (*opaque)->k = -1;
      (*opaque)->kvm = -1;
   }
   struct sCTRL *inst = *opaque;
   const double in_now[7] = {data[0].d, data[1].d, data[2].d, data[3].d, data[4].d, data[5].d, data[6].d};
   const double en = data[7].d, vref1 = data[8].d, vref2 = data[9].d;
   int n;

   /* trapezoidal running integrals of the measured inputs (reset on a solver rollback) */
   if (!inst->have_last || t < inst->t_last)
   {
      for (n = 0; n < 7; n++) inst->in_last[n] = in_now[n];
      inst->t_last = t;
      inst->have_last = 1;
      if (t < inst->t0_hs) { inst->t0_hs = t; for (n = 0; n < 4; n++) inst->acc_hs[n] = 0; }
      if (t < inst->t0_pv) { inst->t0_pv = t; for (n = 0; n < 3; n++) inst->acc_pv[n] = 0; }
   }
   else if (t > inst->t_last)
   {
      double dt = t - inst->t_last;
      for (n = 0; n < 3; n++) inst->acc_pv[n] += 0.5 * (inst->in_last[n] + in_now[n]) * dt;
      for (n = 0; n < 4; n++) inst->acc_hs[n] += 0.5 * (inst->in_last[3 + n] + in_now[3 + n]) * dt;
      for (n = 0; n < 7; n++) inst->in_last[n] = in_now[n];
      inst->t_last = t;
   }

   long kvm = (long)floor(t / INA_TS + 1e-9);

   long k = (long)floor(t / CTRL_TS + 1e-9);
   if (k < inst->k)
   {  /* solver stepped back: replay from the previous tick's state */
      if (inst->have_prev && k == inst->k - 1)
      {
         inst->st = inst->st_prev;
         inst->out = inst->out_prev;
         inst->have_prev = 0;
      }
      inst->k = k;
   }
   if (k > inst->k)
   {  /* new tick: inputs = averages over the elapsed tick interval (hall: the firmware's period
       * average; bus voltages: the 84 us INA239 conversion, read at the 1 kHz poll) */
      double span = t - inst->t0_hs;
      for (n = 0; n < 4; n++) inst->hs_avg[n] = (span > 1e-12) ? inst->acc_hs[n] / span : in_now[3 + n];
      for (n = 0; n < 4; n++) inst->acc_hs[n] = 0;
      inst->t0_hs = t;
      span = t - inst->t0_pv;
      for (n = 0; n < 3; n++) inst->pv_avg[n] = (span > 1e-12) ? inst->acc_pv[n] / span : in_now[n];
      for (n = 0; n < 3; n++) inst->acc_pv[n] = 0;
      inst->t0_pv = t;
      if (kvm != inst->kvm)
      {  /* INA239 poll: latest conversion, 3.125 mV LSB, VM as the firmware forms them */
         double u12 = quant(inst->pv_avg[2], INA_LSB), u11 = quant(inst->pv_avg[1], INA_LSB), u10 = quant(inst->pv_avg[0] - inst->pv_avg[2], INA_LSB);
         inst->vm[2] = u12;
         inst->vm[1] = u11 - u12;
         inst->vm[0] = u10 - inst->vm[1];
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
      if (en > 0.5)
      {
         stack_in_t in;
         memset(&in, 0, sizeof in);
         for (n = 0; n < 3; n++) in.VM[n] = (float)inst->vm[n];
         for (n = 0; n < 4; n++) in.IL[n] = hall_amps(inst->hs_avg[n], HALL_S[n]);
         in.Vstr = in.VM[0] + in.VM[1] + in.VM[2];
         in.Istr = 0.0f;
         in.Vref[0] = (float)vref1;
         in.Vref[1] = (float)vref2;
         in.en_sup = 1.0f;
         in.en_mppt = 0.0f;              /* the load does string MPPT */
         stack_step(&in, &inst->st, &inst->out);
      }
      else
      {
         stack_init(&inst->st);
         idle_outputs(&inst->out);
      }
      inst->k++;
   }

   for (n = 0; n < 4; n++) data[10 + n].d = inst->out.d[n];
   data[14].d = inst->out.rv[0];
   data[15].d = inst->out.rv[1];
   data[16].d = inst->out.beta;
   data[17].d = inst->out.stress;
   data[18].d = inst->out.IM[0];
   data[19].d = inst->out.IM[1];
}

/* largest timestep the solver may take while this block is in the circuit */
extern "C" __declspec(dllexport) double MaxExtStepSize(struct sCTRL *inst)
{
   return CTRL_TS;
}

/* shrink the proposed timestep so the solver lands exactly on the next control tick */
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
