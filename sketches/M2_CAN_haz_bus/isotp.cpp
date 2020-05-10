/* This file contains all the code related to ISOTP processing */

#include <due_can.h>
#include <limits.h>
#include <stdint.h>
#include "defines.h"

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
                device->mailbox_set_mode(0, 0); // Disable ISOTP Mailbox
                device->detachCANInterrupt(0);
            }
            else
            {
                Can0.mailbox_set_mode(0, 0); // Disable ISOTP Mailbox
                Can0.detachCANInterrupt(0);
                Can1.mailbox_set_mode(0, 0); // Disable ISOTP Mailbox
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
                device->mailbox_set_mode(0, 0); // Disable ISOTP Mailbox
                device->detachCANInterrupt(0);
            }
            else
            {
                Can0.mailbox_set_mode(0, 0); // Disable ISOTP Mailbox
                Can0.detachCANInterrupt(0);
                Can1.mailbox_set_mode(0, 0); // Disable ISOTP Mailbox
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

/* Handle any outstanding IsoTP stuff */
void process_isotp()
{
    CAN_FRAME frame = {0};

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
}


uint8_t SendIsoTPFrame(uint8_t serial_buffer[], uint16_t serial_buf_count)
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
            device->mailbox_set_mode(0, CAN_MB_RX_MODE); // Enable mailbox
        }
        else if(mode == CMD_CAN_MODE_CITM)
        {
            Can0.setRXFilter(0, isotp_rx_arbid, (isotp_tx_extended) ? 0x1FFFFFFF : 0x7FF, isotp_tx_extended);
            Can0.setCallback(0, IsoTP_Can0_cb);
            Can0.mailbox_set_mode(0, CAN_MB_RX_MODE); // Enable mailbox
            Can1.setRXFilter(0, isotp_rx_arbid, (isotp_tx_extended) ? 0x1FFFFFFF : 0x7FF, isotp_tx_extended);
            Can1.setCallback(0, IsoTP_Can1_cb);
            Can1.mailbox_set_mode(0, CAN_MB_RX_MODE); // Enable mailbox
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
        device->mailbox_set_mode(0, CAN_MB_RX_MODE); // Enable mailbox
    }
    else if(mode == CMD_CAN_MODE_CITM)
    {
        Can0.setRXFilter(0, isotp_rx_arbid, (isotp_tx_extended) ? 0x1FFFFFFF : 0x7FF, isotp_tx_extended);
        Can0.setCallback(0, IsoTP_Can0_cb);
        Can0.mailbox_set_mode(0, CAN_MB_RX_MODE); // Enable mailbox
        Can1.setRXFilter(0, isotp_rx_arbid, (isotp_tx_extended) ? 0x1FFFFFFF : 0x7FF, isotp_tx_extended);
        Can1.setCallback(0, IsoTP_Can1_cb);
        Can1.mailbox_set_mode(0, CAN_MB_RX_MODE); // Enable mailbox
    }
    return 0; //TODO: Error checking
}
