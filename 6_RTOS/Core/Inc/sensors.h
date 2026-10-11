/**
  * @file    sensors.h
  * @brief   TMCS1126 hall-effect current sensing and over-current latch.
  *
  * Sampled at the control rate (hw control tick): Sensors_Tick() reads the
  * conversions started on the previous tick, converts, checks the latch and
  * starts the next sequence. Each conversion is 4x oversampled over ~10 us,
  * i.e. averaged over one 100 kHz switching period (the average inductor
  * current, not a point on the ripple).
  */
#ifndef __SENSORS_H__
#define __SENSORS_H__

#ifdef __cplusplus
extern "C" {
#endif

#include "main.h"

/* Channel order = control-core IL order {ILA1, ILB1, ILA2, ILB2}. Sign
 * convention: positive INTO the converter midpoint (toward the string node). */
typedef enum
{
  SENSE_ILA_1 = 0,   /* Shuffler 1, A phase, PA0 / ADC1_IN1  (TMCS1126B4, 100 mV/A) */
  SENSE_ILB_1,       /* Shuffler 1, B phase, PA4 / ADC2_IN17 (TMCS1126B1,  25 mV/A, reversed) */
  SENSE_ILA_2,       /* Shuffler 2, A phase, PA1 / ADC1_IN2  (TMCS1126B4, 100 mV/A) */
  SENSE_ILB_2,       /* Shuffler 2, B phase, PC1 / ADC2_IN7  (TMCS1126B1,  25 mV/A, reversed) */
  SENSE_COUNT
} Sense_Channel;

#define SENSE_OC_LIMIT_A    12.0f   /* over-current threshold |I| [A] (TMCS1126B4 range 15.5 A) */
#define SENSE_OC_TICKS      20      /* consecutive control ticks above the limit before latching (2 ms) */
#define SENSE_RAIL_TICKS    3       /* ADC code at a rail for this many ticks = signal fault */

void        Sensors_Init(void);
void        Sensors_Tick(void);                    /* call from the control ISR, before the controller */
float       Sensors_Current_A(Sense_Channel ch);   /* last sample, calibrated, control sign convention */
int32_t     Sensors_Current_mA(Sense_Channel ch);
uint8_t     Sensors_ZeroOk(Sense_Channel ch);      /* 0: zero-current offset was implausible at start-up */
uint8_t     Sensors_FaultLatched(void);
void        Sensors_ClearFault(void);              /* only after the outputs are off */
Sense_Channel Sensors_FaultChannel(void);
float       Sensors_FaultCurrent_A(void);
uint16_t    Sensors_FaultRaw(void);
uint8_t     Sensors_FaultRailed(void);
const char *Sensors_Name(Sense_Channel ch);
/* Calibration: gain [mV/A] (sign = sensor orientation) and ADC zero code. */
void        Sensors_SetCal(Sense_Channel ch, float mV_per_A, int16_t zero_code);
float       Sensors_Cal_mVperA(Sense_Channel ch);

#ifdef __cplusplus
}
#endif

#endif /* __SENSORS_H__ */
