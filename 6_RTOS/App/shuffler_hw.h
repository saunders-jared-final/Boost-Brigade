/**
 * shuffler_hw.h - power-stage hardware layer for the Version 0 shuffler board
 *
 * HRTIM1 drives the four half-bridge legs (two per converter) with
 * complementary outputs and 200 ns hardware dead time:
 *   leg 0 = S1 A  PA8/PA9    HRTIM TA1/TA2
 *   leg 1 = S1 B  PA10/PA11  HRTIM TB1/TB2
 *   leg 2 = S2 A  PB12/PB13  HRTIM TC1/TC2
 *   leg 3 = S2 B  PB14/PB15  HRTIM TD1/TD2
 * The master timer runs at the PWM frequency; A legs are reset (and set) on
 * the master period, B legs on master CMP2 = PER/2, so the two legs of a
 * converter interleave at 180 deg for any duty. Each leg's duty is its own
 * CMP1 (preloaded, applied on the next reset: glitch free).
 * The master repetition interrupt (every HW_CTRL_DIV periods) is the control
 * tick: hw_ctrl_tick_callback() is called from it at HW_PWM_HZ / HW_CTRL_DIV.
 *
 * Hall sampling: HRTIM ADC trigger 1 fires four times per PWM period, evenly
 * spaced at PER/8 + k*PER/4 (timer A CMP3/CMP4 and timer B CMP3/CMP4; A resets
 * on the master period, B on master CMP2 = PER/2). The samples sit a quarter
 * period from the switching edges at d ~ 0.5, and averaging four equally spaced
 * samples per period nulls the ripple at fsw, 2fsw and 3fsw (see sensors.c).
 */
#ifndef SHUFFLER_HW_H
#define SHUFFLER_HW_H

#include <stdbool.h>
#include <stdint.h>

/* PWM frequency build option (HW_PWM_KHZ 200 or 300; 7_Pi/deploy/stage_firmware.sh builds both images).
 * 300 kHz: 5.44 GHz / 300 kHz = 18133.3 -> 18133 counts = 299.99 kHz, 30 periods per 100 us control tick
 * (99.998 us, 0.002 % off CTRL_TS). The hall ADC does its two ranks in 0.71 us (PCLK/4, 2.5-cycle sample)
 * against a 0.83 us trigger spacing. 16 Oct 2026: 300 kHz open loop fine, closed loop hung the firmware
 * within the first control ticks (IWDG reset, bridge unsupervised): keep 200 kHz until the trace says why. */
#ifndef HW_PWM_KHZ
#define HW_PWM_KHZ       200
#endif
#if HW_PWM_KHZ == 400
/* 400 kHz: PER 13600 exact, 40 periods per tick. The hall ADC trigger spacing is 0.625 us: the two-rank sequence
 * needs the ADCs on the PLL P output (340 MHz / 6 = 56.7 MHz, limit 60 MHz; 0.53 us) instead of PCLK/4 (0.71 us):
 * main.c / adc.c switch the clock on HW_PWM_KHZ >= 400. Dead time 200 ns = 8 %: duty floor 0.12, ceiling 0.88. */
#define HW_PWM_HZ        400000U
#define HW_HRTIM_PER     13600U          /* 5.44 GHz / 400 kHz (prescaler MUL32 on 170 MHz) */
#define HW_CTRL_DIV      40U             /* control tick = 400 kHz / 40 = 10 kHz */
#elif HW_PWM_KHZ == 300
#define HW_PWM_HZ        300000U
#define HW_HRTIM_PER     18133U          /* 5.44 GHz / 300 kHz (prescaler MUL32 on 170 MHz) */
#define HW_CTRL_DIV      30U             /* control tick = 300 kHz / 30 = 10 kHz */
#else
#define HW_PWM_HZ        200000U
#define HW_HRTIM_PER     27200U          /* 5.44 GHz / 200 kHz (prescaler MUL32 on 170 MHz) */
#define HW_CTRL_DIV      20U             /* control tick = 200 kHz / 20 = 10 kHz */
#endif
#define HW_ADC_TRIG_PER_PERIOD 4U        /* hall ADC triggers per PWM period (sensors.c) */
#define HW_DEADTIME_NS   100U            /* 16 Oct 2026: 200 -> 100 ns at 400 kHz (4 % of the period) */
#define HW_DEADTIME_STEPS ((HW_DEADTIME_NS * 1000U + 367U) / 735U)   /* dead-time generator step 0.735 ns (DTPRSC 000 at 5.44 GHz) */
#define HW_N_LEG         4U
#define HW_LEGS_S1       0x03U
#define HW_LEGS_S2       0x0CU
#define HW_LEGS_ALL      0x0FU
#if HW_PWM_KHZ == 400
#define HW_DUTY_MIN      0.12f           /* 300 ns on-time at 400 kHz against the 200 ns dead time */
#define HW_DUTY_MAX      0.88f           /* 300 ns low-side on-time for the bootstrap refresh */
#elif HW_PWM_KHZ == 300
#define HW_DUTY_MIN      0.08f           /* 267 ns on-time at 300 kHz against the 200 ns dead time */
#define HW_DUTY_MAX      0.95f
#else
#define HW_DUTY_MIN      0.05f           /* 250 ns on-time at 200 kHz */
#define HW_DUTY_MAX      0.95f
#endif

/* Configure HRTIM (master + four timers), hand the eight gate pins to the
 * HRTIM, start all counters with every output disabled, enable the control
 * tick interrupt. Call after MX_HRTIM1_Init(). */
void hw_init(void);

/* Duty for one leg (high-side on-time fraction), clamped to [MIN, MAX];
 * lands in the preload register, active on the leg's next reset. ISR-safe. */
void hw_set_duty(uint8_t leg, float d);
float hw_get_duty(uint8_t leg);

/* Enable exactly the legs in mask (bit per leg), all others disabled. */
void hw_legs_enable(uint8_t mask);

/* Same, but the legs in mask switch on at the next quarter PWM period (master CMP1, in the master IRQ):
 * centred first pulse, no start-up offset in the circulating current. Legs outside mask go off now.
 * hw_outputs_off() cancels a pending enable. */
void hw_legs_enable_sync(uint8_t mask);
uint8_t hw_legs_enabled(void);

/* Everything off, any context, no HAL: outputs disabled, gate pins driven low. */
void hw_outputs_off(void);

/* Re-hand the gate pins to the HRTIM after hw_outputs_off() (outputs stay disabled). */
void hw_pins_to_hrtim(void);

/* Called from the HRTIM master repetition interrupt at the control rate. */
void hw_ctrl_tick_callback(void);

/* Interrupt entry (wire from HRTIM1_Master_IRQHandler). */
void hw_master_irq(void);

#endif /* SHUFFLER_HW_H */
