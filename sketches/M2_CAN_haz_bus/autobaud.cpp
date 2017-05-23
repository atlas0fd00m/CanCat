#include <due_can.h>
#include "defines.h"

/* Attempts to determine the baud rate using the autobaud feature in the CAN peripheral */
void autobaud(CANRaw *device)
{
    uint32_t reg_val;

    device->disable();
    device->enable_autobaud_listen_mode();

    for(int i = 1; i < NUM_BAUD_RATES; i++)
    {
        device->init(baud_rates_table[i]);
        delay(10);
        reg_val = device->get_status();

        // Check that the status register indicates that the bus is running and no errors
        if(((reg_val & 0xFFFFFF00) != 0) && ((reg_val & 0x0F000000) == 0))
        {
            char baud_msg[128];
            sprintf(baud_msg, "Found baudrate: %4dKBPS", baud_rates_table[i] / 1000);
            log(baud_msg, 24);
            device->disable_autobaud_listen_mode();
            break;
        }
    }
}


