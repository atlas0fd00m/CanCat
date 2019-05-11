/* This file contains all of the code for general purpose use of the CanCat, e.g, sniffing and sending messages */

#include <due_can.h>
#include "autobaud.h"
#include "defines.h"

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

    // Disable unused mailboxes
    device->mailbox_set_mode(0, 0);
    device->mailbox_set_mode(1, 0);
    device->mailbox_set_mode(2, 0);
    device->mailbox_set_mode(3, 0);
    device->mailbox_set_mode(4, 0);

    // Set up mailbox 5 to receive basic and mailbox 6 to receive extended messages
    device->setRXFilter(5, 0, 0, true);
    device->setRXFilter(6, 0, 0, false);
    
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
