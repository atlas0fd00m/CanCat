
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

## Serial Commands ##
CMD_LOG                 = 0x2f
CMD_LOG_HEX             = 0x2e

CMD_CAN_RECV                   = 0x30
CMD_PING_RESPONSE              = 0x31
CMD_CHANGE_BAUD_RESULT         = 0x32
CMD_CAN_BAUD_RESULT            = 0x33
CMD_CAN_SEND_RESULT            = 0x34
CMD_ISO_RECV                   = 0x35
CMD_SET_FILT_MASK              = 0x36
CMD_CAN_MODE_RESULT            = 0x37
CMD_CAN_SEND_ISOTP_RESULT      = 0x38
CMD_CAN_RECV_ISOTP_RESULT      = 0x39
CMD_CAN_SENDRECV_ISOTP_RESULT  = 0x3A
CMD_PRINT_CAN_REGS             = 0x3C

CMD_PING                = 0x41
CMD_CHANGE_BAUD         = 0x42
CMD_CAN_BAUD            = 0x43
CMD_CAN_SEND            = 0x44
CMD_CAN_MODE            = 0x45
CMD_CAN_MODE_SNIFF_CAN0 = 0x00
CMD_CAN_MODE_SNIFF_CAN1 = 0x01
CMD_CAN_MODE_CITM       = 0x02
CMD_CAN_SEND_ISOTP      = 0x46
CMD_CAN_RECV_ISOTP      = 0x47
CMD_CAN_SENDRECV_ISOTP  = 0x48

# TODO: first, implement PING capability



class FakeCanCat:
    '''
    This class emulates a real CanCat (the physical device).
    We're going to try making this single-threaded.  We may need to handle in/out in separate threads, but fingers crossed.
    '''
    def __init__(self):
        self._inbuf = b''
        self._outbuf = b''

        self._inq = queue.Queue()
        self._outq = queue.Queue()  # this is what's handed to the CanCat receiver thread
        self.memory = fakeMemory()

        self.start_ts = time.time()

        #self.memory.writeMemory(0xdf00, FAKE_MEM_DF00)
        #self.memory.writeMemory(0xdf46, b'\xf0\x0d')
        #for intreg, intval in list(FAKE_INTERRUPT_REGISTERS.items()):
        #    logger.info('setting interrupt register: %r = %r', intreg, intval)
        #    self.memory.writeMemory(eval(intreg), intval)

        # do we want to add in a few CAN messages to be received?

    def clock(self):
        return time.time() - self.start_ts

    def CanCat_send(self, data, cmd):
        print(b'===FakeCanCat_send: cmd:%x data: %r' % (cmd, data))
        packet = b'@%c%c%s' % (len(data)+1, cmd, data)
        self._inq.put(packet)

    def log(self, msg):
        self.CanCat_send(b"FakeCanCat: " + msg, CMD_LOG)
    def logHex(self, num):
        self.CanCat_send(struct.pack(b"<I", num), CMD_LOG_HEX)
    def logHexStr(self, num, prefix):
        self.log(prefix)
        self.logHex(num)

    #### FAKE SERIAL DEVICE (interface to Python)
    def read(self, count=1):
        if len(self._inbuf) < count:
            empty = False
            try:
                #print(b'===fccc: attempting to get from _inq:')
                self._inbuf += self._inq.get(timeout = 1)
            except queue.Empty:
                empty = True
                #print(b'===fccc: attempting to get from _inq:  NOPE')
                return b''

        out = self._inbuf[:count]
        self._inbuf = self._inbuf[count:]
        if len(out):
            #print(b"===FakeCanCatCHEAT===: read(%r):  %x" % (count, ord(out)))
            return out

        return b''

    def write(self, msg):
        #self._inq.put(msg) # nah, let's try to handle it here...

        self.log(b"write(%r)" % msg)
        print(b"===FakeCanCatCHEAT===: write(%r)" % msg)

        length, cmd = struct.unpack("<HB", msg[0:3])
        data = msg[3:]

        if cmd == CMD_CHANGE_BAUD:
            self.log(b"CMD_CHANGE_BAUD")

        elif cmd == CMD_PING:
            print(b'=CMD_PING=')
            self.CanCat_send(data, CMD_PING_RESPONSE)

