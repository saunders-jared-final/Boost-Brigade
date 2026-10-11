/**
  * @file    sensors.c
  * @brief   TMCS1126 hall-effect current sensing and overcurrent latch.
  *
  * The four sensor outputs are converted as injected channels (two on ADC1,
  * two on ADC2), software-triggered once per millisecond from SysTick. Each
  * conversion is 16x hardware-oversampled with a 247.5-cycle sample time at
  * 42.5 MHz, i.e. averaged over ~98 us (about ten 100 kHz switching periods),
  * so the reading is the average inductor current rather than a point on the
  * ripple.
  *
  * VOUT = VREF (1.65 V) + S * I. The zero-current offset is measured once at
  * start-up, before any switching.
  *
  * Overcurrent: any channel with |I| above SENSE_OC_LIMIT_MA (or railed) for
  * SENSE_OC_TIME_MS consecutive samples disables every HRTIM output from the
  * SysTick interrupt and latches. Only an MCU reset clears the latch.
  */
#include "sensors.h"
#include "adc.h"
#include "hrtim.h"

#define ADC_FULL_SCALE      4096
#define ADC_NOMINAL_ZERO    2048    /* 1.65 V */
#define ADC_ZERO_TOLERANCE  124     /* +-100 mV around nominal */
#define ADC_RAIL_LOW        40      /* a reading this close to a rail is not a */
#define ADC_RAIL_HIGH       4055    /* valid sensor output: treat as overcurrent */
#define ZERO_CAL_SAMPLES    64

typedef struct
{
  ADC_TypeDef *adc;
  uint32_t     rank;
  int16_t      mV_per_A;   /* negative: sensor mounted with IN+ on the opposite side */
  const char  *name;
} Sense_Cfg;

/* On the PCB the A-phase sensors have IN+ on the inductor side and the
   B-phase sensors have IN+ on the "Output" side, so B is negated to give
   both phases the same sign convention. */
static const Sense_Cfg s_cfg[SENSE_COUNT] =
{
  [SENSE_ILA_1] = { ADC1, LL_ADC_INJ_RANK_1,  100, "ILA_1" },
  [SENSE_ILA_2] = { ADC1, LL_ADC_INJ_RANK_2,  100, "ILA_2" },
  [SENSE_ILB_1] = { ADC2, LL_ADC_INJ_RANK_1,  -25, "ILB_1" },
  [SENSE_ILB_2] = { ADC2, LL_ADC_INJ_RANK_2,  -25, "ILB_2" },
};

static volatile uint16_t s_raw[SENSE_COUNT];
static int16_t           s_zero[SENSE_COUNT];
static uint8_t           s_zero_ok[SENSE_COUNT];
static uint8_t           s_oc_count[SENSE_COUNT];
_Static_assert(SENSE_OC_TIME_MS <= 255, "s_oc_count is a uint8_t: a longer time could never latch");
static volatile uint8_t  s_running;
static volatile uint8_t  s_fault;
static volatile Sense_Channel s_fault_ch;
static volatile int32_t  s_fault_mA;
static volatile uint16_t s_fault_raw;

static void ConfigInjected(ADC_HandleTypeDef *hadc, uint32_t ch1, uint32_t ch2)
{
  ADC_InjectionConfTypeDef inj = {0};

  if (HAL_ADCEx_Calibration_Start(hadc, ADC_SINGLE_ENDED) != HAL_OK)
  {
    Error_Handler();
  }

  /* CubeMX generates ScanConvMode = ADC_SCAN_DISABLE in adc.c (the .ioc has
     no multi-channel sequence), and with that setting
     HAL_ADCEx_InjectedConfigChannel() programs a ONE-conversion injected
     sequence and silently ignores the rank 2 call: JDR2 then stays 0, which
     reads as a railed sensor and trips the overcurrent latch 100 ms after
     start-up. The G4 ADC has no scan bit; this field only makes the HAL
     build the 2-rank JSQR. */
  hadc->Init.ScanConvMode = ADC_SCAN_ENABLE;

  inj.InjectedNbrOfConversion       = 2;
  inj.InjectedSamplingTime          = ADC_SAMPLETIME_247CYCLES_5;
  inj.InjectedSingleDiff            = ADC_SINGLE_ENDED;
  inj.InjectedOffsetNumber          = ADC_OFFSET_NONE;
  inj.InjectedDiscontinuousConvMode = DISABLE;
  inj.AutoInjectedConv              = DISABLE;
  inj.QueueInjectedContext          = DISABLE;
  inj.ExternalTrigInjecConv         = ADC_INJECTED_SOFTWARE_START;
  inj.ExternalTrigInjecConvEdge     = ADC_EXTERNALTRIGINJECCONV_EDGE_NONE;
  inj.InjecOversamplingMode         = ENABLE;
  inj.InjecOversampling.Ratio         = ADC_OVERSAMPLING_RATIO_16;
  inj.InjecOversampling.RightBitShift = ADC_RIGHTBITSHIFT_4;

  inj.InjectedChannel = ch1;
  inj.InjectedRank    = ADC_INJECTED_RANK_1;
  if (HAL_ADCEx_InjectedConfigChannel(hadc, &inj) != HAL_OK)
  {
    Error_Handler();
  }
  inj.InjectedChannel = ch2;
  inj.InjectedRank    = ADC_INJECTED_RANK_2;
  if (HAL_ADCEx_InjectedConfigChannel(hadc, &inj) != HAL_OK)
  {
    Error_Handler();
  }
}

static int32_t Counts_To_mA(Sense_Channel ch, int32_t raw)
{
  /* I = (raw - zero) * 3.3 V / 4096 / S. With |raw - zero| <= 4095 the
     numerator stays below 2^31 (4095 * 412500 = 1.69e9). */
  return ((raw - s_zero[ch]) * 412500) / (512 * s_cfg[ch].mV_per_A);
}

/* Start one injected sequence on both ADCs and wait for it (start-up only). */
static void ConvertBlocking(void)
{
  uint32_t t0 = HAL_GetTick();

  LL_ADC_ClearFlag_JEOS(ADC1);
  LL_ADC_ClearFlag_JEOS(ADC2);
  LL_ADC_INJ_StartConversion(ADC1);
  LL_ADC_INJ_StartConversion(ADC2);
  while (!LL_ADC_IsActiveFlag_JEOS(ADC1) || !LL_ADC_IsActiveFlag_JEOS(ADC2))
  {
    if ((HAL_GetTick() - t0) > 10U)
    {
      Error_Handler();
    }
  }
}

void Sensors_Init(void)
{
  int32_t sum[SENSE_COUNT] = {0};

  ConfigInjected(&hadc1, ADC_CHANNEL_1,  ADC_CHANNEL_2);    /* ILA_1, ILA_2 */
  ConfigInjected(&hadc2, ADC_CHANNEL_17, ADC_CHANNEL_7);    /* ILB_1, ILB_2 */

  /* Enables the ADCs and runs a first (discarded) sequence. */
  if (HAL_ADCEx_InjectedStart(&hadc1) != HAL_OK || HAL_ADCEx_InjectedStart(&hadc2) != HAL_OK)
  {
    Error_Handler();
  }

  HAL_Delay(50);   /* TMCS1126 power-on time is 34 ms */

  for (int n = 0; n < ZERO_CAL_SAMPLES; n++)
  {
    ConvertBlocking();
    for (int ch = 0; ch < SENSE_COUNT; ch++)
    {
      sum[ch] += LL_ADC_INJ_ReadConversionData12(s_cfg[ch].adc, s_cfg[ch].rank);
    }
  }

  for (int ch = 0; ch < SENSE_COUNT; ch++)
  {
    int32_t zero = sum[ch] / ZERO_CAL_SAMPLES;
    int32_t err  = zero - ADC_NOMINAL_ZERO;

    s_zero_ok[ch] = (err > -ADC_ZERO_TOLERANCE) && (err < ADC_ZERO_TOLERANCE);
    /* An implausible offset (sensor unpowered, pin floating, current already
       flowing) must not be calibrated away: fall back to the nominal 1.65 V. */
    s_zero[ch] = s_zero_ok[ch] ? (int16_t)zero : ADC_NOMINAL_ZERO;
    s_raw[ch]  = (uint16_t)zero;
  }

  LL_ADC_ClearFlag_JEOS(ADC1);
  LL_ADC_ClearFlag_JEOS(ADC2);
  LL_ADC_INJ_StartConversion(ADC1);
  LL_ADC_INJ_StartConversion(ADC2);
  s_running = 1;
}

void Sensors_Tick1ms(void)
{
  if (s_fault)
  {
    /* Keep the outputs disabled whatever the main loop does. */
    hhrtim1.Instance->sCommonRegs.ODISR = HRTIM_ALL_OUTPUTS;
  }

  if (!s_running)
  {
    return;
  }

  /* The sequences started on the previous tick take ~200 us, so they are
     complete by now; if not, skip this tick rather than read stale data. */
  if (!LL_ADC_IsActiveFlag_JEOS(ADC1) || !LL_ADC_IsActiveFlag_JEOS(ADC2))
  {
    return;
  }

  for (int ch = 0; ch < SENSE_COUNT; ch++)
  {
    uint16_t raw = LL_ADC_INJ_ReadConversionData12(s_cfg[ch].adc, s_cfg[ch].rank);
    int32_t  mA  = Counts_To_mA((Sense_Channel)ch, raw);

    s_raw[ch] = raw;

    if (mA > SENSE_OC_LIMIT_MA || mA < -SENSE_OC_LIMIT_MA ||
        raw < ADC_RAIL_LOW || raw > ADC_RAIL_HIGH)
    {
      if (s_oc_count[ch] < SENSE_OC_TIME_MS)
      {
        s_oc_count[ch]++;
      }
      if (s_oc_count[ch] >= SENSE_OC_TIME_MS && !s_fault)
      {
        hhrtim1.Instance->sCommonRegs.ODISR = HRTIM_ALL_OUTPUTS;
        s_fault_ch  = (Sense_Channel)ch;
        s_fault_mA  = mA;
        s_fault_raw = raw;
        s_fault     = 1;
      }
    }
    else
    {
      s_oc_count[ch] = 0;
    }
  }

  LL_ADC_ClearFlag_JEOS(ADC1);
  LL_ADC_ClearFlag_JEOS(ADC2);
  LL_ADC_INJ_StartConversion(ADC1);
  LL_ADC_INJ_StartConversion(ADC2);
}

int32_t Sensors_Current_mA(Sense_Channel ch)
{
  return Counts_To_mA(ch, s_raw[ch]);
}

uint8_t Sensors_ZeroOk(Sense_Channel ch)
{
  return s_zero_ok[ch];
}

uint8_t Sensors_FaultLatched(void)
{
  return s_fault;
}

Sense_Channel Sensors_FaultChannel(void)
{
  return s_fault_ch;
}

int32_t Sensors_FaultCurrent_mA(void)
{
  return s_fault_mA;
}

uint16_t Sensors_FaultRaw(void)
{
  return s_fault_raw;
}

uint8_t Sensors_FaultRailed(void)
{
  return (s_fault_raw < ADC_RAIL_LOW) || (s_fault_raw > ADC_RAIL_HIGH);
}

const char *Sensors_Name(Sense_Channel ch)
{
  return s_cfg[ch].name;
}
