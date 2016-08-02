#!/usr/bin/env python

import cancat
from dual_funcs import dualReplay

f_ms = cancat.FordInterface(port="/dev/tty.usbmodem1421", load_filename="data/ms_engine_start.dict")
f_hs = cancat.FordInterface(port="/dev/tty.usbmodem1411", load_filename="data/hs_engine_start.dict")

f_ms._reconnect()
f_hs._reconnect()

dualReplay(f_ms, f_hs, 0, 9434, 0, 13825)

