#!/usr/bin/env python

import cancat
import time

f = cancat.FordInterface(port="/dev/tty.usbmodem1421")

time.sleep(1)

for i in range(1,10):
    f.CANxmit(656, "\x88\x00\x01\x00\x00\x00\x00\x00")

