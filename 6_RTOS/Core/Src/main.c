/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "adc.h"
#include "hrtim.h"
#include "spi.h"
#include "gpio.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include "sensors.h"
#include "ina2x9.h"

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */
typedef enum { APP_IDLE = 0, APP_RUN, APP_FAULT } App_State;

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define S2_HRTIM_OUTPUTS    (HRTIM_OUTPUT_TC1 | HRTIM_OUTPUT_TC2 | HRTIM_OUTPUT_TD1 | HRTIM_OUTPUT_TD2)
#define S2_HRTIM_TIMERS     (HRTIM_TIMERID_TIMER_C | HRTIM_TIMERID_TIMER_D)
#define S2_GATE_PINS        (S2_A_H_Pin | S2_A_L_Pin | S2_B_H_Pin | S2_B_L_Pin)
#define S1_GATE_PINS        (S1_A_H_Pin | S1_A_L_Pin | S1_B_H_Pin | S1_B_L_Pin)

#define TELEMETRY_PERIOD_MS 100U
#define BUTTON_DEBOUNCE_MS  250U
#define FAULT_BLINK_MS      100U
#define FAULT_REPEAT_MS     5000U   /* the fault message is printed again at this interval */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

COM_InitTypeDef BspCOMInit;

/* USER CODE BEGIN PV */
static App_State        app_state = APP_IDLE;
static volatile uint8_t button_pressed;

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
/* USER CODE BEGIN PFP */
static void Shuffler_HRTIM_Config(void);
static void Shuffler_PWM_Start(void);
static void Shuffler_PWM_Stop(void);
static void Shuffler_GatesLow(void);
static void Shuffler_EmergencyStop(void);
static void Print_Banner(void);
static void Print_Telemetry(void);
static void Print_Fault(void);
/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

/* Each gate-drive line feeds a 1ED3140 IN+ (pull-down) and the opposite
   driver's IN- (pull-up), so a floating MCU pin sits mid-rail and the driver
   state is undefined. Drive all eight lines low as early as the C runtime
   allows: this runs from __libc_init_array(), before main() and therefore
   also before the breakpoint of a "halt at main" debug session. */
static void __attribute__((constructor)) Shuffler_GatesLowAtBoot(void)
{
  Shuffler_GatesLow();
}

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */
  /* Already done by Shuffler_GatesLowAtBoot(); repeated so that main() does
     not depend on it. PA8..PA11 (Shuffler 1) stay GPIO-low for the whole
     test; PB12..PB15 (Shuffler 2) are handed to the HRTIM later, whose
     disabled outputs idle low. */
  Shuffler_GatesLow();

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_HRTIM1_Init();
  MX_ADC1_Init();
  MX_ADC2_Init();
  MX_SPI3_Init();
  /* USER CODE BEGIN 2 */
  Shuffler_HRTIM_Config();
  /* USER CODE END 2 */

  /* Initialize led */
  BSP_LED_Init(LED_GREEN);

  /* Initialize USER push-button, will be used to trigger an interrupt each time it's pressed.*/
  BSP_PB_Init(BUTTON_USER, BUTTON_MODE_EXTI);

  /* Initialize COM1 port (115200, 8 bits (7-bit data + 1 stop bit), no parity */
  BspCOMInit.BaudRate   = 115200;
  BspCOMInit.WordLength = COM_WORDLENGTH_8B;
  BspCOMInit.StopBits   = COM_STOPBITS_1;
  BspCOMInit.Parity     = COM_PARITY_NONE;
  BspCOMInit.HwFlowCtl  = COM_HWCONTROL_NONE;
  if (BSP_COM_Init(COM1, &BspCOMInit) != BSP_ERROR_NONE)
  {
    Error_Handler();
  }

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  Sensors_Init();
  INA_Init();
  INA_Poll();
  Print_Banner();

  uint32_t last_telemetry = HAL_GetTick();
  uint32_t last_button    = 0;
  uint32_t last_fault_msg = 0;

  button_pressed = 0;   /* ignore anything latched while booting */

  while (1)
  {
    uint32_t now     = HAL_GetTick();
    uint8_t  pressed = 0;

    /* Take the press and clear the flag in the same place. Clearing it
       unconditionally after the test erased every press whose interrupt
       landed between the two: about one press in seven. */
    if (button_pressed)
    {
      button_pressed = 0;
      pressed = 1;
    }

    if (Sensors_FaultLatched())
    {
      if (app_state != APP_FAULT)
      {
        /* The SysTick handler has already disabled the outputs. */
        Shuffler_PWM_Stop();
        Shuffler_GatesLow();
        app_state = APP_FAULT;
        Print_Fault();
        last_fault_msg = now;
      }
      else if ((now - last_fault_msg) >= FAULT_REPEAT_MS)
      {
        /* So that a terminal opened after the trip still shows the cause. */
        Print_Fault();
        last_fault_msg = now;
      }
      if ((now / FAULT_BLINK_MS) & 1U)
      {
        BSP_LED_On(LED_GREEN);
      }
      else
      {
        BSP_LED_Off(LED_GREEN);
      }
    }
    else if (pressed && (now - last_button) >= BUTTON_DEBOUNCE_MS)
    {
      if (app_state != APP_IDLE)
      {
        last_button = now;
        Shuffler_PWM_Stop();
      }
      /* Start only on a real press: B1 must still be held when the edge is
         handled (at most ~10 ms later), so a glitch on PC13 or the contact
         chatter of a release cannot start the converter. */
      else if (BSP_PB_GetState(BUTTON_USER) == (int32_t)BUTTON_PRESSED)
      {
        last_button = now;
        Shuffler_PWM_Start();
      }
    }

    if ((now - last_telemetry) >= TELEMETRY_PERIOD_MS)
    {
      last_telemetry = now;
      INA_Poll();
      Print_Telemetry();
    }
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1_BOOST);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSI;
  RCC_OscInitStruct.PLL.PLLM = RCC_PLLM_DIV4;
  RCC_OscInitStruct.PLL.PLLN = 85;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
  RCC_OscInitStruct.PLL.PLLQ = RCC_PLLQ_DIV2;
  RCC_OscInitStruct.PLL.PLLR = RCC_PLLR_DIV2;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_4) != HAL_OK)
  {
    Error_Handler();
  }
}

/* USER CODE BEGIN 4 */

/**
  * @brief  Configure the four Shuffler 2 gate-drive PWM outputs on HRTIM1.
  *
  *   PB12 = HRTIM1_CHC1 (S2 leg A high side)   PB13 = HRTIM1_CHC2 (S2 leg A low side)
  *   PB14 = HRTIM1_CHD1 (S2 leg B high side)   PB15 = HRTIM1_CHD2 (S2 leg B low side)
  *
  * 100 kHz, fixed 50 % duty on both legs, leg B inverted with respect to leg A
  * (180 deg at 50 % duty), 200 ns hardware dead time from the HRTIM dead-time
  * generator. Called once from main() after MX_HRTIM1_Init(); it deliberately
  * overrides the placeholder time base / timer / output settings that CubeMX
  * generates in MX_HRTIM1_Init(). Nothing switches until Shuffler_PWM_Start().
  * @retval None
  */
static void Shuffler_HRTIM_Config(void)
{
  /* Register-write ORDER matters on the HRTIM. Once PREEN is set in TIMxCR,
     writes to PERxR / CMPxR / SETxR / RSTxR (and DTxR) land in the *preload*
     registers and only reach the active registers on an update event.
     HAL_HRTIM_WaveformTimerConfig() enables the preload AND forces one
     software update as it returns, so it must be the first call here; every
     value written after it is then transferred by the explicit
     HAL_HRTIM_SoftwareUpdate() in step 6, before the counters are enabled.

     (The earlier version of this function ran the timer config after the
     time base but before the compare / dead-time / output-crossbar writes,
     with no update trigger selected, so those values never left the preload
     registers: the active SETx1R stayed 0, the outputs were never set, and
     the pins stayed flat.) */

  /* ---- 1. Timer unit: preload, dead time, update on roll-over ------- */
  HRTIM_TimerCfgTypeDef tim = {0};
  tim.DMARequests           = HRTIM_TIM_DMA_NONE;
  tim.HalfModeEnable        = HRTIM_HALFMODE_DISABLED;
  tim.StartOnSync           = HRTIM_SYNCSTART_DISABLED;
  tim.ResetOnSync           = HRTIM_SYNCRESET_DISABLED;
  tim.DACSynchro            = HRTIM_DACSYNC_NONE;
  tim.PreloadEnable         = HRTIM_PRELOAD_ENABLED;
  tim.UpdateGating          = HRTIM_UPDATEGATING_INDEPENDENT;
  tim.BurstMode             = HRTIM_TIMERBURSTMODE_MAINTAINCLOCK;
  tim.RepetitionUpdate      = HRTIM_UPDATEONREPETITION_DISABLED;
  tim.PushPull              = HRTIM_TIMPUSHPULLMODE_DISABLED;
  tim.FaultEnable           = HRTIM_TIMFAULTENABLE_NONE;
  tim.FaultLock             = HRTIM_TIMFAULTLOCK_READWRITE;
  tim.DeadTimeInsertion     = HRTIM_TIMDEADTIMEINSERTION_ENABLED;
  tim.DelayedProtectionMode = HRTIM_TIMER_A_B_C_DELAYEDPROTECTION_DISABLED;
  tim.UpdateTrigger         = HRTIM_TIMUPDATETRIGGER_NONE;
  tim.ResetTrigger          = HRTIM_TIMRESETTRIGGER_NONE;
  /* Preload -> active at every period roll-over: a later change to CMP1
     (duty) is applied glitch-free on a period boundary, with no software
     update needed. */
  tim.ResetUpdate           = HRTIM_TIMUPDATEONRESET_ENABLED;
  if (HAL_HRTIM_WaveformTimerConfig(&hhrtim1, HRTIM_TIMERINDEX_TIMER_C, &tim) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_HRTIM_WaveformTimerConfig(&hhrtim1, HRTIM_TIMERINDEX_TIMER_D, &tim) != HAL_OK)
  {
    Error_Handler();
  }

  /* ---- 2. Time base: identical for both legs ---------------------- */
  HRTIM_TimeBaseCfgTypeDef tb = {0};
  tb.Period            = 54400;        /* 5.44 GHz / 100 kHz */
  tb.RepetitionCounter = 0;
  tb.PrescalerRatio    = HRTIM_PRESCALERRATIO_MUL32;   /* 184 ps steps */
  tb.Mode              = HRTIM_MODE_CONTINUOUS;
  if (HAL_HRTIM_TimeBaseConfig(&hhrtim1, HRTIM_TIMERINDEX_TIMER_C, &tb) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_HRTIM_TimeBaseConfig(&hhrtim1, HRTIM_TIMERINDEX_TIMER_D, &tb) != HAL_OK)
  {
    Error_Handler();
  }

  /* ---- 3. Duty: 50 % on both legs -------------------------------- */
  HRTIM_CompareCfgTypeDef cmp = {0};
  cmp.CompareValue = 27200;                    /* PER / 2 */
  if (HAL_HRTIM_WaveformCompareConfig(&hhrtim1, HRTIM_TIMERINDEX_TIMER_C,
                                      HRTIM_COMPAREUNIT_1, &cmp) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_HRTIM_WaveformCompareConfig(&hhrtim1, HRTIM_TIMERINDEX_TIMER_D,
                                      HRTIM_COMPAREUNIT_1, &cmp) != HAL_OK)
  {
    Error_Handler();
  }

  /* ---- 4. Dead time: 272 x 0.735 ns = 200 ns, both edges ---------- */
  /* DTPRSC must be 000, i.e. tDTG = tHRTIM / 8 = 5.882 ns / 8 = 0.735 ns.
     On this HAL package the macro encoding DTPRSC = 000 is
     ..._PRESCALERRATIO_MUL8; ..._PRESCALERRATIO_DIV8 encodes DTPRSC = 110
     (DTPRSC_2 | DTPRSC_1), i.e. tDTG = tHRTIM * 8 = 47.06 ns. See
     stm32g4xx_hal_hrtim.h lines 1631-1638. The register value, not the macro
     name, is what is being pinned here. */
  HRTIM_DeadTimeCfgTypeDef dt = {0};
  dt.Prescaler       = HRTIM_TIMDEADTIME_PRESCALERRATIO_MUL8;  /* = DTPRSC 000 */
  dt.RisingValue     = 272;
  dt.RisingSign      = HRTIM_TIMDEADTIME_RISINGSIGN_POSITIVE;
  dt.RisingLock      = HRTIM_TIMDEADTIME_RISINGLOCK_WRITE;
  dt.RisingSignLock  = HRTIM_TIMDEADTIME_RISINGSIGNLOCK_WRITE;
  dt.FallingValue    = 272;
  dt.FallingSign     = HRTIM_TIMDEADTIME_FALLINGSIGN_POSITIVE;
  dt.FallingLock     = HRTIM_TIMDEADTIME_FALLINGLOCK_WRITE;
  dt.FallingSignLock = HRTIM_TIMDEADTIME_FALLINGSIGNLOCK_WRITE;
  if (HAL_HRTIM_DeadTimeConfig(&hhrtim1, HRTIM_TIMERINDEX_TIMER_C, &dt) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_HRTIM_DeadTimeConfig(&hhrtim1, HRTIM_TIMERINDEX_TIMER_D, &dt) != HAL_OK)
  {
    Error_Handler();
  }

  /* ---- 5. Outputs. Only output 1 of each leg is defined;          */
  /*        TC2 / TD2 are produced by the dead-time generator.       */
  HRTIM_OutputCfgTypeDef out = {0};
  out.Polarity              = HRTIM_OUTPUTPOLARITY_HIGH;   /* 1ED3140 IN+ is active high */
  out.IdleMode              = HRTIM_OUTPUTIDLEMODE_NONE;
  out.IdleLevel             = HRTIM_OUTPUTIDLELEVEL_INACTIVE;  /* park low */
  out.FaultLevel            = HRTIM_OUTPUTFAULTLEVEL_NONE;
  out.ChopperModeEnable     = HRTIM_OUTPUTCHOPPERMODE_DISABLED;
  out.BurstModeEntryDelayed = HRTIM_OUTPUTBURSTMODEENTRY_REGULAR;

  /* Leg A: high at the period roll-over, low at 50 % */
  out.SetSource   = HRTIM_OUTPUTSET_TIMPER;
  out.ResetSource = HRTIM_OUTPUTRESET_TIMCMP1;
  if (HAL_HRTIM_WaveformOutputConfig(&hhrtim1, HRTIM_TIMERINDEX_TIMER_C,
                                     HRTIM_OUTPUT_TC1, &out) != HAL_OK)
  {
    Error_Handler();
  }
  /* TC2: set/reset sources are ignored while dead time is on, but configure
     it so its polarity and idle level are defined. */
  if (HAL_HRTIM_WaveformOutputConfig(&hhrtim1, HRTIM_TIMERINDEX_TIMER_C,
                                     HRTIM_OUTPUT_TC2, &out) != HAL_OK)
  {
    Error_Handler();
  }

  /* Leg B: the mirror image -> 180 deg at exactly 50 % duty */
  out.SetSource   = HRTIM_OUTPUTSET_TIMCMP1;
  out.ResetSource = HRTIM_OUTPUTRESET_TIMPER;
  if (HAL_HRTIM_WaveformOutputConfig(&hhrtim1, HRTIM_TIMERINDEX_TIMER_D,
                                     HRTIM_OUTPUT_TD1, &out) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_HRTIM_WaveformOutputConfig(&hhrtim1, HRTIM_TIMERINDEX_TIMER_D,
                                     HRTIM_OUTPUT_TD2, &out) != HAL_OK)
  {
    Error_Handler();
  }

  /* ---- 6. Transfer preload -> active NOW, while the counters are still */
  /*        stopped, so the very first period already runs with the      */
  /*        period / compare / dead-time / crossbar values above.         */
  if (HAL_HRTIM_SoftwareUpdate(&hhrtim1, HRTIM_TIMERUPDATE_C |
                                         HRTIM_TIMERUPDATE_D) != HAL_OK)
  {
    Error_Handler();
  }

}

/**
  * @brief  Start switching Shuffler 2. Both counters are enabled in one
  *         register write, so the legs start on the same clock edge and stay
  *         locked. Refused while the overcurrent latch is set.
  */
static void Shuffler_PWM_Start(void)
{
  HAL_StatusTypeDef st_out;
  HAL_StatusTypeDef st_cnt;

  if (Sensors_FaultLatched())
  {
    return;
  }
  /* Back to back with interrupts masked: a SysTick between the two calls
     would hold the bridge in one static state for as long as it runs. */
  __disable_irq();
  st_out = HAL_HRTIM_WaveformOutputStart(&hhrtim1, S2_HRTIM_OUTPUTS);
  st_cnt = HAL_HRTIM_WaveformCountStart(&hhrtim1, S2_HRTIM_TIMERS);
  __enable_irq();
  if (st_out != HAL_OK || st_cnt != HAL_OK)
  {
    Error_Handler();
  }
  BSP_LED_On(LED_GREEN);
  app_state = APP_RUN;
}

/**
  * @brief  Stop switching: outputs to their idle (low) level, counters stopped.
  */
static void Shuffler_PWM_Stop(void)
{
  if (HAL_HRTIM_WaveformOutputStop(&hhrtim1, S2_HRTIM_OUTPUTS) != HAL_OK)
  {
    Error_Handler();
  }
  if (HAL_HRTIM_WaveformCountStop(&hhrtim1, S2_HRTIM_TIMERS) != HAL_OK)
  {
    Error_Handler();
  }
  BSP_LED_Off(LED_GREEN);
  if (app_state == APP_RUN)
  {
    app_state = APP_IDLE;
  }
}

/**
  * @brief  Drive all eight gate-drive lines low as plain GPIO: PA8..PA11 stay
  *         that way, PB12..PB15 are taken away from the HRTIM. Register
  *         writes only, so it works before HAL_Init() and in Error_Handler().
  */
static void Shuffler_GatesLow(void)
{
  RCC->AHB2ENR |= RCC_AHB2ENR_GPIOAEN | RCC_AHB2ENR_GPIOBEN;
  (void)RCC->AHB2ENR;
  GPIOA->BRR = S1_GATE_PINS;
  GPIOB->BRR = S2_GATE_PINS;
  MODIFY_REG(GPIOA->MODER, GPIO_MODER_MODE8 | GPIO_MODER_MODE9 | GPIO_MODER_MODE10 | GPIO_MODER_MODE11,
             GPIO_MODER_MODE8_0 | GPIO_MODER_MODE9_0 | GPIO_MODER_MODE10_0 | GPIO_MODER_MODE11_0);
  MODIFY_REG(GPIOB->MODER, GPIO_MODER_MODE12 | GPIO_MODER_MODE13 | GPIO_MODER_MODE14 | GPIO_MODER_MODE15,
             GPIO_MODER_MODE12_0 | GPIO_MODER_MODE13_0 | GPIO_MODER_MODE14_0 | GPIO_MODER_MODE15_0);
}

/**
  * @brief  Switch the power stage off from any context, without the HAL:
  *         disable every HRTIM output (they fall to their idle level, low),
  *         then drive the gate lines low as GPIO.
  */
static void Shuffler_EmergencyStop(void)
{
  if (__HAL_RCC_HRTIM1_IS_CLK_ENABLED())
  {
    HRTIM1->sCommonRegs.ODISR = HRTIM_ALL_OUTPUTS;
  }
  Shuffler_GatesLow();
}

/* Why the protection latched. A code at an ADC rail is a signal fault (sensor
   unpowered, pin open), not a measured current, and is reported as such. */
static void Print_Fault(void)
{
  const char *name = Sensors_Name(Sensors_FaultChannel());

  if (Sensors_FaultRailed())
  {
    printf("\r\n*** FAULT: %s signal out of range (ADC code %u): sensor unpowered or not connected? "
           "PWM latched off, reset the MCU to clear. ***\r\n\r\n", name, (unsigned)Sensors_FaultRaw());
  }
  else
  {
    printf("\r\n*** FAULT: overcurrent on %s (%ld mA, limit %d mA for %d ms). "
           "PWM latched off, reset the MCU to clear. ***\r\n\r\n",
           name, (long)Sensors_FaultCurrent_mA(), SENSE_OC_LIMIT_MA, SENSE_OC_TIME_MS);
  }
}

static void Print_Banner(void)
{
  printf("\r\n=== Shuffler open-loop test: Shuffler 2 (PB12-PB15), 100 kHz, 50 %% ===\r\n");
  printf("Shuffler 1 gates (PA8-PA11) held low. Overcurrent latch: %d mA for %d ms.\r\n",
         SENSE_OC_LIMIT_MA, SENSE_OC_TIME_MS);
  for (int ch = 0; ch < SENSE_COUNT; ch++)
  {
    if (!Sensors_ZeroOk((Sense_Channel)ch))
    {
      printf("WARNING: %s zero-current output is not near 1.65 V (sensor unpowered or pin open?)\r\n",
             Sensors_Name((Sense_Channel)ch));
    }
  }
  for (uint8_t i = 0; i < INA_COUNT; i++)
  {
    const INA_Dev *d = INA_Get(i);
    printf("INA CS%u: %s (MFR 0x%04X, DEV 0x%04X)\r\n", (unsigned)(i + 1U), INA_KindName(d->kind),
           (unsigned)d->mfr_id, (unsigned)d->dev_id);
  }
  if (INA_BusBlocked())
  {
    printf("WARNING: SPI MOSI is held high by another driver (isolator U13 fitted with its channels reversed?). "
           "INA read-out disabled and the SPI pins released.\r\n");
  }
  printf("V1 = PV3+ to GND, V2 = PV2+ to GND, V3 = PV1+ to PV3+.\r\n");
  printf("Press B1 (blue button) to start / stop PWM.\r\n");
  printf("LD2: off = idle, on = PWM running, fast even blink = protection latched (see the FAULT message), "
         "double flash = firmware error.\r\n\r\n");
}

/* One line per call, all integers (newlib-nano printf has no float support):
   state, the four hall currents in mA, then per INA the bus voltage in mV and
   die temperature in degC ("----" = device not answering). */
static void Print_Telemetry(void)
{
  static const char *const state_name[] = { "IDLE ", "RUN  ", "FAULT" };

  printf("%s S2 IA=%6ld IB=%6ld | S1 IA=%6ld IB=%6ld mA |", state_name[app_state],
         (long)Sensors_Current_mA(SENSE_ILA_2), (long)Sensors_Current_mA(SENSE_ILB_2),
         (long)Sensors_Current_mA(SENSE_ILA_1), (long)Sensors_Current_mA(SENSE_ILB_1));
  for (uint8_t i = 0; i < INA_COUNT; i++)
  {
    const INA_Dev *d = INA_Get(i);
    if (d->kind == INA_239 || d->kind == INA_229)
    {
      printf(" V%u=%6ld mV %3dC", (unsigned)(i + 1U), (long)d->vbus_mV, (int)d->temp_C);
    }
    else
    {
      printf(" V%u=  ----        ", (unsigned)(i + 1U));
    }
  }
  printf("\r\n");
}

/**
  * @brief  B1 press (EXTI, called from BSP_PB_IRQHandler). Handled in the main loop.
  */
void BSP_PB_Callback(Button_TypeDef Button)
{
  if (Button == BUTTON_USER)
  {
    button_pressed = 1;
  }
}

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* Reached from a failed HAL call and from the CPU fault handlers. The
     overcurrent latch and the button both live in interrupts, which stop
     here, so the power stage must not be left switching. */
  __disable_irq();
  Shuffler_EmergencyStop();

  /* LD2 (PA5): two short flashes, then a pause - not the even 5 Hz blink of
     the overcurrent latch. Busy-wait delays: the tick no longer runs. */
  MODIFY_REG(GPIOA->MODER, GPIO_MODER_MODE5, GPIO_MODER_MODE5_0);
  while (1)
  {
    for (uint32_t step = 0; step < 10U; step++)
    {
      if (step == 0U || step == 2U)
      {
        GPIOA->BSRR = GPIO_PIN_5;
      }
      else
      {
        GPIOA->BRR = GPIO_PIN_5;
      }
      for (volatile uint32_t n = SystemCoreClock / 100U; n != 0U; n--)
      {
      }
    }
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
