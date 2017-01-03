// Protocol:
// PC->Duino:  <size><cmd><data>  where size includes cmd and data but not the size byte itself
// Duino->PC:  @<size><cmd><data> where size includes cmd and data

#include <SPI.h>
#include "mcp_can.h"

#define MAX_BUF_SIZE  207


#define CMD_LOG                  0x2f
#define CMD_LOG_HEX              0x2e

#define CMD_CAN_RECV             0x30
#define CMD_PING_RESPONSE        0x31
#define CMD_CHANGE_BAUD_RESULT   0x32
#define CMD_CAN_BAUD_RESULT      0x33
#define CMD_CAN_SEND_RESULT      0x34
#define CMD_SET_FILT_MASK        0x36 // 0x35 is used by CAN in the middle

#define CMD_PING                 0x41
#define CMD_CHANGE_BAUD          0x42
#define CMD_CAN_BAUD             0x43
#define CMD_CAN_SEND             0x44

unsigned char len = 0;
unsigned char buf[MAX_BUF_SIZE];

uint32_t count = 0;
uint8_t inbuf[MAX_BUF_SIZE];
uint16_t inbufcount = 0;
uint16_t inbufidx = 0;
INT32U canId;
INT8U results;
INT8U  extflag;
INT8U baud = CAN_500KBPS;
uint16_t failCnt = 0;
uint8_t initialized = 0;



MCP_CAN CAN(9);                                            // Set CS to pin 10




void send(unsigned char *data, unsigned char cmd, unsigned char len)
{
    Serial.write("@");
    Serial.write(len + 1);    // 1 for @
    Serial.write(cmd);
    Serial.write(data, len);
}

void log(char* msg, INT8U len)
{
    send((unsigned char*)msg, CMD_LOG, len);
}

void logHex(INT32U num)
{
    INT32U temp = num;
    send((unsigned char*)&temp, CMD_LOG_HEX, 4);
}

void logHexStr(INT32U num, char* prefix, int len)
{
    log(prefix, len);
    logHex(num);
}

void setup()
{
    Serial.begin(500000);
    while (!Serial);
}


void loop()
{
    // handle CAN-incoming data
    if(initialized == 1 && CAN_MSGAVAIL == CAN.checkReceive())            // check if data coming
    {
        CAN.readMsgBufID(&canId, &len, buf+4);    // read data,  len: data length, buf: data buf

        // requires a binary client on the other end.  this should be python
        
        buf[0] = (canId >> 24) & 0xff;
        buf[1] = (canId >> 16) & 0xff;
        buf[2] = (canId >> 8) & 0xff;
        buf[3] = canId & 0xff;
        // FIXME: grab extflags and put in here.
        
        send(buf, CMD_CAN_RECV, len + 4);
    }

    // handle Serial-incoming data    
    for (count=Serial.available(); count>0; count--)
    {
        //logHexStr((INT32U)count, "readloopcount", 13);
        inbuf[inbufidx++] = Serial.read();
        if (inbufidx==2)
        {
            inbufcount = inbuf[0] << 8u | inbuf[1];
            //logHexStr(inbufcount, "Setting inbufcount", 17);
        }
        
        if (inbufidx == inbufcount)
        // we've got enough of the packet
        {
            count = 1;  // exit the loop
        }        
    }

    // if we've received an entire message, process it here
    if (inbufidx && inbufidx == inbufcount)
    {
        // Check if we've been initialized and we're not trying to initialize
        if(initialized == 0 && inbuf[2] != CMD_CAN_BAUD)
        {
            log("CAN Not Initialized", 19);
            goto NOT_INITIALIZED;
        }
            
        switch (inbuf[2])  // cmd byte
        {
            case CMD_CHANGE_BAUD:
                Serial.begin(*(unsigned int*)(inbuf+3));
                while (!Serial);
                send(&results, CMD_CHANGE_BAUD_RESULT, 1);
                break;
                
            case CMD_PING:
                send(inbuf+3, CMD_PING_RESPONSE, inbufcount-3);
                break;
                
            case CMD_CAN_BAUD:
                baud = inbuf[3];
KEEP_TRYING:
                if(CAN_OK == CAN.begin(baud))                   // init can bus : baudrate = 500k
                {
                    results = 1;
                    send(&results, CMD_CAN_BAUD_RESULT, 1);
                    initialized = 1;
                }
                else
                {
                    results = 0;
                    send(&results, CMD_CAN_BAUD_RESULT, 1);
                    delay(100);
                    goto KEEP_TRYING;
                }
    
                while (!Serial);
                break;
                
            case CMD_CAN_SEND:
                //log("sending", 7);
                // len, cmd, canid, canid2, extflag
                canId = inbuf[6] | 
                        (inbuf[5] << 8) |
                        (inbuf[4] << 16) |
                        (inbuf[3] << 24);
                extflag = inbuf[7];
                len = inbufcount - 8;
                failCnt = 0;
                do
                {
                  results = CAN.sendMsgBuf(canId, extflag, len, inbuf+8);
                  if(results != CAN_OK)
                  {
                    failCnt++;
                  }
                } while (results != CAN_OK && failCnt < 100);
                send(&results, CMD_CAN_SEND_RESULT, 1);
                if(failCnt >= 100)
                {
                    logHexStr(results, "Send failed. Error: ", 20);
                }
                
                break;

            case CMD_SET_FILT_MASK:
                // Loop through all 8 values (2 masks, 6 filters) and set them
                for(uint8_t i = 6; i <=34; i += 4)
                {
                    uint32_t val = inbuf[i] | 
                                   (inbuf[i - 1] << 8) |
                                   (inbuf[i - 2] << 16) |
                                   (inbuf[i - 3] << 24);
                    if(i <= 10) // First two are masks
                    {
                        CAN.init_Mask((i / 4) - 1, 0, val);
                    }
                    else // Rest are filters
                    {
                        CAN.init_Filt((i / 4) - 3, 0, val);
                    }
                }
                
                
            default:
                Serial.write("@\x15\x03BAD COMMAND: ");
                Serial.print(inbuf[2]);
                
        }
NOT_INITIALIZED:
        // clear counters for next message
        inbufidx = 0;
        inbufcount = 0;
        
    }
}

/*********************************************************************************************************
  END FILE
*********************************************************************************************************/

