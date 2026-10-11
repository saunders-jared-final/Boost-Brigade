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
 */
#ifndef SHUFFLER_HW_H
#define SHUFFLER_HW_H

#include <stdbool.h>
#include <stdint.h>

#define HW_PWM_HZ        100000U
#define HW_HRTIM_PER     54400U          /* 5.44 GHz / 100 kHz (prescaler MUL32 on 170 MHz) */
#define HW_CTRL_DIV      10U             /* control tick = 10 kHz */
#define HW_DEADTIME_NS   200U
#define HW_N_LEG         4U
#define HW_LEGS_S1       0x03U
#define HW_LEGS_S2       0x0CU
#define HW_LEGS_ALL      0x0FU
#define HW_DUTY_MIN      0.05f
#define HW_DUTY_MAX      0.95f

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
