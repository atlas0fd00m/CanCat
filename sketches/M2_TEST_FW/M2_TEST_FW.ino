/**
 * This file provides the Arduino setup and loop functions, any general-purpose functionality such as 
 * creating and sending CAN frames and handles the serial communication.
 */

 /*   
  *  CAN Frames Per Second:
  *  
  *  For a CAN Frame with an 11-bit identifier and an 8 byte message length, the frame will be 111 bits total 
  *  length not accounting for any stuff bits. Frames per second is:
  *  1MPBS   - 9009
  *  500KBPs - 4504
  *  125KBPs - 1126
  *  
  *  11 bit identifier with 1 byte message length, frame will be 55 bits total length not accounting for 
  *  stuff bits.
  *  1MBPs   - 18181
  *  500KBPs - 9090
  *  125KPBs - 2272
  *  
  *  29-bit identifier with 8 byte message length, frame will be 131 bits total
  *  1MBPs   - 7633
  *  500KBPs - 3816
  *  125KBPs - 954
  *  
  *  29-bit identifier with 1 byte message length, frame will be 75 bits total
  *  1MBPs   - 13333
  *  500KBPs - 6666
  *  125KBPs - 1666
  */

#include <due_can.h>

#define Serial SerialUSB
CAN_FRAME frame_basic;
CAN_FRAME frame_extended;
uint8_t start_test_basic = 0;
uint8_t start_test_extended = 0;

/* Callback for Can 0 */
void CanRXCallback_basic(CAN_FRAME *frame)
{
    if(frame->data.bytes[0] == 'T' && frame->data.bytes[1] == 'E' && frame->data.bytes[2] == 'S' && frame->data.bytes[3] == 'T')
    {
        start_test_basic = 1;
    }
}

void CanRXCallback_extended(CAN_FRAME *frame)
{
    if(frame->data.bytes[0] == 'T' && frame->data.bytes[1] == 'E' && frame->data.bytes[2] == 'S' && frame->data.bytes[3] == 'T')
    {
        start_test_extended = 1;
    }
}

void setup()
{
    //start serial port
    Serial.begin(250000);

    // Start CAN peripheral
    Can0.init(1000000);
    Can0.setRXFilter(1, 0x10, 0x7FF, false);
    Can0.setRXFilter(0, 0x810, 0x1FFFFFFF, true);
    Can0.setCallback(1, CanRXCallback_basic);
    Can0.setCallback(0, CanRXCallback_extended);

    frame_basic.id = 0x00;
    frame_basic.extended = false;
    frame_basic.length = 1;
    frame_basic.data.byte[0] = 0;
    frame_basic.data.byte[1] = 0xAA;
    frame_basic.data.byte[2] = 0xAA;
    frame_basic.data.byte[3] = 0xAA;
    frame_basic.data.byte[4] = 0xAA;
    frame_basic.data.byte[5] = 0xAA;
    frame_basic.data.byte[6] = 0xAA;
    frame_basic.data.byte[7] = 0xAA;
    
    frame_extended.id = 0x800;
    frame_extended.extended = true;
    frame_extended.length = 1;
    frame_extended.data.byte[0] = 0;
    frame_extended.data.byte[1] = 0xAA;
    frame_extended.data.byte[2] = 0xAA;
    frame_extended.data.byte[3] = 0xAA;
    frame_extended.data.byte[4] = 0xAA;
    frame_extended.data.byte[5] = 0xAA;
    frame_extended.data.byte[6] = 0xAA;
    frame_extended.data.byte[7] = 0xAA;
}

void loop()
{
    if(start_test_basic == 1)
    {
        frame_basic.length = 1; // Send 1 byte CAN frames as fast as possible
        frame_basic.id = 0x00; // User arbid 0 for these messages
        for (int i = 0; i < 181810; i++) // Send ten seconds of messages
        {
            while(!Can0.sendFrame(frame_basic));
            frame_basic.data.byte[0]++;
        }
        frame_basic.data.byte[0] = 0;

        frame_basic.length = 8; // Send 8 byte CAN frames as fast as possible
        frame_basic.id = 0x01; // User arbid 1 for these messages
        for (int i = 0; i < 90090; i++) // Send ten seconds of messages
        {
            while(!Can0.sendFrame(frame_basic));
            frame_basic.data.byte[0]++;
        }
        frame_basic.data.byte[0] = 0;
        start_test_basic = 0;
    }

    
    if(start_test_extended == 1)
    {
        frame_extended.length = 1; // Send 1 byte CAN frames as fast as possible
        frame_extended.id = 0x800; // Use arbid 800 for these messages
        for (int i = 0; i < 133330; i++) // Send ten seconds of messages
        {
            while(!Can0.sendFrame(frame_extended));
            frame_extended.data.byte[0]++;
        }
        frame_extended.data.byte[0] = 0;

        frame_extended.length = 8; // Send 8 byte CAN frames as fast as possible
        frame_extended.id = 0x801; // Use arbid 801 for these messages
        for (int i = 0; i < 76330; i++) // Send ten seconds of messages
        {
            while(!Can0.sendFrame(frame_extended));
            frame_extended.data.byte[0]++;
        }
        frame_extended.data.byte[0] = 0;

        start_test_extended = 0;
    }
}        



/*********************************************************************************************************
  END FILE
*********************************************************************************************************/
