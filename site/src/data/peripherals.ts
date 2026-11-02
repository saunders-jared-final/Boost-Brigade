/** Peripheral configuration of the STM32G474 (delivery report, appendix E, table 11). */
export const PERIPHERALS = [
  { name: 'PWM: HRTIM1', icon: 'pwm', summary: 'Eight outputs for four half-bridge legs, 184 ps resolution, hardware dead time.', rows: [
    ['Clock', '170 MHz × 32 = 5.44 GHz (184 ps steps)'],
    ['Period', 'PER 27200 / 18133 / 13600 for 200 / 300 / 400 kHz'],
    ['Interleave', 'A legs reset on the master period, B legs on CMP2 = PER/2 (180°)'],
    ['Duty', 'CMP1 per leg, preloaded, updated on reset; limits 0.05–0.95 (200 kHz), 0.08–0.95 (300), 0.12–0.88 (400)'],
    ['Dead time', '100 ns both edges (136 steps); 200 ns until 16 Oct'],
    ['Pins', 'S1A PA8/PA9, S1B PA10/PA11, S2A PB12/PB13, S2B PB14/PB15 (AF13), driven low before main()'],
    ['Control tick', 'master repetition interrupt every 20 / 30 / 40 periods = 100 µs'],
  ] },
  { name: 'ADC: ADC1 + ADC2 with DMA', icon: 'adc', summary: 'Four hall currents, four samples per switching period, averaged over the whole control tick.', rows: [
    ['Resolution', '12-bit, two ranks each, 6.5-cycle sample time, 42.5 MHz clock'],
    ['Trigger', 'HRTIM ADC trigger 1 at PER/8 + k·PER/4: mid-slope of the ripple, four per period'],
    ['Channels', 'ADC1: PA0 (ILA1), PA1 (ILA2); ADC2: PA4 (ILB1), PC1 (ILB2)'],
    ['DMA', 'circular, 160 half-words = 4 triggers × 20 periods × 2 ranks = one tick'],
    ['Filter', '80-sample box average per channel: nulls at f_sw and its harmonics (comb filter)'],
    ['Conversion', 'I = (code − zero) · (3300/4096 mV) / 100 mV/A; boot zero-calibration over 64 ticks'],
    ['Protection', 'OC latch: |I| > 12 A for 2 ms, rail codes for 3 ticks, or a stalled DMA'],
  ] },
  { name: 'SPI: SPI3 to the INA239s', icon: 'spi', summary: 'Three voltage monitors on one bus, polled at 1 kHz from the main loop.', rows: [
    ['Mode', 'master, mode 1, 8-bit MSB first, software chip selects, 1.33 MHz'],
    ['Pins', 'PB3 SCK, PB4 MISO, PB5 MOSI; CS1 PA7 (U12), CS2 PB6 (U11), CS3 PC7 (U10 via the isolator)'],
    ['Device config', 'ADC_CONFIG 0xF248: continuous, 84 µs conversion, no averaging (the 1 ms default made the loop ring)'],
    ['Resolution', '3.125 mV per step bus voltage; die temperature 125 m°C per step; INA229 auto-detected'],
    ['Reconstruction', 'VM3 = U12, VM2 = U11 − U12, VM1 = V_string(from the Pi) − U11 by default'],
  ] },
  { name: 'UART: LPUART1 to the Pi', icon: 'uart', summary: 'One ASCII line per message over the ST-LINK virtual COM port.', rows: [
    ['Link', 'PA2/PA3 via ST-LINK VCP, 921600 8N1, 512-byte receive ring buffer (interrupt per byte)'],
    ['Nucleo → Pi', 'T telemetry at 50 Hz (27 fields), S status at 1 Hz and on state change, F fault detail, A answers, P parameters'],
    ['Pi → Nucleo', 'C,MODE · C,EN · C,DUTY · C,VREF · C,SET · C,APPLY · C,ESTOP · C,CLEAR · C,PING (1 Hz heartbeat)'],
    ['Watchdog', 'closed loop trips after 5 s without a command; V_string from the Pi goes stale after 2 s'],
    ['Protocol', 'version 2, firmware shuffler-fw-0.4.1; PARAMS_VERSION in every frame'],
  ] },
  { name: 'GPIO, timers, watchdog', icon: 'misc', summary: 'The safety path that never waits for the main loop.', rows: [
    ['E-stop', 'PC0, pull-up, falling-edge interrupt at the highest priority'],
    ['Watchdog', 'independent watchdog 0.3 s, kicked by the 100 Hz safety task'],
    ['Stall check', 'SysTick 1 kHz: main loop stalled > 20 ms while switching = fault 0x2000'],
    ['Clock', 'HSI 16 MHz → PLL → 170 MHz, flash latency 4, boost scale; ADC from PLL-P at 56.7 MHz in the 400 kHz build'],
    ['Button and LED', 'B1 toggles enable; LD2 PA5'],
  ] },
];
