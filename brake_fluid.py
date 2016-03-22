#!/usr/bin/env python

import cancat

f = cancat.FordInterface(port="/dev/tty.usbmodem1421")

f.CANxmit(656, "\x88\x00\x01\x00\x00\x00\x00\x00")

