// shuffler_ctrl_dll.cpp - QSPICE C-block around the firmware control stack (6_RTOS/ctrl_core)
//
// Build (Digital Mars C++ bundled with QSPICE):  build_dll.bat   -> shuffler_ctrl_dll.dll
// The DLL must sit next to the schematic/netlist that uses it (copied into PCB_Baseline/stages/).
//
// Pins (order = data[] index), all doubles:
//   in  0..2  PV1P PV2P PV3P     string node voltages (the INA239 bus inputs: U12 = PV3P, U11 = PV2P, U10 = PV1P-PV3P)
//   in  3..6  HSA1 HSB1 HSA2 HSB2 hall sensor output voltages (1.65 V + S*I; A: 100 mV/A, B: -25 mV/A as mounted)
//   in  7     CTRL_EN             0 = open loop at 0.5 duty (controller held in reset), 1 = closed loop
//   in  8..9  VREF1 VREF2         manual voltage-difference references [V]
//   out 10..13 DA1 DB1 DA2 DB2    duties 0..1 (held between control ticks)
//   out 14..15 RV1 RV2            supervisor relaxation references
//   out 16..17 BETA STRESS        supervisor governor gain / stress index
//   out 18..19 IM1R IM2R          reconstructed module currents relative to module 3
//
// Sampling: the control tick is CTRL_TS (params.h, 100 us); the solver is forced to land on every
// tick by Trunc(). Module voltages are sampled and held at the INA239 rate (1 ms) with 3.125 mV
// quantisation; hall voltages are quantised to the 12-bit / 3.3 V ADC at every tick. A one-level
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
static const double HALL_S[4] = {100.0, -25.0, 100.0, -25.0};   /* mV/A, control sign convention */

struct sCTRL
{
   stack_state_t st, st_prev;
   stack_out_t out, out_prev;
   long k, k_prev;
   int have_prev;
   long kvm;
   double vm[3];
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
   const double pv1 = data[0].d, pv2 = data[1].d, pv3 = data[2].d;
   const double hs[4] = {data[3].d, data[4].d, data[5].d, data[6].d};
   const double en = data[7].d, vref1 = data[8].d, vref2 = data[9].d;

   /* INA239 sample-and-hold at 1 kHz (bus voltages, quantised), VM as the firmware forms them */
   long kvm = (long)floor(t / INA_TS + 1e-9);
   if (kvm != inst->kvm)
   {
      double u12 = quant(pv3, INA_LSB), u11 = quant(pv2, INA_LSB), u10 = quant(pv1 - pv3, INA_LSB);
      inst->vm[2] = u12;
      inst->vm[1] = u11 - u12;
      inst->vm[0] = u10 - inst->vm[1];
      inst->kvm = kvm;
   }

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
         for (int n = 0; n < 3; n++) in.VM[n] = (float)inst->vm[n];
         for (int n = 0; n < 4; n++) in.IL[n] = hall_amps(hs[n], HALL_S[n]);
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

   for (int n = 0; n < 4; n++) data[10 + n].d = inst->out.d[n];
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
