/**
  * @file    sensors.c
  * @brief   TMCS1126 hall-effect current sensing and over-current latch.
  *
  * Period-synchronous sampling (200 kHz PWM):
  *   HRTIM ADC trigger 1 fires at PER/8 + k*PER/4 (k = 0..3) of every PWM
  *   period (shuffler_hw.c). ADC1 (ILA_1, ILA_2) and ADC2 (ILB_1, ILB_2) each
  *   convert a two-rank regular sequence per trigger: 6.5 + 12.5 cycles at
  *   42.5 MHz = 0.45 us per conversion, 0.89 us per sequence, inside the
  *   1.25 us trigger spacing (1.6 Msps per ADC). DMA1 ch1/ch2 run circular
  *   over SENSE_BUF_LEN = 4 triggers x 20 periods x 2 ranks = 160 samples:
  *   exactly one 10 kHz control tick. Sensors_Tick() sums the whole buffer,
  *   so each reading is the mean over 80 equally spaced samples spanning 20
  *   whole periods, whatever the DMA write position (the ISR reads faster than
  *   the DMA writes, so a read racing the first new samples still covers 80
  *   consecutive samples). |H(f)| = |sin(pi f K D)/(K sin(pi f D))| with
  *   K = 4, D = Tsw/4: zeros at fsw, 2fsw, 3fsw; first pass band at 4fsw =
  *   800 kHz, above the TMCS1126 500 kHz bandwidth. The 20-period sum adds
  *   zeros at every 10 kHz multiple.
  *   The previous software-started 4x oversample (samples 2.47 us apart)
  *   passed the 400 kHz harmonic at 99.6 % at 200 kHz PWM.
  *
  * VOUT = VREF (1.65 V) + S * I. The zero-current offset is measured at
  * start-up with the counters running and every output disabled. Sign
  * convention = the control stack's: ILA positive INTO the converter midpoint,
  * ILB positive OUT of it (ILA+ILB = circulating current, ILA-ILB = shuffled
  * current). The B-phase sensors are mounted the other way round on the PCB,
  * so their RAW output already has that sign: both gains are positive. Verify
  * on the bench with a DC current (C,CAL / C,SET,hall_mva<ch>).
  *
  * Over-current: |I| (tick average) above the limit, or a tick average at an
  * ADC rail, or the sampling DMA stalling, for SENSE_OC_TICKS / SENSE_RAIL_TICKS
  * consecutive ticks disables every HRTIM output from the ISR and latches;
  * Sensors_ClearFault() clears it (the application decides).
  */
#include "sensors.h"
#include "adc.h"
#include "hrtim.h"
#include "shuffler_hw.h"
#include "stm32g4xx_ll_dma.h"
#include "stm32g4xx_ll_dmamux.h"

#define ADC_FULL_SCALE      4096
#define ADC_NOMINAL_ZERO    2048    /* 1.65 V */
#define ADC_ZERO_TOLERANCE  124     /* +-100 mV around nominal */
#define ADC_RAIL_LOW        40
#define ADC_RAIL_HIGH       4055
#define ZERO_CAL_TICKS      64
#define ADC_LSB_MV          (3300.0f / 4096.0f)

#define SENSE_SEQ_PER_TICK  (HW_ADC_TRIG_PER_PERIOD * HW_CTRL_DIV)   /* 80 */
#define SENSE_BUF_LEN       (2U * SENSE_SEQ_PER_TICK)                /* two ranks per sequence */
#define SENSE_STALL_TICKS   3       /* no DMA wrap for this many ticks = sampling dead */

typedef struct
{
  uint8_t      adc;        /* 0 = ADC1, 1 = ADC2 */
  uint8_t      rank;       /* 0 or 1 within the two-rank sequence */
  float        mV_per_A;   /* negative: sensor mounted with IN+ on the opposite side */
  const char  *name;
} Sense_Cfg;

static Sense_Cfg s_cfg[SENSE_COUNT] =
{
  [SENSE_ILA_1] = { 0, 0,  100.0f, "ILA_1" },
  [SENSE_ILB_1] = { 1, 0,   25.0f, "ILB_1" },
  [SENSE_ILA_2] = { 0, 1,  100.0f, "ILA_2" },
  [SENSE_ILB_2] = { 1, 1,   25.0f, "ILB_2" },
};

static volatile uint16_t s_buf[2][SENSE_BUF_LEN];
static volatile float    s_avg[SENSE_COUNT];     /* tick-average ADC code */
static volatile uint32_t s_ticks;
static volatile uint16_t s_raw[SENSE_COUNT];
static volatile float    s_amp[SENSE_COUNT];
static int16_t           s_zero[SENSE_COUNT];
static uint8_t           s_zero_ok[SENSE_COUNT];
static uint8_t           s_oc_count[SENSE_COUNT];
static uint8_t           s_rail_count[SENSE_COUNT];
static uint8_t           s_stall_count;
static volatile float    s_oc_limit = SENSE_OC_LIMIT_A;
static volatile uint8_t  s_running;
static volatile uint8_t  s_fault;
static volatile Sense_Channel s_fault_ch;
static volatile float    s_fault_A;
static volatile uint16_t s_fault_raw;

static void ConfigRegular(ADC_HandleTypeDef *hadc, uint32_t ch1, uint32_t ch2)
{
  ADC_ChannelConfTypeDef c = {0};
  /* MX_ADCx_Init() left the ADC configured but disabled: HAL_ADC_Init() may be called again */
  hadc->Init.ScanConvMode         = ADC_SCAN_ENABLE;
  hadc->Init.EOCSelection          = ADC_EOC_SEQ_CONV;
  hadc->Init.ContinuousConvMode    = DISABLE;
  hadc->Init.NbrOfConversion       = 2;
  hadc->Init.DiscontinuousConvMode = DISABLE;
  hadc->Init.ExternalTrigConv      = ADC_EXTERNALTRIG_HRTIM_TRG1;
  hadc->Init.ExternalTrigConvEdge  = ADC_EXTERNALTRIGCONVEDGE_RISING;
  hadc->Init.DMAContinuousRequests = ENABLE;
  hadc->Init.Overrun               = ADC_OVR_DATA_OVERWRITTEN;
  hadc->Init.OversamplingMode      = DISABLE;
  if (HAL_ADC_Init(hadc) != HAL_OK)
  {
    Error_Handler();
  }
  c.SamplingTime = ADC_SAMPLETIME_6CYCLES_5;   /* TMCS1126 output is low impedance */
  c.SingleDiff   = ADC_SINGLE_ENDED;
  c.OffsetNumber = ADC_OFFSET_NONE;
  c.Offset       = 0;
  c.Channel      = ch1;
  c.Rank         = ADC_REGULAR_RANK_1;
  if (HAL_ADC_ConfigChannel(hadc, &c) != HAL_OK)
  {
    Error_Handler();
  }
  c.Channel      = ch2;
  c.Rank         = ADC_REGULAR_RANK_2;
  if (HAL_ADC_ConfigChannel(hadc, &c) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_ADCEx_Calibration_Start(hadc, ADC_SINGLE_ENDED) != HAL_OK)
  {
    Error_Handler();
  }
}

static void ConfigDma(uint32_t channel, uint32_t request, ADC_TypeDef *adc, volatile uint16_t *buf)
{
  LL_DMA_DisableChannel(DMA1, channel);
  LL_DMA_ConfigTransfer(DMA1, channel,
                        LL_DMA_DIRECTION_PERIPH_TO_MEMORY | LL_DMA_MODE_CIRCULAR | LL_DMA_PERIPH_NOINCREMENT |
                        LL_DMA_MEMORY_INCREMENT | LL_DMA_PDATAALIGN_HALFWORD | LL_DMA_MDATAALIGN_HALFWORD |
                        LL_DMA_PRIORITY_HIGH);
  LL_DMA_SetPeriphRequest(DMA1, channel, request);
  LL_DMA_ConfigAddresses(DMA1, channel, LL_ADC_DMA_GetRegAddr(adc, LL_ADC_DMA_REG_REGULAR_DATA), (uint32_t)buf,
                         LL_DMA_DIRECTION_PERIPH_TO_MEMORY);
  LL_DMA_SetDataLength(DMA1, channel, SENSE_BUF_LEN);
  LL_DMA_EnableChannel(DMA1, channel);
}

static float Counts_To_A(Sense_Channel ch, float raw)
{
  return ((raw - (float)s_zero[ch]) * ADC_LSB_MV) / s_cfg[ch].mV_per_A;
}

void Sensors_Init(void)
{
  for (int ch = 0; ch < SENSE_COUNT; ch++)
  {
    s_zero[ch] = ADC_NOMINAL_ZERO;
    s_zero_ok[ch] = 0;
    s_avg[ch] = (float)ADC_NOMINAL_ZERO;
    s_amp[ch] = 0.0f;
  }
  for (unsigned i = 0; i < SENSE_BUF_LEN; i++)
  {
    s_buf[0][i] = ADC_NOMINAL_ZERO;
    s_buf[1][i] = ADC_NOMINAL_ZERO;
  }
  __HAL_RCC_DMAMUX1_CLK_ENABLE();
  __HAL_RCC_DMA1_CLK_ENABLE();
  ConfigRegular(&hadc1, ADC_CHANNEL_1,  ADC_CHANNEL_2);    /* ILA_1 (PA0), ILA_2 (PA1) */
  ConfigRegular(&hadc2, ADC_CHANNEL_17, ADC_CHANNEL_7);    /* ILB_1 (PA4), ILB_2 (PC1) */
  ConfigDma(LL_DMA_CHANNEL_1, LL_DMAMUX_REQ_ADC1, ADC1, s_buf[0]);
  ConfigDma(LL_DMA_CHANNEL_2, LL_DMAMUX_REQ_ADC2, ADC2, s_buf[1]);
  LL_ADC_REG_SetDMATransfer(ADC1, LL_ADC_REG_DMA_TRANSFER_UNLIMITED);
  LL_ADC_REG_SetDMATransfer(ADC2, LL_ADC_REG_DMA_TRANSFER_UNLIMITED);
  /* enable + ADSTART: conversions now wait for the HRTIM trigger (hw_init starts the counters) */
  if (HAL_ADC_Start(&hadc1) != HAL_OK || HAL_ADC_Start(&hadc2) != HAL_OK)
  {
    Error_Handler();
  }
  s_running = 0;
}

uint8_t Sensors_ZeroCal(void)
{
  float sum[SENSE_COUNT] = {0};
  uint32_t t0, last, n = 0U;

  HAL_Delay(50);   /* TMCS1126 power-on time is 34 ms; HRTIM triggers are running */
  t0 = HAL_GetTick();
  last = s_ticks;
  while (n < ZERO_CAL_TICKS && (HAL_GetTick() - t0) < 100U)
  {
    if (s_ticks != last)
    {
      last = s_ticks;
      for (int ch = 0; ch < SENSE_COUNT; ch++) sum[ch] += s_avg[ch];
      n++;
    }
  }
  for (int ch = 0; ch < SENSE_COUNT; ch++)
  {
    int32_t zero = (n > 0U) ? (int32_t)(sum[ch] / (float)n + 0.5f) : 0;
    int32_t err  = zero - ADC_NOMINAL_ZERO;
    s_zero_ok[ch] = (n == ZERO_CAL_TICKS) && (err > -ADC_ZERO_TOLERANCE) && (err < ADC_ZERO_TOLERANCE);
    /* an implausible offset (sensor unpowered, pin floating, current already
       flowing, sampling dead) must not be calibrated away: nominal 1.65 V */
    s_zero[ch] = s_zero_ok[ch] ? (int16_t)zero : ADC_NOMINAL_ZERO;
    s_raw[ch]  = (uint16_t)zero;
    s_amp[ch]  = 0.0f;
  }
  s_stall_count = 0;
  s_running = 1;
  return (n == ZERO_CAL_TICKS) ? 1U : 0U;
}

void Sensors_Tick(void)
{
  uint32_t acc[2][2] = {{0U, 0U}, {0U, 0U}};
  uint8_t wrapped;

  if (s_fault)
  {
    hhrtim1.Instance->sCommonRegs.ODISR = HRTIM_ALL_OUTPUTS;   /* keep them off whatever happens */
  }
  /* one DMA wrap per tick on each ADC: sampling alive */
  wrapped = (LL_DMA_IsActiveFlag_TC1(DMA1) && LL_DMA_IsActiveFlag_TC2(DMA1)) ? 1U : 0U;
  LL_DMA_ClearFlag_TC1(DMA1);
  LL_DMA_ClearFlag_TC2(DMA1);
  for (unsigned i = 0; i < SENSE_BUF_LEN; i += 2U)
  {
    acc[0][0] += s_buf[0][i];
    acc[0][1] += s_buf[0][i + 1U];
    acc[1][0] += s_buf[1][i];
    acc[1][1] += s_buf[1][i + 1U];
  }
  for (int ch = 0; ch < SENSE_COUNT; ch++)
  {
    s_avg[ch] = (float)acc[s_cfg[ch].adc][s_cfg[ch].rank] * (1.0f / (float)SENSE_SEQ_PER_TICK);
  }
  s_ticks++;
  if (!s_running)
  {
    return;
  }
  s_stall_count = wrapped ? 0U : (uint8_t)(s_stall_count < 255U ? s_stall_count + 1U : 255U);
  for (int ch = 0; ch < SENSE_COUNT; ch++)
  {
    float    avg = s_avg[ch];
    uint16_t raw = (uint16_t)(avg + 0.5f);
    float    amp = Counts_To_A((Sense_Channel)ch, avg);
    float    lim = s_oc_limit;
    uint8_t  railed = (raw < ADC_RAIL_LOW) || (raw > ADC_RAIL_HIGH);
    s_raw[ch] = raw;
    s_amp[ch] = amp;
    s_rail_count[ch] = railed ? (uint8_t)(s_rail_count[ch] < 255U ? s_rail_count[ch] + 1U : 255U) : 0U;
    if (amp > lim || amp < -lim)
    {
      if (s_oc_count[ch] < 255U) s_oc_count[ch]++;
    }
    else
    {
      s_oc_count[ch] = 0;
    }
    if (!s_fault && (s_oc_count[ch] >= SENSE_OC_TICKS || s_rail_count[ch] >= SENSE_RAIL_TICKS ||
                     s_stall_count >= SENSE_STALL_TICKS))
    {
      hhrtim1.Instance->sCommonRegs.ODISR = HRTIM_ALL_OUTPUTS;
      s_fault_ch  = (Sense_Channel)ch;
      s_fault_A   = amp;
      s_fault_raw = (s_stall_count >= SENSE_STALL_TICKS) ? 0U : raw;   /* 0 reads as "railed" in the F line */
      s_fault     = 1;
    }
  }
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
  s_stall_count = 0;
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

int16_t Sensors_Cal_Zero(Sense_Channel ch)
{
  return (ch < SENSE_COUNT) ? s_zero[ch] : 0;
}

void Sensors_SetOcLimit(float amps)
{
  if (!(amps > 0.0f)) return;
  s_oc_limit = (amps > SENSE_OC_LIMIT_A) ? SENSE_OC_LIMIT_A : amps;
}

float Sensors_OcLimit(void)
{
  return s_oc_limit;
}

float Sensors_RawAvg(Sense_Channel ch)
{
  return (ch < SENSE_COUNT) ? s_avg[ch] : 0.0f;
}
