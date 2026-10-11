/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.h
  * @brief          : Header for main.c file.
  *                   This file contains the common defines of the application.
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

/* Define to prevent recursive inclusion -------------------------------------*/
#ifndef __MAIN_H
#define __MAIN_H

#ifdef __cplusplus
extern "C" {
#endif

/* Includes ------------------------------------------------------------------*/
#include "stm32g4xx_hal.h"

#include "stm32g4xx_nucleo.h"
#include <stdio.h>

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */

/* USER CODE END Includes */

/* Exported types ------------------------------------------------------------*/
/* USER CODE BEGIN ET */

/* USER CODE END ET */

/* Exported constants --------------------------------------------------------*/
/* USER CODE BEGIN EC */

/* USER CODE END EC */

/* Exported macro ------------------------------------------------------------*/
/* USER CODE BEGIN EM */

/* USER CODE END EM */

/* Exported functions prototypes ---------------------------------------------*/
void Error_Handler(void);

/* USER CODE BEGIN EFP */

/* USER CODE END EFP */

/* Private defines -----------------------------------------------------------*/
#define RCC_OSC32_IN_Pin GPIO_PIN_14
#define RCC_OSC32_IN_GPIO_Port GPIOC
#define RCC_OSC32_OUT_Pin GPIO_PIN_15
#define RCC_OSC32_OUT_GPIO_Port GPIOC
#define RCC_OSC_IN_Pin GPIO_PIN_0
#define RCC_OSC_IN_GPIO_Port GPIOF
#define RCC_OSC_OUT_Pin GPIO_PIN_1
#define RCC_OSC_OUT_GPIO_Port GPIOF
#define ILB_2_Pin GPIO_PIN_1
#define ILB_2_GPIO_Port GPIOC
#define ILA_1_Pin GPIO_PIN_0
#define ILA_1_GPIO_Port GPIOA
#define ILA_2_Pin GPIO_PIN_1
#define ILA_2_GPIO_Port GPIOA
#define ILB_1_Pin GPIO_PIN_4
#define ILB_1_GPIO_Port GPIOA
#define INA_CS1_Pin GPIO_PIN_7
#define INA_CS1_GPIO_Port GPIOA
#define S2_A_H_Pin GPIO_PIN_12
#define S2_A_H_GPIO_Port GPIOB
#define S2_A_L_Pin GPIO_PIN_13
#define S2_A_L_GPIO_Port GPIOB
#define S2_B_H_Pin GPIO_PIN_14
#define S2_B_H_GPIO_Port GPIOB
#define S2_B_L_Pin GPIO_PIN_15
#define S2_B_L_GPIO_Port GPIOB
#define INA_CS3_Pin GPIO_PIN_7
#define INA_CS3_GPIO_Port GPIOC
#define S1_A_H_Pin GPIO_PIN_8
#define S1_A_H_GPIO_Port GPIOA
#define S1_A_L_Pin GPIO_PIN_9
#define S1_A_L_GPIO_Port GPIOA
#define S1_B_H_Pin GPIO_PIN_10
#define S1_B_H_GPIO_Port GPIOA
#define S1_B_L_Pin GPIO_PIN_11
#define S1_B_L_GPIO_Port GPIOA
#define T_SWDIO_Pin GPIO_PIN_13
#define T_SWDIO_GPIO_Port GPIOA
#define T_SWCLK_Pin GPIO_PIN_14
#define T_SWCLK_GPIO_Port GPIOA
#define INA_CS2_Pin GPIO_PIN_6
#define INA_CS2_GPIO_Port GPIOB

/* USER CODE BEGIN Private defines */
/* Every HRTIM output, as a mask for the common ODISR register. */
#define HRTIM_ALL_OUTPUTS   (HRTIM_OUTPUT_TA1 | HRTIM_OUTPUT_TA2 | HRTIM_OUTPUT_TB1 | HRTIM_OUTPUT_TB2 | \
                             HRTIM_OUTPUT_TC1 | HRTIM_OUTPUT_TC2 | HRTIM_OUTPUT_TD1 | HRTIM_OUTPUT_TD2 | \
                             HRTIM_OUTPUT_TE1 | HRTIM_OUTPUT_TE2 | HRTIM_OUTPUT_TF1 | HRTIM_OUTPUT_TF2)

/* USER CODE END Private defines */

#ifdef __cplusplus
}
#endif

#endif /* __MAIN_H */
