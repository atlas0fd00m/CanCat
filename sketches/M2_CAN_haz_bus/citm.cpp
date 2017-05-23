/* This file contains the code pertaining to CITM */

#include <due_can.h>
#include "defines.h"

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

