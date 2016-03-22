#!/usr/bin/env python

import cancat

f = cancat.FordInterface(port="/dev/tty.usbmodem1421")

f.CANxmit(58, "\x81\x4f\x00\x02\x00\x00\x00\x00")

