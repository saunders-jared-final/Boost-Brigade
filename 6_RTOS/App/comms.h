/**
 * comms.h - ASCII telemetry / command link to the Raspberry Pi over the
 * ST-LINK virtual COM port (LPUART1). Format: 0_Documentation/telemetry.md.
 */
#ifndef COMMS_H
#define COMMS_H

#include <stdint.h>

#define COMMS_BAUD              921600U
#define COMMS_PROTOCOL_VERSION  1
#define COMMS_FW_VERSION        "shuffler-fw-0.2.0"

void comms_init(void);
void comms_banner(void);
void comms_send_telemetry(void);   /* T line */
void comms_send_status(void);      /* S line */
void comms_send_fault(void);       /* F line */
void comms_poll_rx(void);          /* parse complete command lines, answer with A lines */
void comms_rx_irq_byte(uint8_t b); /* from the UART RX interrupt */

#endif /* COMMS_H */
