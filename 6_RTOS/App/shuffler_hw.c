/**
 * shuffler_hw.c - HRTIM power-stage layer (see header)
 *
 * Register-write ORDER matters on the HRTIM: once PREEN is set, writes to
 * PER/CMP/SET/RST/DT land in preload registers and only reach the active
 * registers on an update event. HAL_HRTIM_WaveformTimerConfig() enables the
 * preload and forces one software update, so it is called first; everything
 * written afterwards is transferred by the explicit software update before
 * the counters start.
 */
#include "shuffler_hw.h"

#include "hrtim.h"
#include "main.h"

static const uint32_t s_timidx[HW_N_LEG] = {HRTIM_TIMERINDEX_TIMER_A, HRTIM_TIMERINDEX_TIMER_B,
                                            HRTIM_TIMERINDEX_TIMER_C, HRTIM_TIMERINDEX_TIMER_D};
static const uint32_t s_outputs[HW_N_LEG] = {HRTIM_OUTPUT_TA1 | HRTIM_OUTPUT_TA2,
                                             HRTIM_OUTPUT_TB1 | HRTIM_OUTPUT_TB2,
                                             HRTIM_OUTPUT_TC1 | HRTIM_OUTPUT_TC2,
                                             HRTIM_OUTPUT_TD1 | HRTIM_OUTPUT_TD2};
static const uint32_t s_out1[HW_N_LEG] = {HRTIM_OUTPUT_TA1, HRTIM_OUTPUT_TB1, HRTIM_OUTPUT_TC1,
                                          HRTIM_OUTPUT_TD1};
static const uint32_t s_out2[HW_N_LEG] = {HRTIM_OUTPUT_TA2, HRTIM_OUTPUT_TB2, HRTIM_OUTPUT_TC2,
                                          HRTIM_OUTPUT_TD2};

static float s_duty[HW_N_LEG] = {0.5f, 0.5f, 0.5f, 0.5f};
static uint8_t s_enabled = 0U;
static volatile uint8_t s_pending_en = 0U;   /* legs to switch on at the next quarter period (hw_legs_enable_sync) */
static uint8_t s_en_tries = 0U;

/* Synchronised enable window: master CMP1 at PER/4 (middle of the A legs' high pulse at d ~ 0.5, B legs
 * low). Switching on there centres the circulating-current ripple on zero; a full-width first pulse
 * would leave it offset by half the ripple (~2x the steady peak right after enable). A late service
 * (the control tick shares this IRQ) waits for the next period instead of enabling at a random phase. */
#define HW_EN_CMP     (HW_HRTIM_PER / 4U)
#define HW_EN_WINDOW  (HW_HRTIM_PER / 8U)    /* 1.25 us of IRQ latency still lands within phase 0.25..0.375 */
#define HW_EN_TRIES   16U                   /* then enable anyway: never leave SOFTSTART ramping into dead outputs */

#define S1_GATE_PINS (S1_A_H_Pin | S1_A_L_Pin | S1_B_H_Pin | S1_B_L_Pin)
#define S2_GATE_PINS (S2_A_H_Pin | S2_A_L_Pin | S2_B_H_Pin | S2_B_L_Pin)

/* Drive all eight gate lines low as plain GPIO (register writes only, works
 * before HAL_Init() and inside fault handlers). */
static void gates_low(void)
{
  RCC->AHB2ENR |= RCC_AHB2ENR_GPIOAEN | RCC_AHB2ENR_GPIOBEN;
  (void)RCC->AHB2ENR;
  GPIOA->BRR = S1_GATE_PINS;
  GPIOB->BRR = S2_GATE_PINS;
  MODIFY_REG(GPIOA->MODER,
             GPIO_MODER_MODE8 | GPIO_MODER_MODE9 | GPIO_MODER_MODE10 | GPIO_MODER_MODE11,
             GPIO_MODER_MODE8_0 | GPIO_MODER_MODE9_0 | GPIO_MODER_MODE10_0 | GPIO_MODER_MODE11_0);
  MODIFY_REG(GPIOB->MODER,
             GPIO_MODER_MODE12 | GPIO_MODER_MODE13 | GPIO_MODER_MODE14 | GPIO_MODER_MODE15,
             GPIO_MODER_MODE12_0 | GPIO_MODER_MODE13_0 | GPIO_MODER_MODE14_0 | GPIO_MODER_MODE15_0);
}

/* Runs from __libc_init_array(), before main(): a floating gate line sits
 * mid-rail at the 1ED3140 inputs, so pin them low as early as possible. */
static void __attribute__((constructor)) gates_low_at_boot(void)
{
  gates_low();
}

void hw_pins_to_hrtim(void)
{
  GPIO_InitTypeDef g = {0};
  g.Mode = GPIO_MODE_AF_PP;
  g.Pull = GPIO_NOPULL;
  g.Speed = GPIO_SPEED_FREQ_HIGH;
  g.Alternate = GPIO_AF13_HRTIM1;
  g.Pin = S1_GATE_PINS;
  HAL_GPIO_Init(GPIOA, &g);
  g.Pin = S2_GATE_PINS;
  HAL_GPIO_Init(GPIOB, &g);
}

static uint32_t duty_to_cmp(float d)
{
  if (d < HW_DUTY_MIN) d = HW_DUTY_MIN;
  if (d > HW_DUTY_MAX) d = HW_DUTY_MAX;
  return (uint32_t)(d * (float)HW_HRTIM_PER + 0.5f);
}

void hw_init(void)
{
  uint8_t leg;

  /* ---- master: PWM period, CMP2 at half period, repetition = control tick ---- */
  HRTIM_TimeBaseCfgTypeDef tb = {0};
  tb.Period = HW_HRTIM_PER;
  tb.RepetitionCounter = HW_CTRL_DIV - 1U;
  tb.PrescalerRatio = HRTIM_PRESCALERRATIO_MUL32;
  tb.Mode = HRTIM_MODE_CONTINUOUS;

  HRTIM_TimerCfgTypeDef mcfg = {0};
  mcfg.DMARequests = HRTIM_TIM_DMA_NONE;
  mcfg.HalfModeEnable = HRTIM_HALFMODE_DISABLED;
  mcfg.StartOnSync = HRTIM_SYNCSTART_DISABLED;
  mcfg.ResetOnSync = HRTIM_SYNCRESET_DISABLED;
  mcfg.DACSynchro = HRTIM_DACSYNC_NONE;
  mcfg.PreloadEnable = HRTIM_PRELOAD_ENABLED;
  mcfg.UpdateGating = HRTIM_UPDATEGATING_INDEPENDENT;
  mcfg.BurstMode = HRTIM_TIMERBURSTMODE_MAINTAINCLOCK;
  mcfg.RepetitionUpdate = HRTIM_UPDATEONREPETITION_ENABLED;
  mcfg.InterruptRequests = HRTIM_MASTER_IT_MREP;
  if (HAL_HRTIM_WaveformTimerConfig(&hhrtim1, HRTIM_TIMERINDEX_MASTER, &mcfg) != HAL_OK) Error_Handler();
  if (HAL_HRTIM_TimeBaseConfig(&hhrtim1, HRTIM_TIMERINDEX_MASTER, &tb) != HAL_OK) Error_Handler();
  HRTIM_CompareCfgTypeDef mcmp = {0};
  mcmp.CompareValue = HW_HRTIM_PER / 2U;
  if (HAL_HRTIM_WaveformCompareConfig(&hhrtim1, HRTIM_TIMERINDEX_MASTER, HRTIM_COMPAREUNIT_2, &mcmp) != HAL_OK) Error_Handler();
  mcmp.CompareValue = HW_EN_CMP;
  if (HAL_HRTIM_WaveformCompareConfig(&hhrtim1, HRTIM_TIMERINDEX_MASTER, HRTIM_COMPAREUNIT_1, &mcmp) != HAL_OK) Error_Handler();

  /* ---- the four leg timers ---- */
  for (leg = 0U; leg < HW_N_LEG; leg++)
  {
    const bool legB = (leg & 1U) != 0U;
    HRTIM_TimerCfgTypeDef tim = {0};
    tim.DMARequests = HRTIM_TIM_DMA_NONE;
    tim.HalfModeEnable = HRTIM_HALFMODE_DISABLED;
    tim.StartOnSync = HRTIM_SYNCSTART_DISABLED;
    tim.ResetOnSync = HRTIM_SYNCRESET_DISABLED;
    tim.DACSynchro = HRTIM_DACSYNC_NONE;
    tim.PreloadEnable = HRTIM_PRELOAD_ENABLED;
    tim.UpdateGating = HRTIM_UPDATEGATING_INDEPENDENT;
    tim.BurstMode = HRTIM_TIMERBURSTMODE_MAINTAINCLOCK;
    tim.RepetitionUpdate = HRTIM_UPDATEONREPETITION_DISABLED;
    tim.PushPull = HRTIM_TIMPUSHPULLMODE_DISABLED;
    tim.FaultEnable = HRTIM_TIMFAULTENABLE_NONE;   /* COMP trip: add FAULT4/5 once CubeMX provides COMP+DAC */
    tim.FaultLock = HRTIM_TIMFAULTLOCK_READWRITE;
    tim.DeadTimeInsertion = HRTIM_TIMDEADTIMEINSERTION_ENABLED;
    tim.DelayedProtectionMode = (leg < 2U) ? HRTIM_TIMER_A_B_C_DELAYEDPROTECTION_DISABLED
                                           : HRTIM_TIMER_D_E_DELAYEDPROTECTION_DISABLED;
    tim.UpdateTrigger = HRTIM_TIMUPDATETRIGGER_NONE;
    /* counter reset comes from the master: period for A legs, CMP2 for B legs */
    tim.ResetTrigger = legB ? HRTIM_TIMRESETTRIGGER_MASTER_CMP2 : HRTIM_TIMRESETTRIGGER_MASTER_PER;
    tim.ResetUpdate = HRTIM_TIMUPDATEONRESET_ENABLED;   /* preload -> active on every reset */
    tim.ReSyncUpdate = HRTIM_TIMERESYNC_UPDATE_UNCONDITIONAL;
    if (HAL_HRTIM_WaveformTimerConfig(&hhrtim1, s_timidx[leg], &tim) != HAL_OK) Error_Handler();

    /* the leg timer never rolls over by itself: its period is the maximum,
     * the master reset is its period */
    HRTIM_TimeBaseCfgTypeDef ltb = {0};
    ltb.Period = 0xFFDFU;
    ltb.RepetitionCounter = 0U;
    ltb.PrescalerRatio = HRTIM_PRESCALERRATIO_MUL32;
    ltb.Mode = HRTIM_MODE_CONTINUOUS;
    if (HAL_HRTIM_TimeBaseConfig(&hhrtim1, s_timidx[leg], &ltb) != HAL_OK) Error_Handler();

    HRTIM_CompareCfgTypeDef cmp = {0};
    cmp.CompareValue = duty_to_cmp(s_duty[leg]);
    if (HAL_HRTIM_WaveformCompareConfig(&hhrtim1, s_timidx[leg], HRTIM_COMPAREUNIT_1, &cmp) != HAL_OK) Error_Handler();

    /* dead time 200 ns both edges: DTPRSC = 000 -> tDTG = tHRTIM/8 = 0.735 ns;
     * on this HAL the macro that encodes DTPRSC = 000 is ..._MUL8 */
    HRTIM_DeadTimeCfgTypeDef dt = {0};
    dt.Prescaler = HRTIM_TIMDEADTIME_PRESCALERRATIO_MUL8;
    dt.RisingValue = 272U;
    dt.RisingSign = HRTIM_TIMDEADTIME_RISINGSIGN_POSITIVE;
    dt.RisingLock = HRTIM_TIMDEADTIME_RISINGLOCK_WRITE;
    dt.RisingSignLock = HRTIM_TIMDEADTIME_RISINGSIGNLOCK_WRITE;
    dt.FallingValue = 272U;
    dt.FallingSign = HRTIM_TIMDEADTIME_FALLINGSIGN_POSITIVE;
    dt.FallingLock = HRTIM_TIMDEADTIME_FALLINGLOCK_WRITE;
    dt.FallingSignLock = HRTIM_TIMDEADTIME_FALLINGSIGNLOCK_WRITE;
    if (HAL_HRTIM_DeadTimeConfig(&hhrtim1, s_timidx[leg], &dt) != HAL_OK) Error_Handler();

    /* output 1 (high side): set on the master event that resets this leg,
     * reset on own CMP1; output 2 comes from the dead-time generator */
    HRTIM_OutputCfgTypeDef out = {0};
    out.Polarity = HRTIM_OUTPUTPOLARITY_HIGH;        /* 1ED3140 IN+ active high */
    out.IdleMode = HRTIM_OUTPUTIDLEMODE_NONE;
    out.IdleLevel = HRTIM_OUTPUTIDLELEVEL_INACTIVE;  /* parked low */
    out.FaultLevel = HRTIM_OUTPUTFAULTLEVEL_INACTIVE;
    out.ChopperModeEnable = HRTIM_OUTPUTCHOPPERMODE_DISABLED;
    out.BurstModeEntryDelayed = HRTIM_OUTPUTBURSTMODEENTRY_REGULAR;
    out.SetSource = legB ? HRTIM_OUTPUTSET_MASTERCMP2 : HRTIM_OUTPUTSET_MASTERPER;
    out.ResetSource = HRTIM_OUTPUTRESET_TIMCMP1;
    if (HAL_HRTIM_WaveformOutputConfig(&hhrtim1, s_timidx[leg], s_out1[leg], &out) != HAL_OK) Error_Handler();
    if (HAL_HRTIM_WaveformOutputConfig(&hhrtim1, s_timidx[leg], s_out2[leg], &out) != HAL_OK) Error_Handler();
  }

  /* transfer preload -> active now, while the counters are stopped */
  if (HAL_HRTIM_SoftwareUpdate(&hhrtim1, HRTIM_TIMERUPDATE_MASTER | HRTIM_TIMERUPDATE_A | HRTIM_TIMERUPDATE_B |
                                             HRTIM_TIMERUPDATE_C | HRTIM_TIMERUPDATE_D) != HAL_OK) Error_Handler();

  /* outputs disabled, pins to HRTIM (idle low), counters running, tick IRQ on */
  HRTIM1->sCommonRegs.ODISR = HRTIM_ALL_OUTPUTS;
  s_enabled = 0U;
  hw_pins_to_hrtim();
  __HAL_HRTIM_MASTER_CLEAR_IT(&hhrtim1, HRTIM_MASTER_IT_MREP);
  __HAL_HRTIM_MASTER_ENABLE_IT(&hhrtim1, HRTIM_MASTER_IT_MREP);
  HAL_NVIC_SetPriority(HRTIM1_Master_IRQn, 1, 0);
  HAL_NVIC_EnableIRQ(HRTIM1_Master_IRQn);
  if (HAL_HRTIM_WaveformCountStart(&hhrtim1, HRTIM_TIMERID_MASTER | HRTIM_TIMERID_TIMER_A | HRTIM_TIMERID_TIMER_B |
                                                 HRTIM_TIMERID_TIMER_C | HRTIM_TIMERID_TIMER_D) != HAL_OK) Error_Handler();
}

void hw_set_duty(uint8_t leg, float d)
{
  if (leg >= HW_N_LEG) return;
  if (d < HW_DUTY_MIN) d = HW_DUTY_MIN;
  if (d > HW_DUTY_MAX) d = HW_DUTY_MAX;
  s_duty[leg] = d;
  hhrtim1.Instance->sTimerxRegs[s_timidx[leg]].CMP1xR = duty_to_cmp(d);  /* preload */
}

float hw_get_duty(uint8_t leg)
{
  return (leg < HW_N_LEG) ? s_duty[leg] : 0.5f;
}

void hw_legs_enable(uint8_t mask)
{
  uint32_t en = 0U, dis = 0U;
  uint8_t leg;
  mask &= HW_LEGS_ALL;
  for (leg = 0U; leg < HW_N_LEG; leg++)
  {
    if (mask & (1U << leg)) en |= s_outputs[leg]; else dis |= s_outputs[leg];
  }
  __disable_irq();
  s_pending_en = 0U;                       /* supersedes a pending hw_legs_enable_sync() */
  HRTIM1->sMasterRegs.MDIER &= ~HRTIM_MDIER_MCMP1IE;
  if (dis) HRTIM1->sCommonRegs.ODISR = dis;
  if (en)  HRTIM1->sCommonRegs.OENR = en;
  s_enabled = mask;
  __enable_irq();
}

void hw_legs_enable_sync(uint8_t mask)
{
  uint32_t dis = 0U;
  uint8_t leg;
  mask &= HW_LEGS_ALL;
  for (leg = 0U; leg < HW_N_LEG; leg++)
  {
    if (!(mask & (1U << leg))) dis |= s_outputs[leg];
  }
  __disable_irq();
  if (dis) HRTIM1->sCommonRegs.ODISR = dis;
  s_enabled &= mask;
  s_pending_en = mask;
  s_en_tries = 0U;
  HRTIM1->sMasterRegs.MICR = HRTIM_MICR_MCMP1;
  if (mask) HRTIM1->sMasterRegs.MDIER |= HRTIM_MDIER_MCMP1IE;
  __enable_irq();
}

uint8_t hw_legs_enabled(void)
{
  return s_enabled;
}

void hw_outputs_off(void)
{
  s_pending_en = 0U;                       /* cancels a synchronised enable still waiting for its window */
  if (__HAL_RCC_HRTIM1_IS_CLK_ENABLED())
  {
    HRTIM1->sMasterRegs.MDIER &= ~HRTIM_MDIER_MCMP1IE;
    HRTIM1->sCommonRegs.ODISR = HRTIM_ALL_OUTPUTS;
  }
  s_enabled = 0U;
  gates_low();
}

__attribute__((weak)) void hw_ctrl_tick_callback(void)
{
}

void hw_master_irq(void)
{
  if (HRTIM1->sMasterRegs.MISR & HRTIM_MISR_MREP)
  {
    HRTIM1->sMasterRegs.MICR = HRTIM_MICR_MREP;
    hw_ctrl_tick_callback();
  }
  if ((HRTIM1->sMasterRegs.MDIER & HRTIM_MDIER_MCMP1IE) && (HRTIM1->sMasterRegs.MISR & HRTIM_MISR_MCMP1))
  {
    HRTIM1->sMasterRegs.MICR = HRTIM_MICR_MCMP1;
    /* atomic against hw_outputs_off() from a higher-priority trip (E-stop EXTI) */
    __disable_irq();
    uint32_t cnt = HRTIM1->sMasterRegs.MCNTR;
    uint8_t mask = s_pending_en;
    if (mask && ((cnt >= HW_EN_CMP && cnt < HW_EN_CMP + HW_EN_WINDOW) || ++s_en_tries >= HW_EN_TRIES))
    {
      uint32_t en = 0U;
      uint8_t leg;
      for (leg = 0U; leg < HW_N_LEG; leg++)
      {
        if (mask & (1U << leg)) en |= s_outputs[leg];
      }
      HRTIM1->sCommonRegs.OENR = en;
      s_enabled = mask;
      s_pending_en = 0U;
    }
    if (!s_pending_en) HRTIM1->sMasterRegs.MDIER &= ~HRTIM_MDIER_MCMP1IE;
    __enable_irq();
  }
}
