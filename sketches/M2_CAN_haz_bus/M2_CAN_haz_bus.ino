// Protocol:
// PC->Duino:  <size><cmd><data>  where size includes cmd and data but not the size byte itself
// Duino->PC:  @<size><cmd><data> where size includes cmd and data

/*
  http://ww1.microchip.com/downloads/en/DeviceDoc/21801e.pdf
  http://en.wikipedia.org/wiki/CAN_bus
  http://en.wikipedia.org/wiki/OBD-II_PIDs

  The due_can library files also contain important information.
  
  This sketch is configured to work with the 'Macchina' Automotive Interface board 
  manufactured by RechargeCar Inc. CS_PIN and INT_PIN are specific to this board.
  
*/
// Arduino Due - CAN Sample 1
// Brief CAN example for Arduino Due
// Test the transmission from CAN0 Mailbox 0 to CAN1 Mailbox 0
// By Thibaut Viard/Wilfredo Molina/Collin Kidder 2013

// Required libraries
#include "variant.h"
#include <due_can.h>

#define MAX_BUF_SIZE  207

#define CMD_LOG                  0x2f
#define CMD_LOG_HEX              0x2e

#define CMD_CAN_RECV             0x30
#define CMD_PING_RESPONSE        0x31
#define CMD_CHANGE_BAUD_RESULT   0x32
#define CMD_CAN_BAUD_RESULT      0x33
#define CMD_CAN_SEND_RESULT      0x34

#define CMD_PING                 0x41
#define CMD_CHANGE_BAUD          0x42
#define CMD_CAN_BAUD             0x43
#define CMD_CAN_SEND             0x44

#define CC_STATE_BRIDGE   0
#define CC_STATE_DUAL     1

uint8_t CCstate = CC_STATE_BRIDGE;
uint8_t len = 0;
uint8_t buf[MAX_BUF_SIZE];

uint32_t count = 0;
uint8_t  inbuf[MAX_BUF_SIZE];
uint8_t  inbufcount = 0;
uint8_t  inbufidx = 0;
uint32_t canId;
uint8_t  results;
uint8_t  extflag;
uint32_t sbaud = 115200;
uint32_t baud0 = CAN_BPS_250K;
uint32_t baud1 = CAN_BPS_250K;

//Frame CanMsg;
CAN_FRAME frame0, frame1, incoming;

uint8_t BAUD_LIST[] =
{
    CAN_BPS_1000K,
    CAN_BPS_800K,
    CAN_BPS_500K,
    CAN_BPS_250K,
    CAN_BPS_125K,
    CAN_BPS_50K,
    CAN_BPS_33333,
    CAN_BPS_25K,
    CAN_BPS_10K,
    CAN_BPS_5K,
};

// Pin definitions specific to how the MCP2515 is wired up.
#define CS_PIN    85
#define RESET_PIN  7
#define INT_PIN    84

// Create CAN object with pins as defined
//MCP2515 CAN(CS_PIN, RESET_PIN, INT_PIN);

//byte intFlag;

//void CANHandler() {
//	CAN.intHandler();
//        intFlag = 1;
//}

void send(uint8_t *data, uint8_t cmd, uint8_t len)
{
    SerialUSB.write("@");
    SerialUSB.write(len + 1);    // 1 for cmd
    SerialUSB.write(cmd);
    SerialUSB.write(data, len);
}

void log(char* msg, uint8_t len)
{
    send((uint8_t*)msg, CMD_LOG, len);
}

void logHex(uint32_t num)
{
    uint32_t temp = num;
    send((uint8_t*)&temp, CMD_LOG_HEX, 4);
}

void logHexStr(uint32_t num, char* prefix, int len)
{
    log(prefix, len);
    logHex(num);
}


void setup() {
    // put your setup code here, to run once:  
    SerialUSB.begin(sbaud);
	

START_INIT:
    // NOTE! This speed might need to change. Usually 250 or 500
    if(//CAN.Init(baud,16))
          Can0.begin(baud0) && Can1.begin(baud1))   //FIXME: HANDLE CAN BUS SPEEDS SEPARATELY
   
    {
        SerialUSB.write("@\x05\x01INIT", 7);
    }
    else
    {
        log("FAIL on INIT", 12);
        delay(100);
        goto START_INIT;
    }
    
    while (!SerialUSB);

    //attachInterrupt(6, CANHandler, FALLING); // ????
    
	  //CAN.InitFilters(false);
	  //CAN.SetRXMask(MASK0, 0x7F8, 0); //match all but bottom four bits
        //CAN.SetRXFilter(FILTER0, 0x7E8, 0); // Allows 0x7E8 through 0x7EF, 
                                      // to allow responses from up to 8 ECUs,
                                      // per the 2008 OBD requirements
    //SerialUSB.println("MCP2515 Ready ...");
}

void loop() {
  // put your main code here, to run repeatedly:
  
    // handle CAN-incoming data
    if (Can0.available() > 0)
    {
        Can0.read(frame0);
        // copy along to other side
        Can1.sendFrame(frame0);
        
        canId = frame0.id;
        buf[0] = (canId >> 24) & 0xff;
        buf[1] = (canId >> 16) & 0xff;
        buf[2] = (canId >> 8) & 0xff;
        buf[3] = canId & 0xff;
        // FIXME: grab extflags and put in here.
        buf[4] = (frame0.fid | (frame0.rtr<<1) | (frame0.extended << 2));
        len = frame0.length;
        memcpy(&buf[5], frame0.data.bytes, len);
        
        send(buf, CMD_CAN_RECV, len + 5);
    }

    // handle CAN-incoming data
    if (Can1.available() > 0)
    {
        Can1.read(frame0);
        // copy along to other side
        Can0.sendFrame(frame0);

        canId = frame0.id;
        buf[0] = (canId >> 24) & 0xff;
        buf[1] = (canId >> 16) & 0xff;
        buf[2] = (canId >> 8) & 0xff;
        buf[3] = canId & 0xff;
        // FIXME: grab extflags and put in here.
        buf[4] = (frame0.fid | (frame0.rtr<<1) | (frame0.extended << 2));
        len = frame0.length;
        memcpy(&buf[5], frame0.data.bytes, len);
        
        send(buf, CMD_CAN_RECV, len + 5);
    }

    // handle SerialUSB-incoming data    
    for (count=SerialUSB.available(); count>0; count--)
    {
        //logHexStr((uint32_t)count, "readloopcount", 13);
        inbuf[inbufidx++] = SerialUSB.read();
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
        switch (inbuf[1])  // cmd byte
        {
            case CMD_CHANGE_BAUD:
                SerialUSB.begin(*(uint32_t*)(inbuf+2));
                while (!SerialUSB);
                send(&results, CMD_CHANGE_BAUD_RESULT, 1);
                break;
                
            case CMD_PING:
                send(inbuf+2, CMD_PING_RESPONSE, inbufcount-2);
                break;
                
            case CMD_CAN_BAUD:
                sbaud = BAUD_LIST[inbuf[2]];
KEEP_TRYING:
                if (Can0.set_baudrate(sbaud))                   // init can bus : baudrate = 500k
                {
                    SerialUSB.write("@\x05\x01INIT", 7);
                }
                else
                {
                    log("FAIL on reINIT", 14);
                    delay(100);
                    goto KEEP_TRYING;
                }
    
                while (!SerialUSB);
                break;
                
            case CMD_CAN_SEND:
                //log("sending", 7);
                // len, cmd, canid, canid2, extflag
                canId = inbuf[5] | 
                        (inbuf[4] << 8) |
                        (inbuf[3] << 16) |
                        (inbuf[2] << 24);
                extflag = inbuf[6];
                len = inbuf[0] - 7;
                
                //results = CAN.sendMsgBuf(canId, extflag, len, inbuf+7);
                frame0.id = canId;
                frame0.fid
                = (extflag >> 0)&1;
                frame0.rtr = (extflag >> 1)&1;
                frame0.extended = (extflag >> 2)&1;
                //CanMsg.dlc = (extflag >> 3)&1;
                frame0.length = len;
                memcpy(frame0.data.bytes, inbuf+7, len);
                //CAN.EnqueueTX(CanMsg);
                Can0.sendFrame(frame0);
                Can1.sendFrame(frame0);
                
                send(&results, CMD_CAN_SEND_RESULT, 1);
                
                break;
                
            default:
                SerialUSB.write("@\x15\x03BAD COMMAND: ");
                SerialUSB.print(inbuf[1]);
                
        }
        // clear counters for next message
        inbufidx = 0;
        inbufcount = 0;

/*
  //By default there are 7 mailboxes for each device that are RX boxes
  //This sets each mailbox to have an open filter that will accept extended
  //or standard frames
  int filter;
  //extended
  for (filter = 0; filter < 3; filter++) {
  Can0.setRXFilter(filter, 0, 0, true);
  Can1.setRXFilter(filter, 0, 0, true);
  }  
  //standard
  //for (int filter = 3; filter < 7; filter++) {
  //Can0.setRXFilter(filter, 0, 0, false);
  //Can1.setRXFilter(filter, 0, 0, false);
  //}  
*/
    }

}
