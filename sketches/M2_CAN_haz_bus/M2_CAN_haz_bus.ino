/**
 * This file provides the Arduino setup and loop functions, any general-purpose functionality such as 
 * creating and sending CAN frames and handles the serial communication.
 */

#include <due_can.h>
#include <limits.h>
#include "autobaud.h"
#include "defines.h"
#include "queue.h"
#include "isotp.h"
#include "citm.h"
#include "autocapture.h"
#include "sniffing.h"

#define Serial SerialUSB

/* circular buffers for receiving and sending CAN frames */
Queue<CAN_FRAME> can_rx_frames0(CAN_BUFFER_LEN);
Queue<CAN_FRAME> can_rx_frames1(CAN_BUFFER_LEN);
Queue<CAN_FRAME> can_tx_frames0(CAN_BUFFER_LEN);
Queue<CAN_FRAME> can_tx_frames1(CAN_BUFFER_LEN);

/* Buffer for receiving serial commands */
uint8_t serial_buffer[SERIAL_BUF_SIZE];
uint16_t serial_buf_index = 0;
uint16_t serial_buf_count = 0;
uint8_t initialized = 0;
uint8_t mode = CMD_CAN_MODE_SNIFF_CAN0;
static void printCanRegs(void);


uint32_t baud_rates_table[NUM_BAUD_RATES] = {
    0,      // CAN_AUTO     = 0
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

/* The current can device if sniffing */
CANRaw *device = NULL;

/* Functions for serial communication */
void send(unsigned char *data, unsigned char cmd, unsigned char len)
{
    Serial.write("@");
    Serial.write(len + 1);    // 1 for @
    Serial.write(cmd);
    Serial.write(data, len);
}

void log(const char* msg, uint8_t len)
{
    send((unsigned char*)msg, CMD_LOG, len);
}

void logHex(uint32_t num)
{
    uint32_t temp = num;
    send((unsigned char*)&temp, CMD_LOG_HEX, 4);
}

void logHexStr(uint32_t num, const char* prefix, uint32_t len)
{
    log(prefix, len);
    logHex(num);
}

void setup()
{
  //start serial port
  Serial.begin(250000);
  while(!Serial);
}

void loop()
{
    uint8_t results = 0;
    uint32_t mask;
    uint32_t filter;
    CAN_FRAME frame = {0};
    /* Send enqueued frames */
    if(!can_tx_frames0.isEmpty())
    {
        frame = can_tx_frames0.peek();
        if(Can0.sendFrame(frame))
        {
            can_tx_frames0.remove();
        }
    }
    if(!can_tx_frames1.isEmpty())
    {
        frame = can_tx_frames1.peek();
        if(Can1.sendFrame(frame))
        {
            can_tx_frames1.remove();
        }
    }

    /* Push received frames back up */
    if(!can_rx_frames0.isEmpty())
    {
        uint8_t buf[12];
        frame = can_rx_frames0.dequeue();
        buf[0] = (frame.id >> 24) & 0xff;
        buf[1] = (frame.id >> 16) & 0xff;
        buf[2] = (frame.id >> 8) & 0xff;
        buf[3] = frame.id & 0xff;
        // FIXME: grab extflags and put in here.
        for(uint8_t i = 0; i < frame.length; i++)
            buf[i+4] = frame.data.bytes[i];
        
        send(buf, CMD_CAN_RECV, frame.length + 4);
    }
    if(!can_rx_frames1.isEmpty())
    {
        uint8_t buf[12];
        frame = can_rx_frames1.dequeue();
        buf[0] = (frame.id >> 24) & 0xff;
        buf[1] = (frame.id >> 16) & 0xff;
        buf[2] = (frame.id >> 8) & 0xff;
        buf[3] = frame.id & 0xff;
        // FIXME: grab extflags and put in here.
        for(uint8_t i = 0; i < frame.length; i++)
            buf[i+4] = frame.data.bytes[i];
        
        send(buf, CMD_CAN_RECV, frame.length + 4);
        if(mode == CMD_CAN_MODE_CITM)
            send(buf, CMD_ISO_RECV, frame.length + 4);
    }

    /* Process any pending IsoTP transactions */
    process_isotp();

    // handle Serial-incoming data    
    for (uint32_t count = Serial.available(); count > 0; count--)
    {
        serial_buffer[serial_buf_index++] = Serial.read();
        if (serial_buf_index == 2)
        {
            serial_buf_count = serial_buffer[0] << 8 | serial_buffer[1];
        }
        
        if (serial_buf_index == serial_buf_count)
        // we've got enough of the packet
        {
            count = 1;  // exit the loop
        }        
    }
        
    // if we've received an entire message, process it here
    if (serial_buf_index && serial_buf_index == serial_buf_count)
    {
        // Check if we've been initialized and we're not trying to initialize
        if(initialized == 0 && serial_buffer[2] != CMD_CAN_BAUD && serial_buffer[2] != CMD_CAN_MODE)
        {
            log("CAN Not Initialized", 19);
            // clear counters for next message
            serial_buf_index = 0;
            serial_buf_count = 0;
        }

        switch (serial_buffer[2])  // cmd byte
        {
            case CMD_CHANGE_BAUD:
                Serial.begin(*(unsigned int*)(serial_buffer+3));
                while (!Serial);
                send(&results, CMD_CHANGE_BAUD_RESULT, 1);
                break;

            case CMD_PING:
                send(serial_buffer+3, CMD_PING_RESPONSE, serial_buf_count-3);
                break;

            case CMD_CAN_MODE:
                mode = serial_buffer[3]; // Stores the desired mode
                results = 1;
                send(&results, CMD_CAN_MODE_RESULT, 1);
                break;

            case CMD_CAN_BAUD:
                //Initialize based on mode
                if(mode == CMD_CAN_MODE_SNIFF_CAN0)
                {
                    device = &Can0;
                    results = Init_Sniff(serial_buffer[3]);
                } 
                else if (mode == CMD_CAN_MODE_SNIFF_CAN1)
                {
                    device = &Can1;
                    results = Init_Sniff(serial_buffer[3]);
                }
                else if (mode == CMD_CAN_MODE_CITM)
                {
                    results = Init_CITM(serial_buffer[3]);
                }
                else
                {
                    logHexStr(mode, "Invalid mode", 12);
                    results = 0;
                    initialized = 0;
                }
                send(&results, CMD_CAN_BAUD_RESULT, 1);
                break;
                
            case CMD_CAN_SEND:
                frame.id = (uint32_t)serial_buffer[6] | 
                           ((uint32_t)serial_buffer[5] << 8) |
                           ((uint32_t)serial_buffer[4] << 16) |
                           ((uint32_t)serial_buffer[3] << 24);
                frame.extended = serial_buffer[7];
                frame.length = serial_buf_count - 8;
                for(uint8_t i = 0; i < frame.length; i++)
                {
                    frame.data.bytes[i] = serial_buffer[8+i];
                }

                results = SendFrame(frame);
                send(&results, CMD_CAN_SEND_RESULT, 1);
                
                break;

            case CMD_SET_FILT_MASK:
                mask   = serial_buffer[6]  | (serial_buffer[5] << 8)  | (serial_buffer[4] << 16)  | (serial_buffer[3] << 24);
                filter = serial_buffer[14] | (serial_buffer[13] << 8) | (serial_buffer[12] << 16) | (serial_buffer[11] << 24);
                if (mask <= 0x7FF) // If it's an 11-bit identifier
                    device->setRXFilter(5, filter, mask, true);
                else
                    device->setRXFilter(6, filter, mask, false);
                break;

            case CMD_CAN_SEND_ISOTP:
                results = SendIsoTPFrame(serial_buffer, serial_buf_count);
                send(&results, CMD_CAN_SEND_ISOTP_RESULT, 1);
                break;
                
            case CMD_CAN_RECV_ISOTP:
                results = RecvIsoTPFrame(serial_buffer);
                send(&results, CMD_CAN_RECV_ISOTP_RESULT, 1);
                break;

            case CMD_CAN_SENDRECV_ISOTP:
                results = RecvIsoTPFrame(serial_buffer);
                results |= SendIsoTPFrame(serial_buffer, serial_buf_count);
                send(&results, CMD_CAN_SENDRECV_ISOTP_RESULT, 1);
                break;

            case CMD_PRINT_CAN_REGS:
                printCanRegs();
                break;

            default:
                Serial.write("@\x15\x03""BAD COMMAND: ");
                Serial.print(serial_buffer[2]);
                
        }
        // clear counters for next message
        serial_buf_index = 0;
        serial_buf_count = 0;
    }
}


/*********************************************************************************************************
 Helper Functions
*********************************************************************************************************/

/* Creates a can frame from the given data */
void CreateCanFrame(uint32_t arbid, uint8_t extended, uint8_t len, uint8_t data[], bool padding, uint8_t padding_byte, CAN_FRAME *frame)
{
    frame->id = arbid;
    frame->extended = extended;

    for(uint8_t i = 0; i < len; i++)
        frame->data.bytes[i] = data[i];

    if(!padding)
        frame->length = len;
    else
    {
        for(uint8_t i = len; i < 8; i++)
            frame->data.bytes[i] = padding_byte;
        frame->length = 8;
    }
}

/* Send a CAN frame on the correct interface based on the mode */
uint8_t SendFrame(CAN_FRAME frame)
{
    uint8_t results = 0;

    if (mode == CMD_CAN_MODE_SNIFF_CAN0 && !can_tx_frames0.enqueue(&frame))
    {
        log("Failed sending on Can0", 22);
        results = 1;
    }
    else if (mode == CMD_CAN_MODE_SNIFF_CAN1 && !can_tx_frames1.enqueue(&frame))
    {
        log("Failed sending on Can1", 22);
        results = 2;
    }
    else if (mode == CMD_CAN_MODE_CITM)
    {
        if(!can_tx_frames0.enqueue(&frame))
        {
            log("Failed sending on Can0", 22);
            results = 1;
        }
        if(!can_tx_frames1.enqueue(&frame))
        {
            log("Failed sending on Can1", 22);
            results = 2;
        }
    }

    /* Send the frame back up to be recorded with the other CAN frames */
    if(results == 0)
    {
        if(mode == CMD_CAN_MODE_SNIFF_CAN0 && !can_rx_frames0.enqueue(&frame))
            log("Failed enqueueing sent message", 30);
        else if(mode == CMD_CAN_MODE_SNIFF_CAN1 && !can_rx_frames1.enqueue(&frame))
            log("Failed enqueueing sent message", 30);
        else if(mode == CMD_CAN_MODE_CITM)
        {
            if(!can_rx_frames0.enqueue(&frame))
                log("Failed enqueueing sent message", 30);
            else if(!can_rx_frames1.enqueue(&frame))
                log("Failed enqueueing sent message", 30);
        }
    }

    return results;
}

// Print all of the configuration registers for the CAN peripheral with log messages
static void printCanRegs(void)
{
    char msg[50];
    log("CAN 0", 5);

    snprintf(msg, 50, "CAN_MR: 0x%08X", CAN0->CAN_MR);
    log(msg, strnlen(msg, 50));
    snprintf(msg, 50, "CAN_IMR: 0x%08X", CAN0->CAN_IMR);
    log(msg, strnlen(msg, 50));
    snprintf(msg, 50, "CAN_SR: 0x%08X", CAN0->CAN_SR);
    log(msg, strnlen(msg, 50));
    snprintf(msg, 50, "CAN_BR: 0x%08X", CAN0->CAN_BR);
    log(msg, strnlen(msg, 50));
    snprintf(msg, 50, "CAN_TIM: 0x%08X", CAN0->CAN_TIM);
    log(msg, strnlen(msg, 50));
    snprintf(msg, 50, "CAN_TIMESTP: 0x%08X", CAN0->CAN_TIMESTP);
    log(msg, strnlen(msg, 50));
    snprintf(msg, 50, "CAN_ECR: 0x%08X", CAN0->CAN_ECR);
    log(msg, strnlen(msg, 50));
    snprintf(msg, 50, "CAN_WPMR: 0x%08X", CAN0->CAN_WPMR);
    log(msg, strnlen(msg, 50));
    snprintf(msg, 50, "CAN_WPSR: 0x%08X", CAN0->CAN_WPSR);
    log(msg, strnlen(msg, 50));

    for (int i = 0; i < 8; i++)
    {
        snprintf(msg, 50, "CAN 0 Mailbox %d", i);
        log(msg, strnlen(msg, 50));
        snprintf(msg, 50, "CAN_MMR: 0x%08X", CAN0->CAN_MB[i].CAN_MMR);        
        log(msg, strnlen(msg, 50));
        snprintf(msg, 50, "CAN_MAM: 0x%08X", CAN0->CAN_MB[i].CAN_MAM);        
        log(msg, strnlen(msg, 50));
        snprintf(msg, 50, "CAN_MID: 0x%08X", CAN0->CAN_MB[i].CAN_MID);        
        log(msg, strnlen(msg, 50));
        snprintf(msg, 50, "CAN_MFID: 0x%08X", CAN0->CAN_MB[i].CAN_MFID);        
        log(msg, strnlen(msg, 50));
        snprintf(msg, 50, "CAN_MSR: 0x%08X", CAN0->CAN_MB[i].CAN_MSR);        
        log(msg, strnlen(msg, 50));
        snprintf(msg, 50, "CAN_MDL: 0x%08X", CAN0->CAN_MB[i].CAN_MDL);
        log(msg, strnlen(msg, 50));
        snprintf(msg, 50, "CAN_MDH: 0x%08X", CAN0->CAN_MB[i].CAN_MDH);        
        log(msg, strnlen(msg, 50));
    }

    log("CAN 1", 5);

    snprintf(msg, 50, "CAN_MR: 0x%08X", CAN1->CAN_MR);
    log(msg, strnlen(msg, 50));
    snprintf(msg, 50, "CAN_IMR: 0x%08X", CAN1->CAN_IMR);
    log(msg, strnlen(msg, 50));
    snprintf(msg, 50, "CAN_SR: 0x%08X", CAN1->CAN_SR);
    log(msg, strnlen(msg, 50));
    snprintf(msg, 50, "CAN_BR: 0x%08X", CAN1->CAN_BR);
    log(msg, strnlen(msg, 50));
    snprintf(msg, 50, "CAN_TIM: 0x%08X", CAN1->CAN_TIM);
    log(msg, strnlen(msg, 50));
    snprintf(msg, 50, "CAN_TIMESTP: 0x%08X", CAN1->CAN_TIMESTP);
    log(msg, strnlen(msg, 50));
    snprintf(msg, 50, "CAN_ECR: 0x%08X", CAN1->CAN_ECR);
    log(msg, strnlen(msg, 50));
    snprintf(msg, 50, "CAN_WPMR: 0x%08X", CAN1->CAN_WPMR);
    log(msg, strnlen(msg, 50));
    snprintf(msg, 50, "CAN_WPSR: 0x%08X", CAN1->CAN_WPSR);
    log(msg, strnlen(msg, 50));

    for (int i = 0; i < 8; i++)
    {
        snprintf(msg, 50, "CAN 1 Mailbox %d", i);
        log(msg, strnlen(msg, 50));
        snprintf(msg, 50, "CAN_MMR: 0x%08X", CAN1->CAN_MB[i].CAN_MMR);        
        log(msg, strnlen(msg, 50));
        snprintf(msg, 50, "CAN_MAM: 0x%08X", CAN1->CAN_MB[i].CAN_MAM);        
        log(msg, strnlen(msg, 50));
        snprintf(msg, 50, "CAN_MID: 0x%08X", CAN1->CAN_MB[i].CAN_MID);        
        log(msg, strnlen(msg, 50));
        snprintf(msg, 50, "CAN_MFID: 0x%08X", CAN1->CAN_MB[i].CAN_MFID);        
        log(msg, strnlen(msg, 50));
        snprintf(msg, 50, "CAN_MSR: 0x%08X", CAN1->CAN_MB[i].CAN_MSR);        
        log(msg, strnlen(msg, 50));
        snprintf(msg, 50, "CAN_MDL: 0x%08X", CAN1->CAN_MB[i].CAN_MDL);
        log(msg, strnlen(msg, 50));
        snprintf(msg, 50, "CAN_MDH: 0x%08X", CAN1->CAN_MB[i].CAN_MDH);        
        log(msg, strnlen(msg, 50));
    }

}


/*********************************************************************************************************
  END FILE
*********************************************************************************************************/
