/**
  * @file    sensors.h
  * @brief   TMCS1126 hall-effect current sensing and overcurrent latch.
  */
#ifndef __SENSORS_H__
#define __SENSORS_H__

#ifdef __cplusplus
extern "C" {
#endif

#include "main.h"

typedef enum
{
  SENSE_ILA_1 = 0,   /* Shuffler 1, A phase, PA0 / ADC1_IN1  (TMCS1126B4, 100 mV/A) */
  SENSE_ILA_2,       /* Shuffler 2, A phase, PA1 / ADC1_IN2  (TMCS1126B4, 100 mV/A) */
  SENSE_ILB_1,       /* Shuffler 1, B phase, PA4 / ADC2_IN17 (TMCS1126B1,  25 mV/A) */
  SENSE_ILB_2,       /* Shuffler 2, B phase, PC1 / ADC2_IN7  (TMCS1126B1,  25 mV/A) */
  SENSE_COUNT
} Sense_Channel;

#define SENSE_OC_LIMIT_MA   10000   /* overcurrent threshold, |I| in mA           */
#define SENSE_OC_TIME_MS    100     /* must persist this long before the latch    */

void        Sensors_Init(void);
void        Sensors_Tick1ms(void);                 /* call from SysTick_Handler   */
int32_t     Sensors_Current_mA(Sense_Channel ch);
uint8_t     Sensors_ZeroOk(Sense_Channel ch);      /* 0: zero-current offset was implausible at start-up */
uint8_t     Sensors_FaultLatched(void);
Sense_Channel Sensors_FaultChannel(void);
int32_t     Sensors_FaultCurrent_mA(void);
uint16_t    Sensors_FaultRaw(void);                /* ADC code of the sample that latched         */
uint8_t     Sensors_FaultRailed(void);             /* 1: that code was at a rail (signal fault, not a measured current) */
const char *Sensors_Name(Sense_Channel ch);

#ifdef __cplusplus
}
#endif

#endif /* __SENSORS_H__ */
