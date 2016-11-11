#include <due_can.h>
#include "queue.h"
#include "defines.h"

#define Serial SerialUSB

/* circular buffers for receiving and sending CAN frames */
Queue<CAN_FRAME> can_rx_frames0(32);
Queue<CAN_FRAME> can_rx_frames1(32);
Queue<CAN_FRAME> can_tx_frames0(16);
Queue<CAN_FRAME> can_tx_frames1(16);

/* Buffer for receiving serial commands */
uint8_t serial_buffer[SERIAL_BUF_SIZE];
uint8_t serial_buf_index = 0;
uint8_t serial_buf_count = 0;
uint8_t initialized = 0;

/* Functions for serial communication */
void send(unsigned char *data, unsigned char cmd, unsigned char len)
{
    Serial.write("@");
    Serial.write(len + 1);    // 1 for @
    Serial.write(cmd);
    Serial.write(data, len);
}

void log(char* msg, uint8_t len)
{
    send((unsigned char*)msg, CMD_LOG, len);
}

void logHex(uint32_t num)
{
    uint32_t temp = num;
    send((unsigned char*)&temp, CMD_LOG_HEX, 4);
}

void logHexStr(uint32_t num, char* prefix, uint32_t len)
{
    log(prefix, len);
    logHex(num);
}



/* CAN Callbacks */
void Can0_cb(CAN_FRAME *frame)
{
    if(!can_rx_frames0.enqueue(frame))
        log("RX ENQ Err CAN0", 15);
    if(!can_tx_frames1.enqueue(frame))
        log("TX ENQ Err CAN1", 15);
}

void Can1_cb(CAN_FRAME *frame)
{
    if(!can_rx_frames1.enqueue(frame))
        log("RX ENQ Err CAN1", 15);
    if(!can_tx_frames0.enqueue(frame))
        log("TX ENQ Err CAN0", 15);
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
        frame = can_tx_frames0.dequeue();
        if(!Can0.sendFrame(frame))
        {
            Serial.write("Error Sending on CAN0");
        }
    }
    if(!can_tx_frames1.isEmpty())
    {
        frame = can_tx_frames1.dequeue();
        if(!Can1.sendFrame(frame))
        {
            Serial.write("Error Sending on CAN1");
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
        send(buf, CMD_ISO_RECV, frame.length + 4);
    }

    // handle Serial-incoming data    
    for (uint32_t count = Serial.available(); count > 0; count--)
    {
        serial_buffer[serial_buf_index++] = Serial.read();
        if (serial_buf_index == 1)
        {
            serial_buf_count = serial_buffer[0];
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
        if(initialized == 0 && serial_buffer[1] != CMD_CAN_BAUD)
        {
            log("CAN Not Initialized", 19);
            // clear counters for next message
            serial_buf_index = 0;
            serial_buf_count = 0;
        }

        switch (serial_buffer[1])  // cmd byte
        {
            case CMD_CHANGE_BAUD:
                Serial.begin(*(unsigned int*)(serial_buffer+2));
                while (!Serial);
                send(&results, CMD_CHANGE_BAUD_RESULT, 1);
                break;
                
            case CMD_PING:
                send(serial_buffer+2, CMD_PING_RESPONSE, serial_buf_count-2);
                break;
                
            case CMD_CAN_BAUD:
                if(initialized == 0) // First init
                {
                    //Initialize CAN
                    Can0.init(baud_rates_table[serial_buffer[2]]);
                    Can1.init(baud_rates_table[serial_buffer[2]]);
                    Can0.setNumTXBoxes(2);
                    Can1.setNumTXBoxes(2);
                    Can0.watchFor();
                    Can1.watchFor();
                    Can0.setGeneralCallback(Can0_cb);
                    Can1.setGeneralCallback(Can1_cb);
                    initialized = 1;
                    results = 1; //TODO: Error checking
                    send(&results, CMD_CAN_BAUD_RESULT, 1);
                }
                else // Just changing the baud rate
                {
                    Can0.set_baudrate(baud_rates_table[serial_buffer[2]]);
                    Can1.set_baudrate(baud_rates_table[serial_buffer[2]]);
                    results = 1; //TODO: Error checking
                    send(&results, CMD_CAN_BAUD_RESULT, 1);
                }
                break;
                
            case CMD_CAN_SEND:
                frame.id = (uint32_t)serial_buffer[5] | 
                           ((uint32_t)serial_buffer[4] << 8) |
                           ((uint32_t)serial_buffer[3] << 16) |
                           ((uint32_t)serial_buffer[2] << 24);
                frame.extended = serial_buffer[6];
                frame.length = serial_buffer[0] - 7;
                for(uint8_t i = 0; i < frame.length; i++)
                {
                    frame.data.bytes[i] = serial_buffer[7+i];
                }
                if(!Can0.sendFrame(frame))
                {
                    log("Failed sending on Can0", 22);
                    results = 1;
                }
                if(!Can1.sendFrame(frame))
                {
                    log("Failed sending on Can1", 22);
                    results = 2;
                }

                //TODO: Only sending vehicle results back
                send(&results, CMD_CAN_SEND_RESULT, 1);
                
                break;

            case CMD_SET_FILT_MASK:
                log("Not Implemented", 15);
                
            default:
                Serial.write("@\x15\x03""BAD COMMAND: ");
                Serial.print(serial_buffer[1]);
                
        }
        // clear counters for next message
        serial_buf_index = 0;
        serial_buf_count = 0;
    }
}



/*********************************************************************************************************
  END FILE
*********************************************************************************************************/
