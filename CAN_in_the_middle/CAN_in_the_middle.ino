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

#define CMD_PING                 0x41
#define CMD_CHANGE_BAUD          0x42
#define CMD_CAN_BAUD             0x43
#define CMD_CAN_SEND             0x44

unsigned char len = 0;
unsigned char buf[MAX_BUF_SIZE];

unsigned int count = 0;
unsigned char inbuf[MAX_BUF_SIZE];
unsigned char inbufcount = 0;
unsigned char inbufidx = 0;
INT32U canId;
INT8U results;
INT8U  extflag;
INT8U baud = CAN_500KBPS;



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
    Serial.begin(115200);//345600);

START_ISO_INIT:

    if(CAN_OK == ISO_CAN.begin(baud))                   // init can bus : baudrate = 500k
    {
        Serial.write("@\x05\x01INIT", 7);
    }
    else
    {
        Serial.write("@\x05\x02""FAIL", 7);
        delay(100);
        goto START_ISO_INIT;
    }

START_VEH_INIT:

    if(CAN_OK == VEH_CAN.begin(baud))                   // init can bus : baudrate = 500k
    {
        Serial.write("@\x05\x01INIT", 7);
    }
    else
    {
        Serial.write("@\x05\x02""FAIL", 7);
        delay(100);
        goto START_VEH_INIT;
    }
   
    
    while (!Serial);
}


void loop()
{
    // handle CAN-incoming data on Vehicle side
    if(CAN_MSGAVAIL == VEH_CAN.checkReceive()) // check if data coming on vehicle side
    {
        int results = CAN_FAIL;
        int failcnt = 0;
        VEH_CAN.readMsgBufID(&canId, &len, buf+4);    // read data,  len: data length, buf: data buf
        
        while(results != CAN_OK && failcnt < 10)
        {
            results = ISO_CAN.sendMsgBuf(canId, 0, len, buf+4);     // Re-send this data on the isolation side
            failcnt++;
        }
        //if(failcnt >= 10) logHexStr(results, "ISO SEND FAIL", 13);
        // requires a binary client on the other end.  this should be python
        
        buf[0] = (canId >> 24) & 0xff;
        buf[1] = (canId >> 16) & 0xff;
        buf[2] = (canId >> 8) & 0xff;
        buf[3] = canId & 0xff;
        // FIXME: grab extflags and put in here.
        
        send(buf, CMD_CAN_RECV, len + 4);
    }

    // handle CAN-incoming data on Isolation side
    if(CAN_MSGAVAIL == ISO_CAN.checkReceive()) // check if data coming on isolation side
    {
        int results = CAN_FAIL;
        int failcnt = 0;
        ISO_CAN.readMsgBufID(&canId, &len, buf+4);    // read data,  len: data length, buf: data buf
        
        while(results != CAN_OK && failcnt < 10)
        {
            results = VEH_CAN.sendMsgBuf(canId, 0, len, buf+4);     // Re-send this data on the Vehicle side
            failcnt++;
        }
        //if(failcnt >= 10) logHexStr(results, "VEH SEND FAIL", 13);
        

        // requires a binary client on the other end.  this should be python
        
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
        if (inbufidx==1)
        {
            inbufcount = inbuf[0];
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

        switch (inbuf[1])  // cmd byte
        {
            case CMD_CHANGE_BAUD:
                Serial.begin(*(unsigned int*)(inbuf+2));
                while (!Serial);
                send(&results, CMD_CHANGE_BAUD_RESULT, 1);
                break;
                
            case CMD_PING:
                send(inbuf+2, CMD_PING_RESPONSE, inbufcount-2);
                break;
                
            case CMD_CAN_BAUD:
                baud = inbuf[2];
KEEP_TRYING_ISO:
                if(CAN_OK == ISO_CAN.begin(baud))                   // init can bus : baudrate = 500k
                {
                    Serial.write("@\x05\x01INIT", 7);
                }
                else
                {
                    Serial.write("@\x05\x02""FAIL", 7);
                    delay(100);
                    goto KEEP_TRYING_ISO;
                }
    
KEEP_TRYING_VEH:
                if(CAN_OK == VEH_CAN.begin(baud))                   // init can bus : baudrate = 500k
                {
                    Serial.write("@\x05\x01INIT", 7);
                }
                else
                {
                    Serial.write("@\x05\x02""FAIL", 7);
                    delay(100);
                    goto KEEP_TRYING_VEH;
                }
                while (!Serial);
                break;
                
            case CMD_CAN_SEND:
                //log("sending", 7);
                // len, cmd, canid, canid2, extflag
                canId = (INT32U)inbuf[5] | 
                        ((INT32U)inbuf[4] << 8) |
                        ((INT32U)inbuf[3] << 16) |
                        ((INT32U)inbuf[2] << 24);
                extflag = inbuf[6];
                len = inbuf[0] - 7;
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
                //TODO: Only sending vehicle results back
                send(&results_veh, CMD_CAN_SEND_RESULT, 1);
                
                break;
                
            default:
                Serial.write("@\x15\x03""BAD COMMAND: ");
                Serial.print(inbuf[1]);
                
        }
        // clear counters for next message
        inbufidx = 0;
        inbufcount = 0;
    }
}

/*********************************************************************************************************
  END FILE
*********************************************************************************************************/
