
import usb
import time
import queue
import struct
import logging
import unittest
import threading
import traceback

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


class FakeCanCat:
    '''
    This class emulates a real CanCat (the physical device).
    We're going to try making this single-threaded.  We may need to handle in/out in separate threads, but fingers crossed.

    Lies!  We've added a background thread to handle pumping queued CAN Messages.
    '''
    def __init__(self):
        self._inbuf = b''
        self._outbuf = b''

        self._inq = queue.Queue()
        self._outq = queue.Queue()  # this is what's handed to the CanCat receiver thread
        self.memory = fakeMemory()
        self._fake_can_msgs = queue.Queue()

        self.start_ts = time.time()

        self._go = True
        self._runner_sleep_delay = 0
        self._thread = threading.Thread(target=self._runner, daemon=True)
        self._thread.start()

    def clock(self):
        return time.time() - self.start_ts

    def CanCat_send(self, cmd, data):
        logger.debug(b'===FakeCanCat_send: cmd:%x data: %r' % (cmd, data))
        packet = b'@%c%c%s' % (len(data)+1, cmd, data)
        self._inq.put(packet)

    def log(self, msg):
        self.CanCat_send(CMD_LOG, b"FakeCanCat: " + msg)
    def logHex(self, num):
        self.CanCat_send(CMD_LOG_HEX, struct.pack(b"<I", num))
    def logHexStr(self, num, prefix):
        self.log(prefix)
        self.logHex(num)

    def _runner(self):
        next_duration = self._runner_sleep_delay
        curlist = None
        while self._go:
            try:

                time.sleep(next_duration)
                
                if curlist:

                    # pop the next message from the list
                    msg_ts, datagram = curlist.pop(0)

                    # write message to the out queue
                    self.CanCat_send(CMD_CAN_RECV, datagram)

                    # handle timing
                    if curlist:
                        # try to feather the delay between messages
                        nextmsg_ts = curlist[0][0]
                        next_duration = min(60, max(nextmsg_ts - msg_ts - .05, 0))

                    else:
                        # if we're at the end of a list, sleep the normal amount.
                        next_duration = self._runner_sleep_delay

                else:
                    # the list is done... get a new list if we have one.
                    if self._fake_can_msgs:
                        curlist = self._fake_can_msgs.get()

                    next_duration = self._runner_sleep_delay

            except:
                logger.exception("Error in CanCat FakeDongle._runner thread.  Continuing...", exc_info=1)


    def queueCanMessages(self, msgs):
        '''
        Add a list of messages to the queue, to be delivered as if received by 
        the dongle.  Format:  [  (<timestamp-float>, b'data'), ...  ]

        example: cancat.test.test_messages.test_j1939_msgs
        '''
        self._fake_can_msgs.put(msgs)


    #### FAKE SERIAL DEVICE (interface to Python)
    def read(self, count=1):
        if len(self._inbuf) < count:
            empty = False
            try:
                #logger.info(b'===fccc: attempting to get from _inq:')
                self._inbuf += self._inq.get(timeout = 1)
            except queue.Empty:
                empty = True
                #logger.info(b'===fccc: attempting to get from _inq:  NOPE')
                return b''

        out = self._inbuf[:count]
        self._inbuf = self._inbuf[count:]
        if len(out):
            #logger.info(b"===FakeCanCatCHEAT===: read(%r):  %x" % (count, ord(out)))
            return out

        return b''

    def write(self, msg):
        #self._inq.put(msg) # nah, let's try to handle it here...

        self.log(b"write(%r)" % msg)
        logger.info(b"===FakeCanCatCHEAT===: write(%r)" % msg)

        length, cmd = struct.unpack("<HB", msg[0:3])
        data = msg[3:]

        if cmd == CMD_CHANGE_BAUD:
            logger.info(b'=CMD_CHANGE_BAUD=')
            self.log(b"CMD_CHANGE_BAUD")
            self.CanCat_send(CMD_CHANGE_BAUD_RESULT, b'\x01')

        elif cmd == CMD_PING:
            logger.info(b'=CMD_PING=')
            self.log(b'=CMD_PING=')
            self.CanCat_send(CMD_PING_RESPONSE, data)

        elif cmd == CMD_CAN_MODE:
            logger.info(b'=CMD_CAN_MODE:%r=' % data)
            self.log(b'=CMD_CAN_MODE:%r=' % data)
            self.CanCat_send(CMD_CAN_MODE_RESULT, b'\x01')

        elif cmd == CMD_CAN_BAUD:
            logger.info(b'=CMD_CAN_BAUD:%r=' % data)
            self.log(b'=CMD_CAN_BAUD:%r=' % data)
            self.CanCat_send(CMD_CAN_BAUD_RESULT, b'\x01')

        elif cmd == CMD_CAN_SEND:
            logger.info(b'=CMD_CAN_SEND:%r=' % data)
            self.log(b'=CMD_CAN_SEND:%r=' % data)
            self.CanCat_send(CMD_CAN_SEND_RESULT, b'\x01')

        elif cmd == CMD_SET_FILT_MASK:
            logger.info(b'=CMD_SET_FILT_MASK:%r=' % data)
            self.log(b'=CMD_SET_FILT_MASK:%r=' % data)
            self.CanCat_send(CMD_SET_FILT_MASK_RESULT, b'\x01')

        elif cmd == CMD_CAN_SEND_ISOTP:
            logger.info(b'=CMD_CAN_SEND_ISOTP:%r=' % data)
            self.log(b'=CMD_CAN_SEND_ISOTP:%r=' % data)
            self.CanCat_send(CMD_CAN_SEND_ISOTP_RESULT, b'\x01')

        elif cmd == CMD_CAN_RECV_ISOTP:
            logger.info(b'=CMD_CAN_RECV_ISOTP:%r=' % data)
            self.log(b'=CMD_CAN_RECV_ISOTP:%r=' % data)
            self.CanCat_send(CMD_CAN_RECV_ISOTP_RESULT, b'\x01')

        elif cmd == CMD_CAN_SENDRECV_ISOTP:
            logger.info(b'=CMD_CAN_SENDRECV_ISOTP:%r=' % data)
            self.log(b'=CMD_CAN_SENDRECV_ISOTP:%r=' % data)
            self.CanCat_send(CMD_CAN_SENDRECV_ISOTP_RESULT, b'\x01')

        elif cmd == CMD_PRINT_CAN_REGS:
            logger.info(b'=CMD_PRINT_CAN_REGS:%r=' % data)
            self.log(b'=CMD_PRINT_CAN_REGS:%r=' % data)
            #self.CanCat_send(CMD_PRINT_CAN_REGS_RESULT, b'\x01')??

        else:
            logger.warning(b'===BAD COMMAND: %x : %r' % (cmd, data))
            self.log(b'===BAD COMMAND: %x : %r' % (cmd, data))
            self.CanCat_send(b'===BAD COMMAND: %x : %r' % (cmd, data), 3)
