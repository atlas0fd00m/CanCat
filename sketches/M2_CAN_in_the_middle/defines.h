#ifndef __DEFINES_H__
#define __DEFINES_H__

#define CAN_RX_BUF_SIZE 32
#define CAN_TX_BUF_SIZE 16
#define SERIAL_BUF_SIZE 64

/* Serial Commands */
#define CMD_LOG                  0x2f
#define CMD_LOG_HEX              0x2e

#define CMD_CAN_RECV             0x30
#define CMD_PING_RESPONSE        0x31
#define CMD_CHANGE_BAUD_RESULT   0x32
#define CMD_CAN_BAUD_RESULT      0x33
#define CMD_CAN_SEND_RESULT      0x34
#define CMD_ISO_RECV             0x35
#define CMD_SET_FILT_MASK        0x36

#define CMD_PING                 0x41
#define CMD_CHANGE_BAUD          0x42
#define CMD_CAN_BAUD             0x43
#define CMD_CAN_SEND             0x44

/* constants for setting baudrate for the CAN bus */
uint32_t baud_rates_table[19] = {
    0,      // Index 0 is unused
    5000,   // CAN_5KBPS    = 1
    10000,  // CAN_10KBPS   = 2
    20000,  // CAN_20KBPS   = 3
    25000,  // CAN_25KBPS   = 4 
    31250,  // CAN_31K25BPS = 5
    33000,  // CAN_33KBPS   = 6
    40000,  // CAN_40KBPS   = 7
    50000,  // CAN_50KBPS   = 8
    80000,  // CAN_80KBPS   = 9
    83300,  // CAN_83K3BPS  = 10
    95000,  // CAN_95KBPS   = 11
    100000, // CAN_100KBPS  = 12
    125000, // CAN_125KBPS  = 13
    200000, // CAN_200KBPS  = 14
    250000, // CAN_250KBPS  = 15
    500000, // CAN_500KBPS  = 16
    666000, // CAN_666KBPS  = 17
    1000000,// CAN_1000KBPS = 18
};

#endif
