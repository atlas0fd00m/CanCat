#ifndef __DEFINES_H__
#define __DEFINES_H__

#include "queue.h"

#define ISOTP_BUF_SIZE 4095 // ISO-TP max length is 4095 bytes
#define SERIAL_BUF_SIZE ISOTP_BUF_SIZE + 12 // + 12 bytes of overhead for serial

/* Serial Commands */
#define CMD_LOG                  0x2f
#define CMD_LOG_HEX              0x2e

#define CMD_CAN_RECV                    0x30
#define CMD_PING_RESPONSE               0x31
#define CMD_CHANGE_BAUD_RESULT          0x32
#define CMD_CAN_BAUD_RESULT             0x33
#define CMD_CAN_SEND_RESULT             0x34
#define CMD_ISO_RECV                    0x35
#define CMD_SET_FILT_MASK               0x36
#define CMD_CAN_MODE_RESULT             0x37
#define CMD_CAN_SEND_ISOTP_RESULT       0x38
#define CMD_CAN_RECV_ISOTP_RESULT       0x39
#define CMD_CAN_SENDRECV_ISOTP_RESULT   0x3A
#define CMD_GET_CAN_QUEUE_STATS         0x3C

#define CMD_PING                 0x41
#define CMD_CHANGE_BAUD          0x42
#define CMD_CAN_BAUD             0x43
#define CMD_CAN_SEND             0x44
#define CMD_CAN_MODE             0x45
#define CMD_CAN_MODE_SNIFF_CAN0  0x00
#define CMD_CAN_MODE_SNIFF_CAN1  0x01
#define CMD_CAN_MODE_CITM        0x02
#define CMD_CAN_SEND_ISOTP       0x46
#define CMD_CAN_RECV_ISOTP       0x47
#define CMD_CAN_SENDRECV_ISOTP   0x48

/* constants for setting baudrate for the CAN bus */
#define NUM_BAUD_RATES 19
extern uint32_t baud_rates_table[NUM_BAUD_RATES];

/* circular buffers for receiving and sending CAN frames */
// #define CAN_BUFFER_LEN 128
#define CAN_BUFFER_LEN 1024
extern Queue<CAN_FRAME> can_rx_frames0;
extern Queue<CAN_FRAME> can_rx_frames1;
extern Queue<CAN_FRAME> can_tx_frames0;
extern Queue<CAN_FRAME> can_tx_frames1;

/* General purpose functions */
void CreateCanFrame(uint32_t arbid, uint8_t extended, uint8_t len, uint8_t data[], bool padding, uint8_t padding_byte, CAN_FRAME *frame);
uint8_t SendFrame(CAN_FRAME frame);
void log(const char* msg, uint8_t len);
void logHex(uint32_t num);

/* The device in use */
extern CANRaw *device;

/* Initialization status and operating mode */
extern uint8_t initialized;
extern uint8_t mode;

#endif
