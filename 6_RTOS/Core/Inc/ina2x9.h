/**
  * @file    ina2x9.h
  * @brief   INA239 / INA229 bus-voltage monitors on SPI3 (three chip selects).
  */
#ifndef __INA2X9_H__
#define __INA2X9_H__

#ifdef __cplusplus
extern "C" {
#endif

#include "main.h"

#define INA_COUNT   3

typedef enum
{
  INA_ABSENT = 0,   /* no TI manufacturer ID read back */
  INA_239,          /* 16-bit, VBUS 3.125 mV/LSB        */
  INA_229,          /* 20-bit, VBUS 195.3125 uV/LSB     */
  INA_UNKNOWN       /* TI part answered, unrecognised device ID: raw IDs only */
} INA_Kind;

typedef struct
{
  INA_Kind kind;
  uint16_t mfr_id;      /* register 3Eh, expect 0x5449 ("TI") */
  uint16_t dev_id;      /* register 3Fh                        */
  int32_t  vbus_mV;
  int16_t  temp_C;
} INA_Dev;

/* Index 0 = CS1 (U12, PV3+ to GND), 1 = CS2 (U11, PV2+ to GND),
   2 = CS3 (U10 behind the ISO7762, PV1+ to PV3+). */
void           INA_Init(void);          /* call once before INA_Poll(): checks that the SPI bus is free */
uint8_t        INA_BusBlocked(void);    /* 1: another driver holds the bus, read-out disabled */
void           INA_Poll(void);          /* probe absent devices (1 Hz), read the rest */
const INA_Dev *INA_Get(uint8_t index);
const char    *INA_KindName(INA_Kind kind);

#ifdef __cplusplus
}
#endif

#endif /* __INA2X9_H__ */
