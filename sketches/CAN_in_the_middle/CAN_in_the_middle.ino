// Protocol:
// PC->Duino:  <size><cmd><data>  where size includes cmd and data but not the size byte itself
// Duino->PC:  @<size><cmd><data> where size includes cmd and data
// 
// CAN in the middle uses two CAN shields on one Arduino. This black magic is accomplished by modifying
// one of the CAN shields to use D10 as CS instead of D9. This is accomplished by cutting a trace on the bottom
// of the board and bridging another pad. The CAN shield using D10 as CS is the ISOLATION side (connect directly
// to the device under test). The unmodified CAN shield is then the VEHICLE side.
//
// All traffic received on the VEHICLE side is retransitted on the ISOLATION side, and vice versa. All 
// traffic received is pushed up to the PC as per CAN_haz_bus operation. Additionally, anything received
// on the ISOLATION side is logged to the console.

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
#define CMD_ISO_RECV             0x35
#define CMD_SET_FILT_MASK        0x36

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
uint8_t initialized = 0;



MCP_CAN VEH_CAN(9);     // Set CS to pin 9
MCP_CAN ISO_CAN(10);    // Set CS to pin 10




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
    // handle CAN-incoming data on Vehicle side
    if(initialized == 1 && CAN_MSGAVAIL == VEH_CAN.checkReceive()) // check if data coming on vehicle side
    {
        int results = CAN_FAIL;
        int failcnt = 0;
        VEH_CAN.readMsgBufID(&canId, &len, buf+4);    // read data,  len: data length, buf: data buf
        
        while(results != CAN_OK && failcnt < 10)
        {
            results = ISO_CAN.sendMsgBuf(canId, 0, len, buf+4);     // Re-send this data on the isolation side
            failcnt++;
        }
        if(failcnt >= 10) 
            logHexStr(results, "ISO SEND FAIL", 13);
        
        buf[0] = (canId >> 24) & 0xff;
        buf[1] = (canId >> 16) & 0xff;
        buf[2] = (canId >> 8) & 0xff;
        buf[3] = canId & 0xff;
        // FIXME: grab extflags and put in here.
        
        send(buf, CMD_CAN_RECV, len + 4);
    }

    // handle CAN-incoming data on Isolation side
    if(initialized == 1 && CAN_MSGAVAIL == ISO_CAN.checkReceive()) // check if data coming on isolation side
    {
        int results = CAN_FAIL;
        int failcnt = 0;
        ISO_CAN.readMsgBufID(&canId, &len, buf+4);    // read data,  len: data length, buf: data buf
        
        while(results != CAN_OK && failcnt < 10)
        {
            results = VEH_CAN.sendMsgBuf(canId, 0, len, buf+4);     // Re-send this data on the Vehicle side
            failcnt++;
        }
        if(failcnt >= 10) 
            logHexStr(results, "VEH SEND FAIL", 13);

        buf[0] = (canId >> 24) & 0xff;
        buf[1] = (canId >> 16) & 0xff;
        buf[2] = (canId >> 8) & 0xff;
        buf[3] = canId & 0xff;
        // FIXME: grab extflags and put in here.
        
        send(buf, CMD_CAN_RECV, len + 4);
        send(buf, CMD_ISO_RECV, len+4);
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
        int fail_veh = -1;
        int fail_iso = -1;
        INT8U results_veh = CAN_FAIL;
        INT8U results_iso = CAN_FAIL;

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
KEEP_TRYING_ISO:
                if(CAN_OK == ISO_CAN.begin(baud))                   // init can bus : baudrate = 500k
                {
                    results_iso = 1;
                    send(&results_iso, CMD_CAN_BAUD_RESULT, 1);
                }
                else
                {
                    results_iso = 0;
                    send(&results_iso, CMD_CAN_BAUD_RESULT, 1);
                    delay(100);
                    goto KEEP_TRYING_ISO;
                }
    
KEEP_TRYING_VEH:
                if(CAN_OK == VEH_CAN.begin(baud))                   // init can bus : baudrate = 500k
                {
                    results_veh = 1;
                    send(&results_veh, CMD_CAN_BAUD_RESULT, 1);
                    initialized = 1;
                }
                else
                {
                    results_veh = 0;
                    send(&results_veh, CMD_CAN_BAUD_RESULT, 1);
                    delay(100);
                    goto KEEP_TRYING_VEH;
                }
                break;
                
            case CMD_CAN_SEND:
                // len, cmd, canid, canid2, extflag
                canId = (INT32U)inbuf[6] | 
                        ((INT32U)inbuf[5] << 8) |
                        ((INT32U)inbuf[4] << 16) |
                        ((INT32U)inbuf[3] << 24);
                extflag = inbuf[7];
                len = inbufcount - 8;
                while(results_veh != CAN_OK && 
                      results_iso != CAN_OK &&
                      fail_veh < 10 &&
                      fail_iso < 10)
                {
                    if(results_veh != CAN_OK)
                    {
                        results_veh = VEH_CAN.sendMsgBuf(canId, extflag, len, inbuf+7);
                        fail_veh++;
                    }
                    if(results_iso != CAN_OK)
                    {
                        results_iso = ISO_CAN.sendMsgBuf(canId, extflag, len, inbuf+7);
                        fail_iso++;
                    }                    
                }
                if(fail_veh >= 10 || fail_iso >= 10)
                {
                    logHexStr(results, "Send failed. Error: ", 20);
                }

                //TODO: Only sending vehicle results back
                send(&results_veh, CMD_CAN_SEND_RESULT, 1);
                
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
                        VEH_CAN.init_Mask((i / 4) - 1, 0, val);
                        ISO_CAN.init_Mask((i / 4) - 1, 0, val);
                    }
                    else // Rest are filters
                    {
                        VEH_CAN.init_Filt((i / 4) - 3, 0, val);
                        ISO_CAN.init_Filt((i / 4) - 3, 0, val);
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
