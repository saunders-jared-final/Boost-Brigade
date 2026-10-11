/**
  * @file    sensors.c
  * @brief   TMCS1126 hall-effect current sensing and over-current latch.
  *
  * Injected channels (two on ADC1, two on ADC2), software-started from the
  * control tick, 4x hardware oversampled with a 92.5-cycle sample time at
  * 42.5 MHz: one conversion ~2.5 us x 4 = ~10 us = one 100 kHz PWM period,
  * so each sample is the period-average inductor current. Both ADCs run in
  * parallel; a two-channel sequence is complete ~20 us after the start, long
  * before the next 100 us tick reads it.
  *
  * VOUT = VREF (1.65 V) + S * I. The zero-current offset is measured at
  * start-up, before any switching. The B-phase sensors are mounted the other
  * way round on the PCB, so their gain is negative to give every channel the
  * same sign convention (positive into the midpoint).
  *
  * Over-current: |I| above SENSE_OC_LIMIT_A (or an ADC code at a rail) for
  * SENSE_OC_TICKS consecutive ticks disables every HRTIM output from the ISR
  * and latches; Sensors_ClearFault() clears it (the application decides).
  */
#include "sensors.h"
#include "adc.h"
#include "hrtim.h"

#define ADC_FULL_SCALE      4096
#define ADC_NOMINAL_ZERO    2048    /* 1.65 V */
#define ADC_ZERO_TOLERANCE  124     /* +-100 mV around nominal */
#define ADC_RAIL_LOW        40
#define ADC_RAIL_HIGH       4055
#define ZERO_CAL_SAMPLES    64
#define ADC_LSB_MV          (3300.0f / 4096.0f)

typedef struct
{
  ADC_TypeDef *adc;
  uint32_t     rank;
  float        mV_per_A;   /* negative: sensor mounted with IN+ on the opposite side */
  const char  *name;
} Sense_Cfg;

static Sense_Cfg s_cfg[SENSE_COUNT] =
{
  [SENSE_ILA_1] = { ADC1, LL_ADC_INJ_RANK_1,  100.0f, "ILA_1" },
  [SENSE_ILB_1] = { ADC2, LL_ADC_INJ_RANK_1,  -25.0f, "ILB_1" },
  [SENSE_ILA_2] = { ADC1, LL_ADC_INJ_RANK_2,  100.0f, "ILA_2" },
  [SENSE_ILB_2] = { ADC2, LL_ADC_INJ_RANK_2,  -25.0f, "ILB_2" },
};

static volatile uint16_t s_raw[SENSE_COUNT];
static volatile float    s_amp[SENSE_COUNT];
static int16_t           s_zero[SENSE_COUNT];
static uint8_t           s_zero_ok[SENSE_COUNT];
static uint8_t           s_oc_count[SENSE_COUNT];
static uint8_t           s_rail_count[SENSE_COUNT];
static volatile uint8_t  s_running;
static volatile uint8_t  s_fault;
static volatile Sense_Channel s_fault_ch;
static volatile float    s_fault_A;
static volatile uint16_t s_fault_raw;

static void ConfigInjected(ADC_HandleTypeDef *hadc, uint32_t ch1, uint32_t ch2)
{
  ADC_InjectionConfTypeDef inj = {0};
  if (HAL_ADCEx_Calibration_Start(hadc, ADC_SINGLE_ENDED) != HAL_OK)
  {
    Error_Handler();
  }
  /* CubeMX generates ScanConvMode = ADC_SCAN_DISABLE; with that the HAL
     programs a one-conversion injected sequence and ignores rank 2. */
  hadc->Init.ScanConvMode = ADC_SCAN_ENABLE;
  inj.InjectedNbrOfConversion       = 2;
  inj.InjectedSamplingTime          = ADC_SAMPLETIME_92CYCLES_5;
  inj.InjectedSingleDiff            = ADC_SINGLE_ENDED;
  inj.InjectedOffsetNumber          = ADC_OFFSET_NONE;
  inj.InjectedDiscontinuousConvMode = DISABLE;
  inj.AutoInjectedConv              = DISABLE;
  inj.QueueInjectedContext          = DISABLE;
  inj.ExternalTrigInjecConv         = ADC_INJECTED_SOFTWARE_START;
  inj.ExternalTrigInjecConvEdge     = ADC_EXTERNALTRIGINJECCONV_EDGE_NONE;
  inj.InjecOversamplingMode         = ENABLE;
  inj.InjecOversampling.Ratio         = ADC_OVERSAMPLING_RATIO_4;
  inj.InjecOversampling.RightBitShift = ADC_RIGHTBITSHIFT_2;
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

static float Counts_To_A(Sense_Channel ch, int32_t raw)
{
  return ((float)(raw - s_zero[ch]) * ADC_LSB_MV) / s_cfg[ch].mV_per_A;
}

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
    /* an implausible offset (sensor unpowered, pin floating, current already
       flowing) must not be calibrated away: fall back to the nominal 1.65 V */
    s_zero[ch] = s_zero_ok[ch] ? (int16_t)zero : ADC_NOMINAL_ZERO;
    s_raw[ch]  = (uint16_t)zero;
    s_amp[ch]  = 0.0f;
  }
  LL_ADC_ClearFlag_JEOS(ADC1);
  LL_ADC_ClearFlag_JEOS(ADC2);
  LL_ADC_INJ_StartConversion(ADC1);
  LL_ADC_INJ_StartConversion(ADC2);
  s_running = 1;
}

void Sensors_Tick(void)
{
  if (s_fault)
  {
    hhrtim1.Instance->sCommonRegs.ODISR = HRTIM_ALL_OUTPUTS;   /* keep them off whatever happens */
  }
  if (!s_running)
  {
    return;
  }
  if (!LL_ADC_IsActiveFlag_JEOS(ADC1) || !LL_ADC_IsActiveFlag_JEOS(ADC2))
  {
    return;   /* not complete (should never happen at 100 us): keep the old sample */
  }
  for (int ch = 0; ch < SENSE_COUNT; ch++)
  {
    uint16_t raw = LL_ADC_INJ_ReadConversionData12(s_cfg[ch].adc, s_cfg[ch].rank);
    float    amp = Counts_To_A((Sense_Channel)ch, raw);
    uint8_t  railed = (raw < ADC_RAIL_LOW) || (raw > ADC_RAIL_HIGH);
    s_raw[ch] = raw;
    s_amp[ch] = amp;
    s_rail_count[ch] = railed ? (uint8_t)(s_rail_count[ch] + 1U) : 0U;
    if (amp > SENSE_OC_LIMIT_A || amp < -SENSE_OC_LIMIT_A)
    {
      if (s_oc_count[ch] < 255U) s_oc_count[ch]++;
    }
    else
    {
      s_oc_count[ch] = 0;
    }
    if (!s_fault && (s_oc_count[ch] >= SENSE_OC_TICKS || s_rail_count[ch] >= SENSE_RAIL_TICKS))
    {
      hhrtim1.Instance->sCommonRegs.ODISR = HRTIM_ALL_OUTPUTS;
      s_fault_ch  = (Sense_Channel)ch;
      s_fault_A   = amp;
      s_fault_raw = raw;
      s_fault     = 1;
    }
  }
  LL_ADC_ClearFlag_JEOS(ADC1);
  LL_ADC_ClearFlag_JEOS(ADC2);
  LL_ADC_INJ_StartConversion(ADC1);
  LL_ADC_INJ_StartConversion(ADC2);
}

float Sensors_Current_A(Sense_Channel ch)
{
  return s_amp[ch];
}

int32_t Sensors_Current_mA(Sense_Channel ch)
{
  return (int32_t)(s_amp[ch] * 1000.0f);
}

uint8_t Sensors_ZeroOk(Sense_Channel ch)
{
  return s_zero_ok[ch];
}

uint8_t Sensors_FaultLatched(void)
{
  return s_fault;
}

void Sensors_ClearFault(void)
{
  for (int ch = 0; ch < SENSE_COUNT; ch++)
  {
    s_oc_count[ch] = 0;
    s_rail_count[ch] = 0;
  }
  s_fault = 0;
}

Sense_Channel Sensors_FaultChannel(void)
{
  return s_fault_ch;
}

float Sensors_FaultCurrent_A(void)
{
  return s_fault_A;
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

void Sensors_SetCal(Sense_Channel ch, float mV_per_A, int16_t zero_code)
{
  if (ch >= SENSE_COUNT || mV_per_A == 0.0f) return;
  s_cfg[ch].mV_per_A = mV_per_A;
  if (zero_code > 0) s_zero[ch] = zero_code;
}

float Sensors_Cal_mVperA(Sense_Channel ch)
{
  return s_cfg[ch].mV_per_A;
}
