/**
  * @file    ina2x9.c
  * @brief   INA239 / INA229 bus-voltage monitors on SPI3 (three chip selects).
  *
  * The schematic shows INA229 while the datasheet kept with the project is
  * the INA239; the two share the SPI frame and register addresses but differ
  * in register width and scaling, so the part is identified from DEVICE_ID
  * and scaled accordingly.
  *
  * SPI mode 1, MSB first. First byte = (address << 2) | R/W (1 = read),
  * followed by 16 or 24 data bits. The only write is ADC_CONFIG: continuous
  * conversion with an 84 us bus-voltage conversion time (the 1052 us power-on
  * default is ~1 ms of measurement lag, which the 150 Hz voltage loop cannot
  * afford: QSPICE S9 rings with it). On this PCB the shunt inputs are tied
  * to GND, so only VBUS and DIETEMP carry information.
  */
#include "ina2x9.h"
#include "spi.h"

#define REG_ADC_CONFIG      0x01
#define REG_VBUS            0x05
#define REG_DIETEMP         0x06
#define REG_MANUFACTURER_ID 0x3E
#define REG_DEVICE_ID       0x3F

#define MANUFACTURER_ID_TI  0x5449
#define DIE_ID_INA239       0x239     /* DEVICE_ID[15:4] */
#define DIE_ID_INA229       0x229

#define PROBE_INTERVAL_MS   1000U
#define SPI_TIMEOUT_MS      5U

#define MOSI_GPIO_Port      GPIOB       /* SPI3_MOSI, see HAL_SPI_MspInit() */
#define MOSI_Pin            GPIO_PIN_5

static GPIO_TypeDef *const s_cs_port[INA_COUNT] = { INA_CS1_GPIO_Port, INA_CS2_GPIO_Port, INA_CS3_GPIO_Port };
static const uint16_t      s_cs_pin[INA_COUNT]  = { INA_CS1_Pin, INA_CS2_Pin, INA_CS3_Pin };

static INA_Dev  s_dev[INA_COUNT];
static uint32_t s_last_probe[INA_COUNT];
static uint8_t  s_probed[INA_COUNT];
static uint8_t  s_bus_blocked;

/* Read an n-byte (2 or 3) big-endian register. Returns 0 on SPI error. */
static uint8_t ReadReg(uint8_t index, uint8_t reg, uint8_t nbytes, uint32_t *value)
{
  uint8_t tx[4] = { (uint8_t)((reg << 2) | 0x01U), 0, 0, 0 };
  uint8_t rx[4] = { 0 };
  HAL_StatusTypeDef st;

  HAL_GPIO_WritePin(s_cs_port[index], s_cs_pin[index], GPIO_PIN_RESET);
  st = HAL_SPI_TransmitReceive(&hspi3, tx, rx, (uint16_t)(nbytes + 1U), SPI_TIMEOUT_MS);
  HAL_GPIO_WritePin(s_cs_port[index], s_cs_pin[index], GPIO_PIN_SET);

  if (st != HAL_OK)
  {
    return 0;
  }
  *value = 0;
  for (uint8_t i = 1; i <= nbytes; i++)
  {
    *value = (*value << 8) | rx[i];
  }
  return 1;
}

/* ADC_CONFIG: MODE = continuous bus+shunt+temp (0xF), VBUSCT = VSHCT = VTCT = 84 us (1), AVG = 1 (0) */
#define ADC_CONFIG_VALUE    0xF248U

static uint8_t WriteReg(uint8_t index, uint8_t reg, uint16_t value)
{
  uint8_t tx[3] = { (uint8_t)(reg << 2), (uint8_t)(value >> 8), (uint8_t)value };
  uint8_t rx[3] = { 0 };
  HAL_StatusTypeDef st;
  HAL_GPIO_WritePin(s_cs_port[index], s_cs_pin[index], GPIO_PIN_RESET);
  st = HAL_SPI_TransmitReceive(&hspi3, tx, rx, 3U, SPI_TIMEOUT_MS);
  HAL_GPIO_WritePin(s_cs_port[index], s_cs_pin[index], GPIO_PIN_SET);
  return (st == HAL_OK) ? 1U : 0U;
}

static void Probe(uint8_t index)
{
  INA_Dev *d = &s_dev[index];
  uint32_t mfr = 0;
  uint32_t dev = 0;

  d->kind = INA_ABSENT;
  if (!ReadReg(index, REG_MANUFACTURER_ID, 2, &mfr) || !ReadReg(index, REG_DEVICE_ID, 2, &dev))
  {
    return;
  }
  d->mfr_id = (uint16_t)mfr;
  d->dev_id = (uint16_t)dev;
  if (mfr != MANUFACTURER_ID_TI)
  {
    return;
  }
  switch (dev >> 4)
  {
    case DIE_ID_INA239: d->kind = INA_239;     break;
    case DIE_ID_INA229: d->kind = INA_229;     break;
    default:            d->kind = INA_UNKNOWN; break;
  }
  if (d->kind == INA_239 || d->kind == INA_229)
  {
    (void)WriteReg(index, REG_ADC_CONFIG, ADC_CONFIG_VALUE);   /* fast bus conversion, see header */
  }
}

static void ReadMeasurements(uint8_t index)
{
  INA_Dev *d = &s_dev[index];
  uint32_t vbus = 0;
  uint32_t temp = 0;

  if (d->kind == INA_239)
  {
    if (!ReadReg(index, REG_VBUS, 2, &vbus) || !ReadReg(index, REG_DIETEMP, 2, &temp))
    {
      d->kind = INA_ABSENT;
      return;
    }
    d->vbus_mV = ((int32_t)(int16_t)vbus * 25) / 8;            /* 3.125 mV/LSB        */
    d->temp_C  = (int16_t)(((int16_t)temp >> 4) / 8);          /* [15:4], 125 mC/LSB  */
  }
  else if (d->kind == INA_229)
  {
    if (!ReadReg(index, REG_VBUS, 3, &vbus) || !ReadReg(index, REG_DIETEMP, 2, &temp))
    {
      d->kind = INA_ABSENT;
      return;
    }
    d->vbus_mV = (int32_t)(((vbus >> 4) * 3125U) / 16000U);    /* [23:4], 195.3125 uV/LSB */
    d->temp_C  = (int16_t)((int16_t)temp / 128);               /* 7.8125 mC/LSB           */
  }
}

/**
  * @brief  Check that nothing else drives the SPI bus before it is used.
  *
  * On the first PCB revision the isolator in front of U10 (U13, ISO7762) has
  * its four used channels pointing from the INA side to the MCU side, so
  * three of its push-pull outputs sit on SCLK, MOSI and CS3 and hold them
  * high, and its MISO output masks U11 / U12. Clocking SPI3 against that
  * overloads the MCU pins and the isolator and reads nothing, so if MOSI
  * reads high against a weak pull-down the SPI pins are released and the
  * read-out stays off. On a free bus (isolator removed or corrected) only
  * high-impedance inputs hang on MOSI, it reads low, and SPI3 is used as
  * normal.
  */
void INA_Init(void)
{
  GPIO_InitTypeDef gpio = {0};

  gpio.Pin  = MOSI_Pin;
  gpio.Mode = GPIO_MODE_INPUT;
  gpio.Pull = GPIO_PULLDOWN;
  HAL_GPIO_Init(MOSI_GPIO_Port, &gpio);
  HAL_Delay(2);
  s_bus_blocked = (HAL_GPIO_ReadPin(MOSI_GPIO_Port, MOSI_Pin) == GPIO_PIN_SET);

  if (s_bus_blocked)
  {
    HAL_SPI_DeInit(&hspi3);                            /* SCLK, MISO, MOSI to high impedance */
    HAL_GPIO_DeInit(INA_CS3_GPIO_Port, INA_CS3_Pin);   /* CS3 is driven by the isolator too  */
  }
  else
  {
    HAL_SPI_MspInit(&hspi3);                           /* MOSI back to SPI3 */
  }
}

uint8_t INA_BusBlocked(void)
{
  return s_bus_blocked;
}

void INA_Poll(void)
{
  uint32_t now = HAL_GetTick();

  if (s_bus_blocked)
  {
    return;
  }

  for (uint8_t i = 0; i < INA_COUNT; i++)
  {
    if (s_dev[i].kind == INA_ABSENT || s_dev[i].kind == INA_UNKNOWN)
    {
      /* U10 is powered from the floating PV-side supply and can appear later. */
      if (!s_probed[i] || (now - s_last_probe[i]) >= PROBE_INTERVAL_MS)
      {
        s_probed[i]     = 1;
        s_last_probe[i] = now;
        Probe(i);
      }
    }
    ReadMeasurements(i);
  }
}

const INA_Dev *INA_Get(uint8_t index)
{
  return &s_dev[index];
}

const char *INA_KindName(INA_Kind kind)
{
  switch (kind)
  {
    case INA_239:     return "INA239";
    case INA_229:     return "INA229";
    case INA_UNKNOWN: return "unknown TI part";
    default:          return "no response";
  }
}
