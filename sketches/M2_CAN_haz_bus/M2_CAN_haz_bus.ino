#include <due_can.h>
#include <limits.h>
#include "autobaud.h"
#include "defines.h"
#include "queue.h"

#define Serial SerialUSB

/* Function headers */
void CreateCanFrame(uint32_t arbid, uint8_t extended, uint8_t len, uint8_t data[], bool padding, uint8_t padding_byte, CAN_FRAME *frame);
uint8_t SendFrame(CAN_FRAME frame);
uint8_t SendIsoTPFrame(uint8_t serial_buffer[]);
uint8_t RecvIsoTPFrame(uint8_t serial_buffer[]);

/* circular buffers for receiving and sending CAN frames */
Queue<CAN_FRAME> can_rx_frames0(128);
Queue<CAN_FRAME> can_rx_frames1(128);
Queue<CAN_FRAME> can_tx_frames0(128);
Queue<CAN_FRAME> can_tx_frames1(128);

/* Buffer for receiving serial commands */
uint8_t serial_buffer[SERIAL_BUF_SIZE];
uint16_t serial_buf_index = 0;
uint16_t serial_buf_count = 0;
uint8_t initialized = 0;
uint8_t mode = CMD_CAN_MODE_SNIFF_CAN0;

/* The current can device if sniffing */
CANRaw *device = NULL;

/* IsoTP related globals */
uint32_t isotp_rx_arbid;
uint32_t isotp_tx_arbid;
uint8_t isotp_tx_extended;
uint8_t isotp_tx_buffer[ISOTP_BUF_SIZE];
volatile uint16_t isotp_tx_index = 0;
volatile uint16_t isotp_tx_length = 0;
volatile uint8_t isotp_tx_go = 0;
uint8_t isotp_tx_PCIIndex = 1;
unsigned long isotp_sep_time = 0;
unsigned long isotp_last_tx_time;

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

/* CAN interrupt Callbacks */

/* CITM callback for Can 0 */
void CITM_Can0_cb(CAN_FRAME *frame)
{
    if(!can_rx_frames0.enqueue(frame))
        log("RX ENQ Err CAN0", 15);
    if(!can_tx_frames1.enqueue(frame))
        log("TX ENQ Err CAN1", 15);
}

/* CITM callback for Can 1 */
void CITM_Can1_cb(CAN_FRAME *frame)
{
    if(!can_rx_frames1.enqueue(frame))
        log("RX ENQ Err CAN1", 15);
    if(!can_tx_frames0.enqueue(frame))
        log("TX ENQ Err CAN0", 15);
}

/* Sniffing callback for Can 0 */
void Sniff_Can0_cb(CAN_FRAME *frame)
{
    if(!can_rx_frames0.enqueue(frame))
        log("RX ENQ Err CAN0", 15);
}

/* Sniffing callback for Can 1 */
void Sniff_Can1_cb(CAN_FRAME *frame)
{
    if(!can_rx_frames1.enqueue(frame))
        log("RX ENQ Err CAN1", 15);
}

/* IsoTP callback.
 * 
 * Receives packets for IsoTP. Responds with flow control message
 * as required. Otherwise sends the CAN frame up the serial link like
 * all the other messages. Upon receipt of a flow control message
 * starts ISOTP transmission if one is pending
 */
void IsoTP_cb(CAN_FRAME *frame, CANRaw *device)
{
    if ((frame->data.bytes[0] & 0xF0) == 0x10) /* First message */
    {
        CAN_FRAME tx_frame;
        tx_frame.data.byte[0] = 0x30;

        //TODO: Support for configurable padding and delay
        CreateCanFrame(isotp_tx_arbid, isotp_tx_extended, 1, tx_frame.data.byte, true, 0x00, &tx_frame);
        SendFrame(tx_frame);
    }
    else if ((frame->data.bytes[0] & 0xF0) == 0x30) /* Flow control message */
    {
        /* Check for an abort message */
        if((frame->data.bytes[0] & 0x0F) == 0x02)
        {
            log("Received ABORT from ISOTP TX", 28);
            if (mode != CMD_CAN_MODE_CITM)
            {
                device->setRXFilter(0, 0, 0x7FF, false);
                device->detachCANInterrupt(0);
            }
            else
            {
                Can0.setRXFilter(0, 0, 0x7FF, false);
                Can0.detachCANInterrupt(0);
                Can1.setRXFilter(0, 0, 0x7FF, false);
                Can1.detachCANInterrupt(0);
            }
            isotp_tx_index = 0;
            isotp_tx_length = 0;
        }

        /* Check for a wait message  */
        else if((frame->data.bytes[0] & 0x0F) == 0x01)
        {
            isotp_tx_go = 0; // Suspend sending messages
        }

        /* Check for block size */
        else if(frame->data.bytes[1] != 0)
        {
            log("Block size specified, which is unimplemented", 67);
            if (mode != CMD_CAN_MODE_CITM)
            {
                device->setRXFilter(0, 0, 0x7FF, false);
                device->detachCANInterrupt(0);
            }
            else
            {
                Can0.setRXFilter(0, 0, 0x7FF, false);
                Can0.detachCANInterrupt(0);
                Can1.setRXFilter(0, 0, 0x7FF, false);
                Can1.detachCANInterrupt(0);
            }
            isotp_tx_index = 0;
            isotp_tx_length = 0;
        }
        
        /* Check for separation time */
        else if(frame->data.bytes[2] != 0)
        {
            switch(frame->data.bytes[2])
            {
                case 0xf1:
                    isotp_sep_time = 100;
                    break;
                case 0xf2:
                    isotp_sep_time = 200;
                    break;
                case 0xf3:
                    isotp_sep_time = 300;
                    break;
                case 0xf4:
                    isotp_sep_time = 400;
                    break;
                case 0xf5:
                    isotp_sep_time = 500;
                    break;
                case 0xf6:
                    isotp_sep_time = 600;
                    break;
                case 0xf7:
                    isotp_sep_time = 700;
                    break;
                case 0xf8:
                    isotp_sep_time = 800;
                    break;
                case 0xf9:
                    isotp_sep_time = 900;
                    break;
                default:
                    isotp_sep_time = frame->data.bytes[2] * 1000;
                    break;
            }
            isotp_last_tx_time = micros();
            isotp_tx_go = 1;
        }

        /* No flow control, we can just finish sending the message */
        else
        {
            isotp_tx_go = 1;
            isotp_sep_time = 0;
        }
    }
    if(mode == CMD_CAN_MODE_SNIFF_CAN0 && !can_rx_frames0.enqueue(frame))
        log("RX ENQ Err CAN0", 15);
    else if(mode == CMD_CAN_MODE_SNIFF_CAN1 && !can_rx_frames1.enqueue(frame))
        log("RX ENQ Err CAN1", 15);
    else if(mode == CMD_CAN_MODE_CITM)
    {
        if(device == &Can0)
        {
            if(!can_rx_frames0.enqueue(frame))
                log("RX ENQ Err CAN0", 15);
            if(!can_tx_frames1.enqueue(frame))
                log("TX ENQ Err CAN1", 15);
        }
        else if(device == &Can1)
        {
            if(!can_rx_frames0.enqueue(frame))
                log("RX ENQ Err CAN0", 15);
            if(!can_tx_frames1.enqueue(frame))
                log("TX ENQ Err CAN1", 15);
        }
    }
}

/* Just calls IsoTP_cb with the right interface number */
void IsoTP_Can0_cb(CAN_FRAME *frame)
{
    IsoTP_cb(frame, &Can0);
}

/* Just calls IsoTP_cb with the right interface number */
void IsoTP_Can1_cb(CAN_FRAME *frame)
{
    IsoTP_cb(frame, &Can1);
}

/* Initialization functions for different modes */
/* Initialization for sniffing
 * 
 * Sets mailboxes as follows:
 * 0 - Used for ISOTP, initialized when ISOTP is requested
 * 1 - unused
 * 2 - unused
 * 3 - unused
 * 4 - unused 
 * 5 - Default RX - accepts all standard messages
 * 6 - Default RX - accepts all extended
 * 7 - Default TX - automatically set by init function
 */
uint8_t Init_Sniff(uint8_t baud)
{
    if(baud == 0)
        autobaud(device);
    else
        device->init(baud_rates_table[baud]);
    
    device->setRXFilter(5, 0, 0, false);
    device->setRXFilter(6, 0, 0, true);
    
    if(device == &Can0)
    {
        device->setCallback(5, Sniff_Can0_cb);
        device->setCallback(6, Sniff_Can0_cb);
    }
    else
    {
        device->setCallback(5, Sniff_Can1_cb);
        device->setCallback(6, Sniff_Can1_cb);
    }
    initialized = 1;
    return 1; //TODO: Error Checking
}

/* Initialization for CITM 
 * 
 * Sets mailboxes as follows:
 * 0 - Used for ISOTP, initialized when ISOTP requested
 * 1 - unused
 * 2 - unused
 * 3 - unused
 * 4 - Default RX - accepts all standard messages
 * 5 - Default RX - accepts all extended messages
 * 6 - Default TX
 * 7 - Default TX (two TX mailboxes since there can be a lot of TX traffic)
 */
uint8_t Init_CITM(uint8_t baud)
{
    Can0.init(baud_rates_table[baud]);
    Can1.init(baud_rates_table[baud]);
    Can0.setNumTXBoxes(2);
    Can1.setNumTXBoxes(2);
    Can0.setRXFilter(4, 0, 0, false);
    Can0.setRXFilter(5, 0, 0, true);
    Can1.setRXFilter(4, 0, 0, false);
    Can1.setRXFilter(5, 0, 0, true);
    Can0.setCallback(4, CITM_Can0_cb);
    Can0.setCallback(5, CITM_Can0_cb);
    Can1.setCallback(4, CITM_Can1_cb);
    Can1.setCallback(5, CITM_Can1_cb);
    initialized = 1;
    return 1; //TODO: Error Checking
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

    // handle micros() rollover edge case where isotp_last_tx_time + isotp_sep_time < ULONG_MAX 
    // but the micros timer has already rolled over
    if(isotp_sep_time > 0 && micros() < isotp_last_tx_time)
    {
        unsigned long diff = ULONG_MAX - isotp_last_tx_time;
        if(diff >= isotp_sep_time)
            isotp_last_tx_time = ULONG_MAX - isotp_sep_time + 1;
    }
    
    // Check if we have isotp frames to send, and enough time has elapsed if rate limiting is requested
    if(isotp_tx_go > 0 && 
       ((isotp_sep_time == 0) || ((isotp_last_tx_time + isotp_sep_time) < micros())))
    {
        uint8_t num_bytes = (isotp_tx_length - isotp_tx_index > 7) ? 7 : (isotp_tx_length - isotp_tx_index);
        isotp_tx_buffer[isotp_tx_index - 1] = 0x20 | isotp_tx_PCIIndex; // Set PCI Byte

        CreateCanFrame(isotp_tx_arbid, isotp_tx_extended, num_bytes + 1, &isotp_tx_buffer[isotp_tx_index - 1], true, 0x00, &frame);
        if(SendFrame(frame) == 0) // Successfully sent
        {
            /* Move to the next frame and check if we're done */
            isotp_last_tx_time = micros();
            if(++isotp_tx_PCIIndex > 15)
                isotp_tx_PCIIndex = 0;
            isotp_tx_index += num_bytes;
            if(isotp_tx_index == isotp_tx_length)
            {
                isotp_tx_go = 0;
                isotp_tx_PCIIndex = 1;
                isotp_tx_index = 0;
                isotp_tx_length = 0;
                isotp_sep_time = 0;
            }
        }
    }

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
                log("Not Implemented", 15);
                break;

            case CMD_CAN_SEND_ISOTP:
                results = SendIsoTPFrame(serial_buffer);
                send(&results, CMD_CAN_SEND_ISOTP_RESULT, 1);
                break;
                
            case CMD_CAN_RECV_ISOTP:
                results = RecvIsoTPFrame(serial_buffer);
                send(&results, CMD_CAN_RECV_ISOTP_RESULT, 1);
                break;

            case CMD_CAN_SENDRECV_ISOTP:
                results = RecvIsoTPFrame(serial_buffer);
                results |= SendIsoTPFrame(serial_buffer);
                send(&results, CMD_CAN_SENDRECV_ISOTP_RESULT, 1);
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

uint8_t SendIsoTPFrame(uint8_t serial_buffer[])
{
    CAN_FRAME frame;
    uint8_t results;
    
    isotp_tx_arbid = ((uint32_t)serial_buffer[3] << 24) | 
                     ((uint32_t)serial_buffer[4] << 16) |
                     ((uint32_t)serial_buffer[5] << 8) |
                     (uint32_t)serial_buffer[6];
    isotp_rx_arbid = ((uint32_t)serial_buffer[7] << 24) | 
                     ((uint32_t)serial_buffer[8] << 16) |
                     ((uint32_t)serial_buffer[9] << 8) |
                     (uint32_t)serial_buffer[10];
    isotp_tx_extended = serial_buffer[11];

    /* If we're sending < 7 bytes, we can just send it */
    if(serial_buf_count <= 19)
    {
        serial_buffer[11] = serial_buf_count - 12; // Set the PCI byte for single
        CreateCanFrame(isotp_tx_arbid, isotp_tx_extended, serial_buf_count - 10,
                       &serial_buffer[11], true, 0x00, &frame);
        results = SendFrame(frame);
    }
    /* > 7 bytes. Send out the First PCI message, save off the rest of the data
       for after we get the FC message */
    else
    {
        if(mode == CMD_CAN_MODE_SNIFF_CAN0 || mode == CMD_CAN_MODE_SNIFF_CAN1)
        {
            device->setRXFilter(0, isotp_rx_arbid, (isotp_tx_extended) ? 0x1FFFFFFF : 0x7FF, isotp_tx_extended);
            device->setCallback(0, (mode == CMD_CAN_MODE_SNIFF_CAN0) ? IsoTP_Can0_cb : IsoTP_Can1_cb);
        }
        else if(mode == CMD_CAN_MODE_CITM)
        {
            Can0.setRXFilter(0, isotp_rx_arbid, (isotp_tx_extended) ? 0x1FFFFFFF : 0x7FF, isotp_tx_extended);
            Can0.setCallback(0, IsoTP_Can0_cb);
            Can1.setRXFilter(0, isotp_rx_arbid, (isotp_tx_extended) ? 0x1FFFFFFF : 0x7FF, isotp_tx_extended);
            Can1.setCallback(0, IsoTP_Can1_cb);
        }
        isotp_tx_go = 0;
        isotp_tx_index = 6;
        isotp_tx_length = serial_buf_count - 12;
        isotp_tx_PCIIndex = 1;
        /* Copy the data from the serial buffer into the isotp buffer */
        for(uint16_t i = isotp_tx_index; i < isotp_tx_length; i++)
            isotp_tx_buffer[i] = serial_buffer[i + 12];
        
        serial_buffer[10] = 0x10 | (isotp_tx_length >> 8); // Set the PCI byte for first
        serial_buffer[11] = (uint8_t)(isotp_tx_length & 0x00FF);
        CreateCanFrame(isotp_tx_arbid, isotp_tx_extended, 8, &serial_buffer[10], false, 0x00, &frame);
        results = SendFrame(frame);
    }

    return results;
}
 
uint8_t RecvIsoTPFrame(uint8_t serial_buffer[])
{
    isotp_tx_arbid = ((uint32_t)serial_buffer[3] << 24) | 
                     ((uint32_t)serial_buffer[4] << 16) |
                     ((uint32_t)serial_buffer[5] << 8) |
                     (uint32_t)serial_buffer[6];
    isotp_rx_arbid = ((uint32_t)serial_buffer[7] << 24) | 
                     ((uint32_t)serial_buffer[8] << 16) |
                     ((uint32_t)serial_buffer[9] << 8) |
                     (uint32_t)serial_buffer[10];
    isotp_tx_extended = serial_buffer[11];

    /* Start listening for a reply */
    if(mode == CMD_CAN_MODE_SNIFF_CAN0 || mode == CMD_CAN_MODE_SNIFF_CAN1)
    {
        device->setRXFilter(0, isotp_rx_arbid, (isotp_tx_extended) ? 0x1FFFFFFF : 0x7FF, isotp_tx_extended);
        device->setCallback(0, (mode == CMD_CAN_MODE_SNIFF_CAN0) ? IsoTP_Can0_cb : IsoTP_Can1_cb);
    }
    else if(mode == CMD_CAN_MODE_CITM)
    {
        Can0.setRXFilter(0, isotp_rx_arbid, (isotp_tx_extended) ? 0x1FFFFFFF : 0x7FF, isotp_tx_extended);
        Can0.setCallback(0, IsoTP_Can0_cb);
        Can1.setRXFilter(0, isotp_rx_arbid, (isotp_tx_extended) ? 0x1FFFFFFF : 0x7FF, isotp_tx_extended);
        Can1.setCallback(0, IsoTP_Can1_cb);
    }
    return 0; //TODO: Error checking
}


/*********************************************************************************************************
  END FILE
*********************************************************************************************************/


