/**
 * comms.h - ASCII telemetry / command link to the Raspberry Pi over the
 * ST-LINK virtual COM port (LPUART1). Format: 0_Documentation/telemetry.md.
 */
#ifndef COMMS_H
#define COMMS_H

#include <stdint.h>

#define COMMS_BAUD              921600U
#define COMMS_PROTOCOL_VERSION  2   /* 2: T frame gains kscale,pset before pver; C,SET/SETM/GET/LIST/APPLY/REVERT */
#define COMMS_FW_VERSION        "shuffler-fw-0.3.3"

void comms_init(void);
void comms_banner(void);
void comms_send_telemetry(void);   /* T line */
void comms_send_status(void);      /* S line */
void comms_send_fault(void);       /* F line */
char *comms_fmt(char *buf, float x); /* buf >= 16 bytes; printf-nano has no %f */
void comms_note(const char *line); /* '# ...' comment line (ignored by the Pi bridge), CRLF added */
void comms_poll_rx(void);          /* parse complete command lines, answer with A lines */
void comms_rx_irq_byte(uint8_t b); /* from the UART RX interrupt */

#endif /* COMMS_H */
