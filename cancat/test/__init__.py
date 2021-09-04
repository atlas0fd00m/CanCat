
import usb
import time
import queue
import logging
import unittest
import threading
import traceback

from rflib.const import *
from rflib.bits import ord23

logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
logger = logging.getLogger(__name__)

EP0BUFSIZE = 512


class fakeMemory:
    def __init__(self, size=64*1024):
        self.memory = [0 for x in range(size)]
        self.mmio = {}

    def readMemory(self, addr, size):
        logger.debug("fm.readMemory(0x%x, 0x%x)", addr, size)
        chunk = b''.join([b'%c' % x for x in self.memory[addr:addr+size]])
        if len(chunk) < size:
            chunk += b"@" * (size-len(chunk))
        return chunk

    def writeMemory(self, addr, data):
        logger.debug("fm.writeMemory(0x%x, %r)", addr, data)
        #if type(data) == str:
        #    raise(Exception("Cannot write 'str' to fakeMemory!  Must use 'bytes'"))

        for x in range(len(data)):
            tgt = addr+x
            val = data[x]

            handler = self.mmio.get(tgt)
            if handler is not None:
                val = handler(tgt, data[x])

            # if we didn't return None from the handler, write it anyway
            if val is not None:
                self.memory[tgt] = val

    '''
    def mmio_RFST(self, tgt, dbyte):
        logger.info('mmio_RFST(0x%x, %r)', tgt, dbyte)
        print("RFST==%x  (%x)" % (self.readMemory(X_RFST, 1), ord(dbyte)))


        # configure MARCSTATE
        val = ord(dbyte)
        if val in (2, 3):
            val = dbyte+10

        else:
            val = MARC_STATE_RX

        self.writeMemory(MARCSTATE, b'%c'%(val))

        # still set RFST
        return dbyte

    def mmio_MARCSTATE(self, tgt, dbyte):
        rfst = self.readMemory(X_RFST, 1)
        logger.info('mmio_MARCSTATE(0x%x, %r) rfst=%r', tgt, dbyte, rfst)
        return MARC_STATE_RX
    '''

# TODO: first, implement PING capability

class FakeCanCat:
    '''
    This class emulates a real CanCat (the physical device).
    '''
    def __init__(self):
        self._recvbuf = queue.Queue()
        self._outbuf = queue.Queue()  # this is what's handed to the CanCat receiver thread
        self.memory = fakeMemory()

        self.start_ts = time.time()

        self.memory.writeMemory(0xdf00, FAKE_MEM_DF00)
        self.memory.writeMemory(0xdf46, b'\xf0\x0d')
        for intreg, intval in list(FAKE_INTERRUPT_REGISTERS.items()):
            logger.info('setting interrupt register: %r = %r', intreg, intval)
            self.memory.writeMemory(eval(intreg), intval)

    def clock(self):
        return time.time() - self.start_ts

    def CanCat_send(data, cmd):
        packet = '@%c%c%s' % (len(data)+1, cmd, data)
        self._outbuf += packet

    #### FAKE SERIAL DEVICE (interface to Python)

