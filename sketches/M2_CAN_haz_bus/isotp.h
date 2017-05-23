#ifndef __ISOTP_H__
#define __ISOTP_H__

uint8_t SendIsoTPFrame(uint8_t serial_buffer[]);
uint8_t RecvIsoTPFrame(uint8_t serial_buffer[]);

void process_isotp();
uint8_t SendIsoTPFrame(uint8_t serial_buffer[], uint16_t serial_buf_count);
uint8_t RecvIsoTPFrame(uint8_t serial_buffer[]);

#endif
