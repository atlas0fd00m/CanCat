from __future__ import print_function
from past.builtins import xrange
from builtins import input, bytes
import six

import os
import sys
import cmd
import time
import serial
import select
import struct
import threading
import math
import pickle
import binascii

from cancat import iso_tp

baud = 4000000


# command constants (used to identify messages between
# python client and the CanCat transceiver
CMD_LOG                     = 0x2f
CMD_LOG_HEX                 = 0x2e

CMD_CAN_RECV                = 0x30
CMD_PING_RESPONSE           = 0x31
CMD_CHANGE_BAUD_RESULT      = 0x32
CMD_CAN_BAUD_RESULT         = 0x33
CMD_CAN_SEND_RESULT         = 0x34
CMD_ISO_RECV                = 0x35
CMD_SET_FILT_MASK           = 0x36
CMD_CAN_MODE_RESULT         = 0x37
CMD_CAN_SEND_ISOTP_RESULT   = 0x38
CMD_CAN_RECV_ISOTP_RESULT   = 0x39
CMD_CAN_SENDRECV_ISOTP_RESULT = 0x3A
CMD_SET_FILT_MASK_RESULT    = 0x3B
CMD_PRINT_CAN_REGS          = 0x3C

CMD_PING                    = 0x41
CMD_CHANGE_BAUD             = 0x42
CMD_CAN_BAUD                = 0x43
CMD_CAN_SEND                = 0x44
CMD_CAN_MODE                = 0x45
CMD_CAN_MODE_SNIFF_CAN0     = 0x00 # Start sniffing on can 0
CMD_CAN_MODE_SNIFF_CAN1     = 0x01 # Start sniffing on can 1
CMD_CAN_MODE_CITM           = 0x02 # Start CITM between can1 and can2
CMD_CAN_SEND_ISOTP          = 0x46
CMD_CAN_RECV_ISOTP          = 0x47
CMD_CAN_SENDRECV_ISOTP      = 0x48


CAN_RESP_OK                 = (0)
CAN_RESP_FAILINIT           = (1)
CAN_RESP_FAILTX             = (2)
CAN_RESP_MSGAVAIL           = (3)
CAN_RESP_NOMSG              = (4)
CAN_RESP_CTRLERROR          = (5)
CAN_RESP_GETTXBFTIMEOUT     = (6)
CAN_RESP_SENDMSGTIMEOUT     = (7)
CAN_RESP_FAIL               = (0xff)

CAN_RESPS = { v: k for k,v in globals().items() if k.startswith('CAN_RESP_') }

# constants for setting baudrate for the CAN bus
CAN_AUTOBPS  = 0
CAN_5KBPS    = 1
CAN_10KBPS   = 2
CAN_20KBPS   = 3
CAN_25KBPS   = 4
CAN_31K25BPS = 5
CAN_33KBPS   = 6
CAN_40KBPS   = 7
CAN_50KBPS   = 8
CAN_80KBPS   = 9
CAN_83K3BPS  = 10
CAN_95KBPS   = 11
CAN_100KBPS  = 12
CAN_125KBPS  = 13
CAN_200KBPS  = 14
CAN_250KBPS  = 15
CAN_500KBPS  = 16
CAN_666KBPS  = 17
CAN_1000KBPS = 18

# state constants for the Receiver thread
RXTX_DISCONN    = -1
RXTX_SYNC       = 0
RXTX_GO         = 1

# constants for CANreplay mode
TIMING_FAST         = 0
TIMING_REAL         = 1
TIMING_INTERACTIVE  = 2
TIMING_SEARCH       = 3

# constants for VIEW settings:
VIEW_ASCII =        1<<0
VIEW_COMPARE =      1<<1
VIEW_BOOKMARKS =    1<<2
VIEW_TS_DELTA =     1<<3
VIEW_ENDSUM =       1<<4
VIEW_ALL = VIEW_ASCII | VIEW_COMPARE | VIEW_BOOKMARKS | VIEW_TS_DELTA | VIEW_ENDSUM

# message id's and metadata (soon to be moved into modules)
GM_messages = {
        }

Ford_messages = {
        }

Chrysler_messages = {
        }

Toyota_messages = {
        }

Honda_messages = {
        }

VW_messages = {
        }

Nissan_messages = {
        }

Mitsubishi_messages = {
        }

Hyundai_messages = {
        }

Kia_messages = {
        }

Suzuki_messages = {
        }

Harley_messages = {
        }

# helper functions for printing log messages from the CanCat Transceiver
def handleLogToScreen(message, canbuf):
    print('LOG: %s' % repr(message))

def handleLogHexToScreen(message, canbuf):
    num = struct.unpack("<L", message)
    print('LOG: %x' % num)

def handleCanMsgsDuringSniff(message, canbuf, arbids=None):
    ts = time.time()
    idx = canbuf._submitMessage(CMD_CAN_RECV, (ts, message))
    arbid, data = canbuf._splitCanMsg(message)

    if arbids:
        if arbid in arbids:
            print(reprCanMsg(idx, ts, arbid, data))
    else:
        print(reprCanMsg(idx, ts, arbid, data))

default_cmdhandlers = {
        CMD_LOG : handleLogToScreen,
        CMD_LOG_HEX: handleLogHexToScreen,
        }

def loadCanBuffer(filename):
    return pickle.load(open(filename))

def keystop(delay=0):
    if os.name == 'posix':
        return len(select.select([sys.stdin],[],[],delay)[0])
    else:
        return msvcrt.kbhit()

class SPECIAL_CASE(object):
    pass
DONT_PRINT_THIS_MESSAGE = SPECIAL_CASE

class CanInterface(object):
    _msg_source_idx = CMD_CAN_RECV
    def __init__(self, port=None, baud=baud, verbose=False, cmdhandlers=None, comment='', load_filename=None, orig_iface=None, max_msgs=None):
        '''
        CAN Analysis Workspace
        This can be subclassed by vendor to allow more vendor-specific code
        based on the way each vendor uses the varios Buses
        '''
        if orig_iface != None:
            self._consumeInterface(orig_iface)
            return


        self.init(port, baud, verbose, cmdhandlers, comment, load_filename, orig_iface, max_msgs)

    def init(self, port=None, baud=baud, verbose=False, cmdhandlers=None, comment='', load_filename=None, orig_iface=None, max_msgs=None):
        self._inbuf = b''
        self._trash = []
        self._messages = {}
        self._msg_events = {}
        self._queuelock = threading.Lock()
        self._config = {}

        self._config['shutdown'] = False
        self._config['go'] = False
        self._max_msgs = self._config['max_msgs'] = max_msgs
        self.verbose = self._config['verbose'] = verbose
        self.port = self._config['port'] = port
        self._baud = self._config['baud'] = baud
        self.name = self._config['name'] = 'CanCat'
        self._io = None
        self._in_lock = None
        self._out_lock = None
        self._commsthread = None
        self._last_can_msg = None

        self.bookmarks = []
        self.bookmark_info = {}

        self.comments = []
        if cmdhandlers == None:
            cmdhandlers = default_cmdhandlers
        self._cmdhandlers = cmdhandlers

        if load_filename != None:
            self.loadFromFile(load_filename)

        #### FIXME: make this a connection cycle, not just a "pick the first one" thing...
        #### Prove that it's a CanCat... and that it's not in use by something else...
        # If we specify a file and no port, assume we just want to read the file, only try to guess
        # ports if there is no file specified
        if self.port == None and load_filename == None:
            self.port = getDeviceFile()

        # No filename, can't guess the port, whatcha gonna do?
        if self.port == None and load_filename == None:
            raise Exception("Cannot find device, and no filename specified.  Please try again.")

        if self.port != None:
            self._reconnect()

            # just start the receive thread, it's lightweight and you never know when you may want it.
            self._startRxThread()
        self._config['go'] = True

    def _startRxThread(self):
        self._commsthread = threading.Thread(target=self._rxtx)
        self._commsthread.setDaemon(True)
        self._commsthread.start()

    def register_handler(self, cmd, handler):
        self._cmdhandlers[cmd] = handler

    def remove_handler(self, cmd):
        self._cmdhandlers[cmd] = None

    def _consumeInterface(self, other):
        other._config['go'] = False

        for k,v in vars(other).items():
            setattr(self, k, v)

        if other._commsthread != None:
            self._startRxThread()

    def _reconnect(self, port=None, baud=None):
        '''
        Attempt to connect/reconnect to the CanCat Transceiver
        '''
        if self.port == None and port == None:
            print("cannot connect to an unspecified port")
            return

        if self._io != None:
            self._io.close()

        # SHIM to allow us to easily specify a Fake CanCat for testing
        if self.port == 'FakeCanCat':
            import cancat.test as testcat
            self._io = testcat.FakeCanCat()

        else:
            self._io = serial.Serial(port=self.port, baudrate=self._baud, dsrdtr=True, timeout=None)
            self._io.setDTR(True)

        # clear all locks and free anything waiting for them
        if self._in_lock != None:
            while self._in_lock.locked_lock():
                self._in_lock.release()
                time.sleep(.01)
        self._in_lock = threading.Lock()

        if self._out_lock != None:
            while self._out_lock.locked_lock():
                self._out_lock.release()
                time.sleep(.01)
        self._out_lock = threading.Lock()

        time.sleep(1)

        return self._io

    def __del__(self):
        '''
        Destructor, called when the CanInterface object is being garbage collected
        '''
        if self._io and isinstance(self._io, serial.Serial):
            print("shutting down serial connection")
            self._io.close()
        self._config['shutdown'] = True
        if self._commsthread != None:
            self._commsthread.wait()

    def clearCanMsgs(self):
        '''
        Clear out all messages currently received on the CAN bus, allowing for
        basically a new analysis session without creating a new object/connection

        returns a list of the messages
        '''
        allmsgs = self.recvall(CMD_CAN_RECV)

        # Clear the bookmarks as well because they are no longer meaningful
        self.bookmarks = []
        self.bookmark_info = {}

        return allmsgs

    def _rxtx(self):
        '''
        Receiver thread runner.  Internal use only.
        Processes data from the CanCat transceiver, parses and places messages
        into correct mailboxes and/or hands off to pre-configured handlers.
        '''
        self._rxtx_state = RXTX_SYNC


        while not self._config['shutdown']:
            try:
                if not self._config['go']:
                    time.sleep(.4)
                    continue

                if self.verbose > 4:
                    if self.verbose > 5:
                        print("STATE: %s" % self._rxtx_state)
                    else:
                        sys.stderr.write('.')

                # try to reconnect to disconnected unit (FIXME: not working right yet)
                if self._rxtx_state == RXTX_DISCONN:
                    print("FIXME: reconnect disconnected serial port...")
                    time.sleep(1)
                    self._reconnect()
                    self._rxtx_state = RXTX_SYNC
                    continue

                # fill the queue ##########################################
                self._in_lock.acquire()
                try:
                    char = self._io.read()

                except serial.serialutil.SerialException as e:
                    self.errorcode = e
                    self.log("serial exception")
                    if "disconnected" in e.message:
                        self._io.close()
                        self._rxtx_state = RXTX_DISCONN
                    continue

                finally:
                    if self._in_lock.locked_lock():
                        self._in_lock.release()

                self._inbuf += char
                #self.log("RECV: %s" % repr(self._inbuf), 4)
                ##########################################################

                # FIXME: should we make the rest of this a separate thread, so we're not keeping messages from flowing?
                # ====== it would require more locking/synchronizing...

                # make sure we're synced
                if self._rxtx_state == RXTX_SYNC:
                    if self._inbuf.startswith(b'@') != True:
                        self._queuelock.acquire()
                        try:
                            idx = self._inbuf.find(b'@')
                            if idx == -1:
                                self.log("sitting on garbage...", 3)
                                continue

                            trash = self._inbuf[:idx]
                            self._trash.append(trash)

                            self._inbuf = self._inbuf[idx:]
                        finally:
                            self._queuelock.release()

                    self._rxtx_state = RXTX_GO

                # handle buffer if we have anything in it
                if self._rxtx_state == RXTX_GO:
                    if len(self._inbuf) < 3: continue
                    if self._inbuf.startswith(b'@') != True:
                        self._rxtx_state = RXTX_SYNC
                        continue

                    pktlen = self._inbuf[1] + 2        # <size>, doesn't include "@"

                    if len(self._inbuf) >= pktlen:
                        self._queuelock.acquire()
                        try:
                            cmd = self._inbuf[2]                # first bytes are @<size>
                            message = self._inbuf[3:pktlen]
                            self._inbuf = self._inbuf[pktlen:]
                        finally:
                            self._queuelock.release()

                        # generate the timestamp here
                        timestamp = time.time()
                        tsmsg = (timestamp, message)

                        #if we have a handler, use it
                        cmdhandler = self._cmdhandlers.get(cmd)
                        if cmdhandler != None:
                            cmdhandler(tsmsg, self)

                        # otherwise, file it
                        else:
                            self._submitMessage(cmd, tsmsg)
                        self._rxtx_state = RXTX_SYNC

            except:
                if self.verbose:
                    sys.excepthook(*sys.exc_info())

    def _submitMessage(self, cmd, tsmsg):
        '''
        submits a message to the cmd mailbox.  creates mbox if doesn't exist.
        *threadsafe*
        '''

        mbox = self._messages.get(cmd)
        if mbox == None:
            mbox = []
            self._messages[cmd] = mbox
            self._msg_events[cmd] = threading.Event()

        try:
            self._queuelock.acquire()
            mbox.append(tsmsg)
            self._msg_events[cmd].set()

        except Exception as e:
            self.log("_submitMessage: ERROR: %r" % e, -1)

        finally:
            self._queuelock.release()
        return len(mbox)-1

    def log(self, message, verbose=2):
        '''
        print a log message.  Only prints if CanCat's verbose setting >=verbose
        '''
        if self.verbose >= verbose:
            print("%.2f %s: %s" % (time.time(), self.name, message))

    def recv(self, cmd, wait=0xffffffff):
        '''
        Warning: Destructive:
            removes a message from a mailbox and returns it.
            For CMD_CAN_RECV mailbox, this will alter analysis results!
        '''
        start = time.time()
        while (time.time() - start) < wait:
            mbox = self._messages.get(cmd)

            if mbox != None and len(mbox):
                self._queuelock.acquire()
                try:
                    timestamp, message = mbox.pop(0)
                finally:
                    self._queuelock.release()

                return timestamp, message

            time.sleep(.01)
        return None, None

    def recvall(self, cmd):
        '''
        Warning: Destructive:
            removes ALL messages from a mailbox and returns them.
            For CMD_CAN_RECV mailbox, this is like getting a new
                analysis session
        '''
        mbox = self._messages.get(cmd)
        if mbox == None:
            return []

        self._queuelock.acquire()
        try:
            messages = list(mbox)
            self._messages[cmd] = []
        finally:
            self._queuelock.release()

        return messages

    def _inWaiting(self, cmd):
        '''
        Does the given cmd mailbox have any messages??
        '''
        mbox = self._messages.get(cmd)
        if mbox == None:
            return 0
        return len(mbox)

    def _send(self, cmd, message):
        '''
        Send a message to the CanCat transceiver (not the CAN bus)
        '''
        msgchar = bytes(struct.pack(">H", len(message) + 3)) # 2 byte Big Endian
        cmdByte = bytes(struct.pack('B', cmd))
        message = self._bytesHelper(message)

        msg = msgchar + cmdByte + message
        self.log("XMIT: %s" % repr(msg),  4)

        try:
            self._out_lock.acquire()
            try:
                self._io.write(msg)
            finally:
                self._out_lock.release()
            # FIXME: wait for response?
        except Exception as e:
            print("Exception: %r" % e)
            #print("Could not acquire lock. Are you trying interactive commands without an active connection?")

    def CANrecv(self, count=1):
        '''
        Warning: Destructive:
            removes a message from the received CAN messages and returns it.
            == This will alter analysis results! ==
        '''
        if count == -1:
            count = self.getCanMsgCount()

        for x in range(count):
            yield self.recv(CMD_CAN_RECV)

    def CANxmit(self, arbid, message, extflag=0, timeout=3, count=1):
        '''
        Transmit a CAN message on the attached CAN bus
        Currently returns the *last* result
        '''

        msg = struct.pack('>I', arbid) + struct.pack('B', extflag) + self._bytesHelper(message)

        for i in range(count):
            self._send(CMD_CAN_SEND, msg)
            ts, result = self.recv(CMD_CAN_SEND_RESULT, timeout)

        if result == None:
            print("CANxmit:  Return is None!?")
            return None

        resval = ord(result)
        if resval != 0:
            print("CANxmit() failed: %s" % CAN_RESPS.get(resval))

        return resval

    def ISOTPxmit(self, tx_arbid, rx_arbid, message, extflag=0, timeout=3, count=1):
        '''
        Transmit an ISOTP can message. tx_arbid is the arbid we're transmitting,
        and rx_arbid is the arbid we're listening for
        '''
        msg = struct.pack('>IIB', tx_arbid, rx_arbid, extflag) + message
        for i in range(count):
            self._send(CMD_CAN_SEND_ISOTP, msg)
            ts, result = self.recv(CMD_CAN_SEND_ISOTP_RESULT, timeout)

        if result == None:
            print("ISOTPxmit: Return is None!?")
        resval = ord(result)
        if resval != 0:
            print("ISOTPxmit() failed: %s" % CAN_RESPS.get(resval))

        return resval

    def ISOTPrecv(self, tx_arbid, rx_arbid, extflag=0, timeout=3, count=1, start_msg_idx=None):
        '''
        Receives an ISOTP can message. This function just causes
        the hardware to send the appropriate flow control command
        when an ISOTP frame is received from rx_arbid, using
        tx_arbid for the flow control frame. The ISOTP frame
        itself needs to be extracted from the received can messages
        '''
        if start_msg_idx is None:
            start_msg_idx = self.getCanMsgCount()
        # set the CANCat to respond to Flow Control messages
        resval = self._isotp_enable_flowcontrol(tx_arbid, rx_arbid, extflag)

        msg = self._getIsoTpMsg(rx_arbid, start_index=start_msg_idx, timeout=timeout)

        return msg

    def _isotp_enable_flowcontrol(self, tx_arbid, rx_arbid, extflag):
        msg = struct.pack('>IIB', tx_arbid, rx_arbid, extflag)
        self._send(CMD_CAN_RECV_ISOTP, msg)
        ts, result = self.recv(CMD_CAN_RECV_ISOTP_RESULT, timeout)

        if result == None:
            print("_isotp_enable_flowcontrol: Return is None!?")
        resval = ord(result)
        if resval != 0:
            print("_isotp_enable_flowcontrol() failed: %s" % CAN_RESPS.get(resval))

        return resval

    def ISOTPxmit_recv(self, tx_arbid, rx_arbid, message, extflag=0, timeout=3, count=1, service=None):
        '''
        Transmit an ISOTP can message, then wait for a response.
        tx_arbid is the arbid we're transmitting, and rx_arbid
        is the arbid we're listening for
        '''

        currIdx = self.getCanMsgCount()
        msg = struct.pack('>II', tx_arbid, rx_arbid) + struct.pack('B', extflag) + self._bytesHelper(message)
        for i in range(count):
            self._send(CMD_CAN_SENDRECV_ISOTP, msg)
            ts, result = self.recv(CMD_CAN_SENDRECV_ISOTP_RESULT, timeout)

        if result == None:
            print("ISOTPxmit: Return is None!?")
        resval = ord(result)
        if resval != 0:
            print("ISOTPxmit() failed: %s" % CAN_RESPS.get(resval))

        msg, idx = self._isotp_get_msg(rx_arbid, start_index = currIdx, service = service, timeout = timeout)
        return msg, idx

    def _isotp_get_msg(self, rx_arbid, start_index=0, service=None, timeout=None):
        '''
        Internal Method to piece together a valid ISO-TP message from received CAN packets.
        '''

        found = False
        complete = False
        starttime = lasttime = time.time()

        while not complete and (not timeout or (lasttime-starttime < timeout)):
            time.sleep(0.01)
            msgs = [msg for msg in self.genCanMsgs(start=start_index, arbids=[rx_arbid])]

            if len(msgs):
                try:
                    # Check that the message is for the expected service, if specified
                    arbid, msg, count = iso_tp.msg_decode(msgs)
                    if msg[0] == 0x7e:  # response for TesterPresent... ignore
                        start_index = msgs[count-1][0] + 1

                    elif service is not None:
                        # Check if this is the right service, or there was an error
                        if msg[0] == service or msg[0] == 0x7f:
                            msg_found = True
                            return msg, msgs[count-1][0]

                        print("Hey, we got here, wrong service code?")
                        start_index = msgs[count-1][0] + 1
                    else:
                        msg_found = True
                        return msg, msgs[count-1][0]

                except iso_tp.IncompleteIsoTpMsg as e:
                    #print(e) # debugging only, this is expected
                    pass

            lasttime = time.time()
            #print("_isotp_get_msg: status: %r - %r (%r) > %r" % (lasttime, starttime, (lasttime-starttime),  timeout))

        if self.verbose:
            print("_isotp_get_msg: Timeout: %r - %r (%r) > %r" % (lasttime, starttime, (lasttime-starttime),  timeout))
        return None, start_index

    def CANsniff(self, start_msg=None, arbids=None, advfilters=[], maxmsgs=None):
        '''
        Print messages in real time.

        start_msg - first message to print
                    (None: the next message captured, 0: first message since starting CanCat)
        arbids - list of arbids to print (others will be ignored)
        advfilters - list of python code to eval for each message (message context provided)
                    eg. ['pf==0xeb', 'sa==0', 'ps & 0xf']
                        will print TP data message from source address 0 if the top 4 bits of PS
                        are set.

                    Expressions are evaluated from left to right in a "and" like fashion.  If any
                    expression evaluates to "False" and the message will be ignored.

                    Variables mapped into default namespace:
                        'arbid'
                        'id'
                        'ts'
                        'data'

                    J1939 adds 'pgn', 'pf', 'ps', 'edp', 'dp', 'sa'

                    (this description is true for all advfilters, not specifically CANsniff)

        '''
        count = 0
        msg_gen = self.reprCanMsgsLines(start_msg=start_msg, arbids=arbids, advfilters=advfilters, tail=True)

        while True:
            if maxmsgs != None and maxmsgs < count:
                return
            line = next(msg_gen)
            if line:
                print(line)
                count += 1
            else:
                time.sleep(.1)

            if keystop():
                break

    def CANreplay(self, start_bkmk=None, stop_bkmk=None, start_msg=0, stop_msg=None, arbids=None, timing=TIMING_FAST):
        '''
        Replay packets between two bookmarks.
        timing = TIMING_FAST: just slam them down the CAN bus as fast as possible
        timing = TIMING_READ: send the messages using similar timing to how they
                    were received
        timing = TIMING_INTERACTIVE: wait for the user to press Enter between each
                    message being transmitted
        timing = TIMING_SEARCH: wait for the user to respond (binary search)
        '''
        if start_bkmk != None:
            start_msg = self.getMsgIndexFromBookmark(start_bkmk)

        if stop_bkmk != None:
            stop_msg = self.getMsgIndexFromBookmark(stop_bkmk)

        if timing == TIMING_SEARCH:
                diff = stop_msg - start_msg
                if diff == 1:
                    mid_msg = stop_msg
                    start_tmp = start_msg
                else:
                    mid_msg = int(start_msg + math.floor((stop_msg - start_msg) / 2))
                    start_tmp = start_msg
                    start_msg = mid_msg

        last_time = -1
        newstamp = time.time()
        for idx,ts,arbid,data in self.genCanMsgs(start_msg, stop_msg, arbids=arbids):
            laststamp = newstamp
            newstamp = time.time()
            delta_correction = newstamp - laststamp

            if timing == TIMING_INTERACTIVE:
                char = input("Transmit this message? %s (Y/n)" % reprCanMsg(idx, ts, arbid, data))

                if char is not None and len(char) > 0 and char[0] == 'n':
                    return

            elif timing == TIMING_SEARCH:
                self.CANreplay(start_msg=mid_msg, stop_msg=stop_msg)
                char = input("Expected outcome?  start_msg = %s, stop_msg = %s (Y/n/q)" % (mid_msg, stop_msg))
                if char is not None and len(char) > 0 and char[0] == 'q':
                    return
                if diff > 1:
                    if char is not None and len(char) > 0 and char[0] == 'y':
                        return self.CANreplay(start_msg=mid_msg, stop_msg=stop_msg, timing=TIMING_SEARCH)
                    elif char is not None and len(char) > 0 and char[0] == 'n':
                        return self.CANreplay(start_msg=start_tmp, stop_msg=mid_msg, timing=TIMING_SEARCH)
                else:
                    if char is not None and len(char) > 0 and char[0] == 'y':
                        print("Target message: %s" % (stop_msg))
                        return
                    elif char is not None and len(char) > 0 and char[0] == 'n':
                        print("Target message: %s" % (start_tmp))
                        return

            elif timing == TIMING_REAL:
                if last_time != -1:
                    delta = ts - last_time - delta_correction
                    if delta >= 0:
                        time.sleep(delta)
                last_time = ts

            self.CANxmit(arbid, data)
            if timing == TIMING_INTERACTIVE:
                print("Message transmitted")

    def setCanBaud(self, baud_const=CAN_500KBPS):
        '''
        set the baud rate for the CAN bus.  this has nothing to do with the
        connection from the computer to the tool
        '''

        baud = struct.pack("B", baud_const)

        self._send(CMD_CAN_BAUD, baud)
        response = self.recv(CMD_CAN_BAUD_RESULT, wait=30)
        self._config['can_baud'] = baud_const

        while(response[1] != b'\x01'):
            print("CAN INIT FAILED WHILE SETTING BAUD RATE: Retrying")
            response = self.recv(CMD_CAN_BAUD_RESULT, wait=30)

    def setCanMode(self, mode):
        '''
        Sets the desired operation mode. Note that just setting the operational mode
        does not change anything on the hardware, after changing the mode you must change
        the baud rate in order to properly configure the hardware
        '''
        CAN_MODES = { v: k for k,v in globals().items() if k.startswith('CMD_CAN_MODE_') and k != 'CMD_CAN_MODE_RESULT' }
        if mode not in CAN_MODES:
            print("{} is not a valid can mode. Valid modes are:".format(mode))
            for k in CAN_MODES:
                print("{} ({})".format(CAN_MODES[k], k))
        else:
            self._send(CMD_CAN_MODE, chr(mode))
            response = self.recv(CMD_CAN_MODE_RESULT, wait=30)

            while(response[1] != b'\x01'):
                print("CAN INIT FAILED WHILE SETTING MODE: Retrying")
                response = self.recv(CMD_CAN_MODE_RESULT, wait=30)

        self._config['can_mode'] = mode
        return response

    def ping(self, buf='ABCDEFGHIJKL'):
        '''
        Utility function, only to send and receive data from the
        CanCat Transceiver.  Has no effect on the CAN bus
        '''
        buf = self._bytesHelper(buf)

        self._send(CMD_PING, buf)
        response = self.recv(CMD_PING_RESPONSE, wait=3)
        return response

    def genCanMsgs(self, start=0, stop=None, arbids=None, tail=False, maxsecs=None):
        '''
        CAN message generator.  takes in start/stop indexes as well as a list
        of desired arbids (list)

        maxsecs limits the number of seconds this generator will go for.  it's intended
        for use with tail

        if tail==True, if we run out of messages in the queue, this will yield a None
        to allow the caller to decide what to do instead of waiting forever or until a
        new message is received.
        '''

        messages = self.getCanMsgQueue()

        # get the ts of the first received message
        if messages != None and len(messages):
            startts = messages[0][0]
        else:
            startts = time.time()

        if start == None:
            start = self.getCanMsgCount()

        if messages == None:
            stop = 0
        elif stop == None or tail:
            stop = len(messages)
        else:
            stop = stop + 1 # This makes the stop index inclusive if specified

        starttime = time.time()

        idx = start
        while tail or idx < stop:
            # obey our time restrictions
            # placed here to ensure checking whether we're receiving messages or not
            if maxsecs != None and time.time() > maxsecs+starttime:
                return

            # If we start sniffing before we receive any messages,
            # messages will be "None". In this case, each time through
            # this loop, check to see if we have messages, and if so,
            # re-create the messages handle
            if messages == None:
                messages = self._messages.get(self._msg_source_idx, None)

            # if we're off the end of the original request, and "tailing"
            if messages != None:
                if tail and idx >= stop:
                    msglen = len(messages)
                    self.log("stop=%d  len=%d" % (stop, msglen), 3)

                    if stop == msglen:
                        self.log("waiting for messages", 3)
                        # if we're "tailing" yield Nones so the caller can decide what to do
                        if tail:
                            yield None

                        # wait for trigger event so we're not constantly polling
                        self._msg_events[self._msg_source_idx].wait(1)
                        self._msg_events[self._msg_source_idx].clear()
                        self.log("received 'new messages' event trigger", 3)

                    # we've gained some messages since last check...
                    stop = len(messages)
                    continue    # to the big message loop.

                # now actually handle messages
                ts, msg = messages[idx]

                # make ts an offset instead of the real time.
                ts -= startts

                arbid, data = self._splitCanMsg(msg)

                if arbids != None and arbid not in arbids:
                    # allow filtering of arbids
                    idx += 1
                    continue

                yield((idx, ts, arbid, data))
                idx += 1

    def _splitCanMsg(self, msg):
        '''
        takes in captured message
        returns arbid and data

        does not check msg size.  MUST be at least 4 bytes in length as the
        tool should send 4 bytes for the arbid
        '''

        arbid = struct.unpack(">I", msg[:4])[0]
        data = msg[4:]
        return arbid, data

    def getCanMsgQueue(self):
        '''
        returns the list of interface/CAN messages for this object
        for CanInterface, this is self._messages[CMD_CAN_RECV]
        '''
        return self._messages.get(self._msg_source_idx)

    def getCanMsgCount(self):
        '''
        the number of CAN messages we've received this session
        '''
        canmsgs = self._messages.get(self._msg_source_idx, [])
        return len(canmsgs)

    def printSessionStatsByBookmark(self, start=None, stop=None):
        '''
        Prints session stats only for messages between two bookmarks
        '''
        print(self.getSessionStatsByBookmark(start, stop))

    def printSessionStats(self, start=0, stop=None):
        '''
        Print session stats by Arbitration ID (aka WID/PID/CANID/etc...)
        between two message indexes (where they sit in the CMD_CAN_RECV
        mailbox)
        '''
        print(self.getSessionStats(start, stop))

    def getSessionStatsByBookmark(self, start=None, stop=None):
        '''
        returns session stats by bookmarks
        '''
        if start != None:
            start_msg = self.getMsgIndexFromBookmark(start)
        else:
            start_msg = 0

        if stop != None:
            stop_msg = self.getMsgIndexFromBookmark(stop)
        else:
            stop_msg = self.getCanMsgCount()

        return(self.getSessionStats(start=start_msg, stop=stop_msg))

    def getArbitrationIds(self, start=0, stop=None, reverse=False):
        '''
        return a list of Arbitration IDs
        '''
        arbids = {}
        msg_count = 0
        for idx,ts,arbid,data in self.genCanMsgs(start, stop):
            arbmsgs = arbids.get(arbid)
            if arbmsgs == None:
                arbmsgs = []
                arbids[arbid] = arbmsgs
            arbmsgs.append((ts, data))
            msg_count += 1

        arbid_list = [(len(msgs), arbid, msgs) for arbid,msgs in arbids.items()]
        arbid_list.sort(reverse=reverse)

        return arbid_list

    def getSessionStats(self, start=0, stop=None):
        out = []

        arbid_list = self.getArbitrationIds(start=start, stop=stop, reverse=True)

        for datalen, arbid, msgs in arbid_list:
            last = 0
            high = 0
            low = 0xffffffff
            for ts, data in msgs:
                if last == 0:
                    last = ts
                    continue

                # calculate the high and low
                delta = ts - last
                if delta > high:
                    high = delta
                if delta < low:
                    low = delta

                # track repeated values (rounded to nearest .001 sec)
                last = ts

            if datalen > 1:
                mean = (msgs[-1][0] - msgs[0][0]) / (datalen-1)
                median = low + (high-low) / 2
            else:
                low = 0
                mean = 0
                median = mean
            out.append("id: 0x%x\tcount: %d\ttiming::  mean: %.3f\tmedian: %.3f\thigh: %.3f\tlow: %.3f" % \
                    (arbid, datalen, mean, median, high, low))

        msg_count = self.getCanMsgCount()
        out.append("Total Uniq IDs: %d\nTotal Messages: %d" % (len(arbid_list), msg_count))
        return '\n'.join(out)

    # TODO files still lacking compatibility between Python 2 and 3
    def loadFromFile(self, filename, force=False):
        '''
        Load a previous analysis session from a saved file
        see: saveSessionToFile()
        '''
        loadedFile = open(filename, 'rb')
        me = pickle.load(loadedFile, encoding='latin1')

        # Go through the msgs and turn them into bytes
        for cmd in me['messages']:
            for i in range(len(me['messages'][cmd])):
                ts, msg = me['messages'][cmd][i]
                if isinstance(msg, str):
                    me['messages'][cmd][i] = (ts, msg.encode('latin-1'))

        self.restoreSession(me, force=force)
        self._filename = filename

    def restoreSession(self, me, force=False):
        '''
        Load a previous analysis session from a python dictionary object
        see: saveSession()
        '''
        if isinstance(self._io, serial.Serial) and force==False:
            print("Refusing to reload a session while active session!  use 'force=True' option")
            return

        self._messages = me.get('messages')
        self.bookmarks = me.get('bookmarks')
        self.bookmark_info = me.get('bookmark_info')
        self.comments = me.get('comments')

        # handle previous versions
        ver = me.get('file_version')
        if ver is not None:
            self._config = me.get('config')

        for cmd in self._messages:
            self._msg_events[cmd] = threading.Event()

    def saveSessionToFile(self, filename=None):
        '''
        Saves the current analysis session to the filename given
        If saved previously, the name will already be cached, so it is
        unnecessary to provide it again.
        '''
        if filename != None:
            self._filename = filename
        elif self._filename == None:
            raise Exception('Cannot save to file when no filename given (and first time save)')
        else:
            filename = self._filename

        savegame = self.saveSession()
        me = pickle.dumps(savegame)

        outfile = open(filename, 'wb')
        outfile.write(me)
        outfile.close()

    def saveSession(self):
        '''
        Save the current analysis session to a python dictionary object
        What you do with it form there is your own business.
        This function is called by saveSessionToFile() to get the data
        to save to the file.
        '''
        savegame = { 'messages' : self._messages,
                'bookmarks' : self.bookmarks,
                'bookmark_info' : self.bookmark_info,
                'comments' : self.comments,
                'file_version' : 1.0,
                'class' : self.__class__,
                'config' : self._config,
                }
        return savegame

    # bookmark subsystem
    def placeCanBookmark(self, name=None, comment=None):
        '''
        Save a named bookmark (with optional comment).
        This stores the message index number from the
        CMD_CAN_RECV mailbox.

        DON'T USE CANrecv or recv(CMD_CAN_RECV) with Bookmarks or Snapshots!!
        '''
        mbox = self._messages.get(self._msg_source_idx)
        if mbox == None:
            msg_index = 0
        else:
            msg_index = len(mbox)

        bkmk_index = len(self.bookmarks)
        self.bookmarks.append(msg_index)

        info = { 'name' : name,
                'comment' : comment }

        self.bookmark_info[bkmk_index] = info #should this be msg_index? benefit either way?
        return bkmk_index

    def getMsgIndexFromBookmark(self, bkmk_index):
        return self.bookmarks[bkmk_index]

    def getBookmarkFromMsgIndex(self, msg_index):
        bkmk_index = self.bookmarks.index(msg_index)
        return bkmk_index

    def setCanBookmarkName(self, bkmk_index, name):
        info = self.bookmark_info[bkmk_index]
        info[name] = name

    def setCanBookmarkComment(self, bkmk_index, comment):
        info = self.bookmark_info[bkmk_index]
        info[name] = name

    def setCanBookmarkNameByMsgIndex(self, msg_index, name):
        bkmk_index = self.bookmarks.index(msg_index)
        info = self.bookmark_info[bkmk_index]
        info[name] = name

    def setCanBookmarkCommentByMsgIndex(self, msg_index, comment):
        bkmk_index = self.bookmarks.index(msg_index)
        info = self.bookmark_info[bkmk_index]
        info[name] = name

    def snapshotCanMessages(self, name=None, comment=None):
        '''
        Save bookmarks at the start and end of some event you are about to do
        Bookmarks are named "Start_" + name and "Stop_" + name

        DON'T USE CANrecv or recv(CMD_CAN_RECV) with Bookmarks or Snapshots!!
        '''
        start_bkmk = self.placeCanBookmark("Start_" + name, comment)
        input("Press Enter When Done...")
        stop_bkmk = self.placeCanBookmark("Stop_" + name, comment)

    def filterCanMsgsByBookmark(self, start_bkmk=None, stop_bkmk=None, start_baseline_bkmk=None, stop_baseline_bkmk=None,
                    arbids=None, ignore=[], advfilters=[]):
        if start_bkmk != None:
            start_msg = self.getMsgIndexFromBookmark(start_bkmk)
        else:
            start_msg = 0

        if stop_bkmk != None:
            stop_msg = self.getMsgIndexFromBookmark(stop_bkmk)
        else:
            stop_bkmk = -1

        if start_baseline_bkmk != None:
            start_baseline_msg = self.getMsgIndexFromBookmark(start_baseline_bkmk)
        else:
            start_baseline_msg = None

        if stop_baseline_bkmk != None:
            stop_baseline_msg = self.getMsgIndexFromBookmark(stop_baseline_bkmk)
        else:
            stop_baseline_msg = None

        return self.filterCanMsgs(start_msg, stop_msg, start_baseline_msg, stop_baseline_msg, arbids, ignore, advfilters)

    def _getLocals(self, idx, ts, arbid, data):
        return {'idx':idx, 'ts':ts, 'arbid':arbid, 'data':data}

    def filterCanMsgs(self, start_msg=0, stop_msg=None, start_baseline_msg=None, stop_baseline_msg=None, arbids=None, ignore=[], advfilters=[], tail=False, maxsecs=None):
        '''
        returns the received CAN messages between indexes "start_msg" and "stop_msg"
        but only messages to ID's that *do not* appear in the the baseline indicated
        by "start_baseline_msg" and "stop_baseline_msg".

        for message indexes, you *will* want to look into the bookmarking subsystem!
        '''
        self.log("starting filtering messages...")
        if stop_baseline_msg != None:
            self.log("ignoring arbids from baseline...")
            # get a list of baseline arbids
            filter_ids = { arbid:1 for idx,ts,arbid,data in self.genCanMsgs(start_baseline_msg, stop_baseline_msg)
                }.keys()
        else:
            filter_ids = None
        self.log("filtering messages...")

        if arbids != None and type(arbids) != list:
            arbids = [arbids]

        for genmsg in self.genCanMsgs(start_msg, stop_msg, arbids=arbids, tail=tail, maxsecs=maxsecs):
            # if we use "tail" we may yield Nones if we're waiting.
            if genmsg is None:
                yield None
                continue

            idx,ts,arbid,msg = genmsg
            if not ((arbids != None and arbid in arbids) or arbid not in ignore and (filter_ids==None or arbid not in filter_ids)):
                self.log("skipping message: (%r, %r, %r, %r)" % ((idx, ts, arbid, msg)))
                continue

            # advanced filters allow python code to be handed in.  if any of the python code snippits result in "False" or 0, skip this message
            skip = False
            if advfilters:
                # do this once per message, but only if there are advanced filters
                lcls = self._getLocals(idx, ts, arbid, msg)

            for advf in advfilters:
                # eval each advfilter string/python and determine if this 
                # message should be included.
                if not eval(advf, lcls):
                    skip = True

            if skip:
                self.log("skipping message(adv): (%r, %r, %r, %r)" % ((idx, ts, arbid, msg)))
                continue

            yield (idx, ts, arbid, msg)

    def printCanMsgsByBookmark(self, start_bkmk=None, stop_bkmk=None, start_baseline_bkmk=None, stop_baseline_bkmk=None,
                    arbids=None, ignore=[], advfilters=[]):
        '''
        deprecated: use printCanMsgs(start_bkmk=foo, stop_bkmk=bar)
        '''
        print(self.reprCanMsgsByBookmark(start_bkmk, stop_bkmk, start_baseline_bkmk, stop_baseline_bkmk, arbids, ignore, advfilters))

    def reprCanMsgsByBookmark(self, start_bkmk=None, stop_bkmk=None, start_baseline_bkmk=None, stop_baseline_bkmk=None, arbids=None, ignore=[], advfilters=[]):
        '''
        deprecated: use reprCanMsgs(start_bkmk=foo, stop_bkmk=bar)
        '''
        out = []

        if start_bkmk != None:
            start_msg = self.getMsgIndexFromBookmark(start_bkmk)
        else:
            start_msg = 0

        if stop_bkmk != None:
            stop_msg = self.getMsgIndexFromBookmark(stop_bkmk)
        else:
            stop_bkmk = -1

        if start_baseline_bkmk != None:
            start_baseline_msg = self.getMsgIndexFromBookmark(start_baseline_bkmk)
        else:
            start_baseline_msg = None

        if stop_baseline_bkmk != None:
            stop_baseline_msg = self.getMsgIndexFromBookmark(stop_baseline_bkmk)
        else:
            stop_baseline_msg = None

        return self.reprCanMsgs(start_msg, stop_msg, start_baseline_msg, stop_baseline_msg, arbids, ignore, advfilters)

    def printCanMsgs(self, start_msg=0, stop_msg=None, start_bkmk=None, stop_bkmk=None, start_baseline_msg=None, stop_baseline_msg=None, arbids=None, ignore=[], advfilters=[], pretty=False, paginate=None, viewbits=VIEW_ALL):

        data = self.reprCanMsgsLines(start_msg, stop_msg, start_bkmk, stop_bkmk, start_baseline_msg, stop_baseline_msg, arbids, ignore, advfilters, pretty, viewbits=viewbits)

        pidx = 0
        try:
            while True:
                line = next(data)
                lines = line.split('\n')
                for thing in lines:
                    print(thing)
                    pidx += 1

                    if paginate != None and pidx % paginate == 0:
                        inp = input("PRESS ENTER TO CONTINUE")

        except StopIteration:
            pass

    def reprCanMsgsLines(self, start_msg=0, stop_msg=None, start_bkmk=None, stop_bkmk=None, start_baseline_msg=None, stop_baseline_msg=None, arbids=None, ignore=[], advfilters=[], pretty=False, tail=False, viewbits=VIEW_ALL):
        # TODO: make different stats selectable using a bitfield arg (eg. REPR_TIME_DELTA | REPR_ASCII)
        '''
        String representation of a set of CAN Messages.
        These can be filtered by start and stop message indexes, as well as
        use a baseline (defined by start/stop message indexes),
        by a list of "desired" arbids as well as a list of
        ignored arbids

        Many functions wrap this one.

        viewbits is a bitfield made up of VIEW_* options OR'd together:
            ... viewbits=VIEW_ASCII|VIEW_COMPARE)
        '''

        if start_bkmk != None:
            start_msg = self.getMsgIndexFromBookmark(start_bkmk)

        if stop_bkmk != None:
            stop_msg = self.getMsgIndexFromBookmark(stop_bkmk)


        if (viewbits & VIEW_BOOKMARKS) and start_msg in self.bookmarks:
            bkmk = self.bookmarks.index(start_msg)
            yield ("starting from bookmark %d: '%s'" %
                    (bkmk,
                    self.bookmark_info[bkmk].get('name'))
                    )

        if (viewbits & VIEW_BOOKMARKS) and stop_msg in self.bookmarks:
            bkmk = self.bookmarks.index(stop_msg)
            yield ("stoppng at bookmark %d: '%s'" %
                    (bkmk,
                    self.bookmark_info[bkmk].get('name'))
                    )

        last_msg = None
        next_bkmk = 0
        next_bkmk_idx = 0

        msg_count = 0
        last_ts = None
        tot_delta_ts = 0
        counted_msgs = 0    # used for calculating averages, excluding outliers

        data_delta = None


        data_repeat = 0
        data_similar = 0

        for filtmsg in self.filterCanMsgs(start_msg, stop_msg, start_baseline_msg, stop_baseline_msg, arbids=arbids, ignore=ignore, advfilters=advfilters, tail=tail):
            # if we use "tail" we may yield Nones if we're waiting.
            if filtmsg is None:
                yield None
                continue

            idx, ts, arbid, msg = filtmsg
            # insert bookmark names/comments in appropriate places
            while next_bkmk_idx < len(self.bookmarks) and idx >= self.bookmarks[next_bkmk_idx]:
                yield (self.reprBookmark(next_bkmk_idx))
                next_bkmk_idx += 1

            msg_count += 1
            diff = []

            # check data
            byte_cnt_diff = 0
            if (viewbits & VIEW_COMPARE) and last_msg != None:
                if len(last_msg) == len(msg):
                    for bidx in range(len(msg)):
                        if last_msg[bidx] != msg[bidx]:
                            byte_cnt_diff += 1

                    if byte_cnt_diff == 0:
                        diff.append("REPEAT")
                        data_repeat += 1
                    elif byte_cnt_diff <=4:
                        diff.append("Similar")
                        data_similar += 1
                    # TODO: make some better heuristic to identify "out of norm"

            # look for ASCII data (4+ consecutive bytes)
            if (viewbits & VIEW_ASCII) and hasAscii(msg):
                diff.append("ASCII: %s" % repr(msg))

            # calculate timestamp delta and comment if out of whack
            if last_ts == None:
                last_ts = ts

            delta_ts = ts - last_ts
            if counted_msgs:
                avg_delta_ts = tot_delta_ts / counted_msgs
            else:
                avg_delta_ts = delta_ts


            if abs(delta_ts - avg_delta_ts) <= delta_ts:
                tot_delta_ts += delta_ts
                counted_msgs += 1
            elif (viewbits & VIEW_TS_DELTA):
                diff.append("TS_delta: %.3f" % delta_ts)

            if pretty:
                if delta_ts >= .95:
                    yield ('')

            msgrepr = self._reprCanMsg(idx, ts, arbid, msg, comment='\t'.join(diff))
            # allow _reprCanMsg to return None to skip printing the message
            if msgrepr != DONT_PRINT_THIS_MESSAGE:
                yield msgrepr

            last_ts = ts
            last_msg = msg

        if viewbits & VIEW_ENDSUM:
            yield ("Total Messages: %d  (repeat: %d / similar: %d)" % (msg_count, data_repeat, data_similar))

    def reprCanMsgs(self, start_msg=0, stop_msg=None, start_bkmk=None, stop_bkmk=None, start_baseline_msg=None, stop_baseline_msg=None, arbids=None, ignore=[], advfilters=[], pretty=False, tail=False, viewbits=VIEW_ALL):
        out = [x for x in self.reprCanMsgsLines(start_msg, stop_msg, start_bkmk, stop_bkmk, start_baseline_msg, stop_baseline_msg, arbids, ignore, advfilters, pretty, tail, viewbits)]
        return "\n".join(out)

    def _reprCanMsg(self, idx, ts, arbid, msg, comment=None):
        return reprCanMsg(idx, ts, arbid, msg, comment=comment)

    def printCanSessions(self, arbid_list=None, advfilters=[]):
        '''
        Split CAN messages into Arbitration ID's and prints entire
        sessions for each CAN id.
        Defaults to printing by least number of messages, including all IDs
        Or... provide your own list of ArbIDs in whatever order you like
        '''
        if arbid_list == None:
            arbids = self.getArbitrationIds()
        else:
            arbids = [arbdata for arbdata in self.getArbitrationIds() if arbdata[1] in arbid_list]

        for datalen,arbid,msgs in arbids:
            print(self.reprCanMsgs(arbids=[arbid], advfilters=advfilters))
            cmd = input("\n[N]ext, R)eplay, F)astReplay, I)nteractiveReplay, S)earchReplay, Q)uit: ").upper()
            while len(cmd) and cmd != 'N':
                if cmd == 'R':
                    self.CANreplay(arbids=[arbid], timing=TIMING_REAL)

                elif cmd == 'F':
                    self.CANreplay(arbids=[arbid], timing=TIMING_FAST)

                elif cmd == 'I':
                    self.CANreplay(arbids=[arbid], timing=TIMING_INTERACTIVE)

                elif cmd == 'S':
                    self.CANreplay(arbids=[arbid], timing=TIMING_SEARCH)

                elif cmd == 'Q':
                    return

                cmd = input("\n[N]ext, R)eplay, F)astReplay, I)nteractiveReplay, S)earchReplay, Q)uit: ").upper()
            print

    def printBookmarks(self):
        '''
        Print out the list of current Bookmarks and where they sit
        '''
        print(self.reprBookmarks())

    def printAsciiStrings(self, minbytes=4, strict=True):
        '''
        Search through messages looking for ASCII strings
        '''
        for idx, ts, arbid, msg in self.genCanMsgs():
            if hasAscii(msg, minbytes=minbytes, strict=strict):
                print(reprCanMsg(idx, ts, arbid, msg, repr(msg)))

    def reprBookmarks(self):
        '''
        get a string representation of the bookmarks
        '''
        out = []
        for bid in range(len(self.bookmarks)):
            out.append(self.reprBookmark(bid))
        return '\n'.join(out)

    def reprBookmark(self, bid):
        '''
        get a string representation of one bookmark
        '''
        msgidx = self.bookmarks[bid]
        info = self.bookmark_info.get(bid)
        comment = info.get('comment')
        if comment == None:
            return "bkmkidx: %d\tmsgidx: %d\tbkmk: %s" % (bid, msgidx, info.get('name'))

        return "bkmkidx: %d\tmsgidx: %d\tbkmk: %s \tcomment: %s" % (bid, msgidx, info.get('name'), info.get('comment'))

    def setMaskAndFilter(self,
                         mask0=0,
                         mask1=0,
                         filter0=0,
                         filter1=0,
                         filter2=0,
                         filter3=0,
                         filter4=0,
                         filter5=0):
        '''
        Set the filters and masks. The mask determines which bits matter for the filter following the
        below truth table:

        _____________________________________________________________________________
        | Mask Bit n    | Filter Bit n  | Arbitration ID bit n  | Accept or Reject  |
        | 0             | X             | X                     | Accept            |
        | 1             | 0             | 0                     | Accept            |
        | 1             | 0             | 1                     | Reject            |
        | 1             | 1             | 0                     | Reject            |
        | 1             | 1             | 1                     | Accept            |
        -----------------------------------------------------------------------------

        There are two RX buffers. mask0 and filters 0 and 1 apply to buffer 0. mask1 and the other four filters
        apply to buffer 1.
        '''
        msg = struct.pack('>IIIIIIII', mask0, mask1, filter0, filter1, filter2, filter3, filter4, filter5)
        return self._send(CMD_SET_FILT_MASK, msg)

    def clearMaskAndFilter(self):
        '''
        Clears all masks and filters
        '''
        msg = struct.pack('>IIIIIIII', 0, 0, 0, 0, 0, 0, 0, 0)
        return self._send(CMD_SET_FILT_MASK, msg)

    def _test_throughput(self):
        '''
        Use in conjuction with the M2_TEST_FW to test throughput

        Connect one CanCat up to another M2 or Arduino DUE device runing the M2_TEST_FW firmware
        and run this function to perform a throughput test. No other device should be connected
        to allow the test to run unimpeded by other CAN traffic.
        '''
        self.clearCanMsgs()
        self.CANxmit(0x0010, "TEST")
        for i in range(6, 3, -1):
            print("Time remaining: ", i*10, " seconds")
            time.sleep(10)
        self.CANxmit(0x810, "TEST", extflag=True)
        for i in range(3, 0, -1):
            print("Time remaining: ", i*10, " seconds")
            time.sleep(10)

        out_of_order_count = 0
        msg_count = 0
        prev_val = 0xFF
        for foo in self.genCanMsgs(arbids=[0x00]):
            msg_count += 1
            prev_val += 1
            if prev_val > 0xff:
                prev_val = 0
            if prev_val != foo[3]:
                out_of_order_count += 1
                prev_val = foo[3]
        if (out_of_order_count > 0):
            print("ERROR: 11 bit IDs, 1 byte messages, ", out_of_order_count, " Messages received out of order")
        elif (msg_count != 181810):
            print("ERROR: Received ", msg_count, " out of expected 181810 message")
        else:
            print("PASS: 11 bit IDs, 1 byte messages")

        out_of_order_count = 0
        msg_count = 0
        prev_val = 0xFF
        for foo in self.genCanMsgs(arbids=[0x01]):
            msg_count += 1
            prev_val += 1
            if prev_val > 0xff:
                prev_val = 0
            if prev_val != foo[3][0]:
                out_of_order_count += 1
                prev_val = foo[3][0]
        if (out_of_order_count > 0):
            print("ERROR: 11 bit IDs, 8 byte messages, ", out_of_order_count, " Messages received out of order")
        elif (msg_count != 90090):
            print("ERROR: Received ", msg_count, " out of expected 90090 message")
        else:
            print("PASS: 11 bit IDs, 8 byte messages")

        out_of_order_count = 0
        msg_count = 0
        prev_val = 0xFF
        for foo in self.genCanMsgs(arbids=[0x800]):
            msg_count += 1
            prev_val += 1
            if prev_val > 0xff:
                prev_val = 0
            if prev_val != foo[3]:
                out_of_order_count += 1
                prev_val = foo[3]
        if (out_of_order_count > 0):
            print("ERROR: 29 bit IDs, 1 byte messages, ", out_of_order_count, " Messages received out of order")
        elif (msg_count != 133330):
            print("ERROR: Received ", msg_count, " out of expected 133330 message")
        else:
            print("PASS: 29 bit IDs, 1 byte messages")

        out_of_order_count = 0
        msg_count = 0
        prev_val = 0xFF
        for foo in self.genCanMsgs(arbids=[0x801]):
            msg_count += 1
            prev_val += 1
            if prev_val > 0xff:
                prev_val = 0
            if prev_val != foo[3][0]:
                out_of_order_count += 1
                prev_val = foo[3][0]
        if (out_of_order_count > 0):
            print("ERROR: 29 bit IDs, 8 byte messages, ", out_of_order_count, " Messages received out of order")
        elif (msg_count != 76330):
            print("ERROR: Received ", msg_count, " out of expected 76330 message")
        else:
            print("PASS: 29 bit IDs, 8 byte messages")

    def _printCanRegs(self):
        self._send(CMD_PRINT_CAN_REGS, "")

    def _bytesHelper(self, msg):
        if isinstance(msg, six.string_types):
            if sys.version_info < (3, 0):
                msg = bytes(msg)
            else:
                msg = bytes(msg, 'raw_unicode_escape')

        return msg

def getAscii(msg, minbytes=3):
    '''
    if strict, every character has to be clean ASCII
    otherwise, look for strings of at least minbytes in length
    '''
    strings = []

    ascii_match = 0
    ascii_count = 0
    startidx = None

    for bidx in range(len(msg)):
        byte = msg[bidx]
        if 0x20 <= byte < 0x7f:
            if startidx == None:
                startidx = bidx

            ascii_count +=1

        else:
            # non printable char
            # if we reached the magic threshold, package it
            if ascii_count >= minbytes:
                strings.append(msg[startidx:bidx])

            # reset counters
            ascii_count = 0
            startidx = None

    # in case we have a string all the way to the end
    if ascii_count >= minbytes:
        strings.append(msg[startidx:])

    return strings

def hasAscii(msg, minbytes=3, strict=False):
    '''
    if minbytes == -1, every character has to be clean ASCII
    otherwise, look for strings of at least minbytes in length
    '''
    ascii_match = 0
    ascii_count = 0
    for byte in msg:
        if 0x20 <= byte < 0x7f:
            ascii_count +=1
            if ascii_count >= minbytes:
                ascii_match = 1
        else:
            if strict:
                return 0

            ascii_count = 0
    return ascii_match

def reprCanMsg(idx, ts, arbid, data, comment=None):
    #TODO: make some repr magic that spits out known ARBID's and other subdata
    if comment == None:
        comment = ''
    return "%.8d %8.3f ID: %.3x,  Len: %.2x, Data: %-18s\t%s" % (idx, ts, arbid, len(data), binascii.hexlify(data), comment)

class FordInterface(CanInterface):
    def setCanBaudHSCAN(self):
        self.setCanBaud(CAN_500KBPS)

    def setCanBaudMSCAN(self):
        self.setCanBaud(CAN_125KBPS)

    def setCanBaudICAN(self):
        self.setCanBaud(CAN_500KBPS)

class GMInterface(CanInterface):
    '''
    DLC port:
        SW-LS-CAN   - pin 1                 33kbps
        MS-CAN      - pins 3+ and 11-       95kbps
        DW-FT-CAN   - pins 1+ and 9-        <125kbps
        HS-CAN      - pins 6+ and 14-       500kbps
    '''
    def setCanBaudHSCAN(self):
        self.setCanBaud(CAN_500KBPS)

    def setCanBaudMSCAN(self):
        self.setCanBaud(CAN_95KBPS)

    def setCanBaudLSCAN(self):
        self.setCanBaud(CAN_33KBPS)

class CanInTheMiddleInterface(CanInterface):
    def __init__(self, port=None, baud=baud, verbose=False, cmdhandlers=None, comment='', load_filename=None, orig_iface=None):
        '''
        CAN in the middle. Allows the user to determine what CAN messages are being
        sent by a device by isolating a device from the CAN network and using two
        Can shields on one Arduino to relay the CAN messages to each other.

        Device<----->Isolation CanCat<----->Arduino<----->Vehicle CanCat<----->Vehicle
                CAN                    SPI     |     SPI                  CAN
                                               |
                                               | < Serial
                                               PC

        This solves the problem of not being able to determine which device is sending
        which CAN message, since CAN messages have no source information and all messages
        are broadcast.

        The Can shield connected to the device is referred to as the isolation CanCat.
        This CanCat should be modified so that the CS SPI pin is connected to D10, rather
        than the default of D9. This is accomplished by cutting a trace on the circuit
        board and bridging the CS pad to the D10 pad. Seeedstudio has instructions
        on their Wiki, but there shield differed slightly from my board. The CanCat
        connected to the vehicle is referred to as the vehicle CanCat and should be unmodified.
        '''
        self.bookmarks_iso = []
        self.bookmark_info_iso = {}
        CanInterface.__init__(self, port=port, baud=baud, verbose=verbose, cmdhandlers=cmdhandlers, comment=comment, load_filename=load_filename, orig_iface=orig_iface)
        if load_filename is None:
            self.setCanMode(CMD_CAN_MODE_CITM)


    def genCanMsgsIso(self, start=0, stop=None, arbids=None):
        # TODO: move to "indexed" CAN interfaces, to allow for up to 10 or more without new code.
        '''
        CAN message generator.  takes in start/stop indexes as well as a list
        of desired arbids (list). Uses the isolation messages.
        '''
        messages = self._messages.get(CMD_ISO_RECV, [])
        if stop == None:
            stop = len(messages)
        else:
            stop = stop + 1

        for idx in xrange(start, stop):
            ts, msg = messages[idx]

            arbid, data = self._splitCanMsg(msg)

            if arbids != None and arbid not in arbids:
                # allow filtering of arbids
                continue

            yield((idx, ts, arbid, data))

    def getCanMsgCountIso(self):
        # FIXME: move to "indexed" CAN interfaces, to allow for up to 10 or more without new code.
        '''
        the number of CAN messages we've received on the isolation side session
        '''
        canmsgs = self._messages.get(CMD_ISO_RECV, [])
        return len(canmsgs)

    def printSessionStatsByBookmarkIso(self, start=None, stop=None):
        # FIXME: move to "indexed" CAN interfaces, to allow for up to 10 or more without new code.
        '''
        Prints session stats only for messages between two bookmarks
        '''
        print(self.getSessionStatsByBookmarkIso(start, stop))

    def printSessionStatsIso(self, start=0, stop=None):
        # FIXME: move to "indexed" CAN interfaces, to allow for up to 10 or more without new code.
        '''
        Print session stats by Arbitration ID (aka WID/PID/CANID/etc...)
        between two message indexes (where they sit in the CMD_CAN_RECV
        mailbox)
        '''
        print(self.getSessionStatsIso(start, stop))
        # FIXME: move to "indexed" CAN interfaces, to allow for up to 10 or more without new code.

    def getSessionStatsByBookmarkIso(self, start=None, stop=None):
        # FIXME: move to "indexed" CAN interfaces, to allow for up to 10 or more without new code.
        '''
        returns session stats by bookmarks
        '''
        if start != None:
            start_msg = self.getMsgIndexFromBookmarkIso(start)
        else:
            start_msg = 0

        if stop != None:
            stop_msg = self.getMsgIndexFromBookmarkIso(stop)
        else:
            stop_msg = self.getCanMsgCountIso()

        return self.getSessionStatsIso(start=start_msg, stop=stop_msg)

    def getArbitrationIdsIso(self, start=0, stop=None, reverse=False):
        # FIXME: move to "indexed" CAN interfaces, to allow for up to 10 or more without new code.
        '''
        return a list of Arbitration IDs
        '''
        arbids = {}
        msg_count = 0
        for idx,ts,arbid,data in self.genCanMsgsIso(start, stop):
            arbmsgs = arbids.get(arbid)
            if arbmsgs == None:
                arbmsgs = []
                arbids[arbid] = arbmsgs
            arbmsgs.append((ts, data))
            msg_count += 1

        arbid_list = [(len(msgs), arbid, msgs) for arbid,msgs in arbids.items()]
        arbid_list.sort(reverse=reverse)

        return arbid_list

    def getSessionStatsIso(self, start=0, stop=None):
        # FIXME: move to "indexed" CAN interfaces, to allow for up to 10 or more without new code.
        out = []

        arbid_list = self.getArbitrationIdsIso(start=start, stop=stop, reverse=True)

        for datalen, arbid, msgs in arbid_list:
            last = 0
            high = 0
            low = 0xffffffff
            for ts, data in msgs:
                if last == 0:
                    last = ts
                    continue

                # calculate the high and low
                delta = ts - last
                if delta > high:
                    high = delta
                if delta < low:
                    low = delta

                # track repeated values (rounded to nearest .001 sec)
                last = ts

            if datalen > 1:
                mean = (msgs[-1][0] - msgs[0][0]) / (datalen-1)
                median = low + (high-low) / 2
            else:
                low = 0
                mean = 0
                median = mean
            out.append("id: 0x%x\tcount: %d\ttiming::  mean: %.3f\tmedian: %.3f\thigh: %.3f\tlow: %.3f" % \
                    (arbid, datalen, mean, median, high, low))

        msg_count = self.getCanMsgCountIso()
        out.append("Total Uniq IDs: %d\nTotal Messages: %d" % (len(arbid_list), msg_count))
        return '\n'.join(out)

    # bookmark subsystem
    def placeCanBookmark(self, name=None, comment=None):
        '''
        Save a named bookmark (with optional comment).
        This stores the message index number from the
        CMD_ISO_RECV mailbox.

        This also places a bookmark in the normal CAN message
        stream.

        DON'T USE CANrecv or recv(CMD_CAN_RECV) with Bookmarks or Snapshots!!
        '''
        mbox = self._messages.get(CMD_ISO_RECV)
        if mbox == None:
            msg_index = 0
        else:
            msg_index = len(mbox)

        bkmk_index = len(self.bookmarks_iso)
        self.bookmarks_iso.append(msg_index)

        info = { 'name' : name,
                'comment' : comment }

        self.bookmark_info_iso[bkmk_index] = info #should this be msg_index? benefit either way?
        CanInterface.placeCanBookmark(self, name=name, comment=comment)
        return bkmk_index

    def getMsgIndexFromBookmarkIso(self, bkmk_index):
        # FIXME: move to "indexed" CAN interfaces, to allow for up to 10 or more without new code.
        return self.bookmarks_iso[bkmk_index]

    def getBookmarkFromMsgIndexIso(self, msg_index):
        # FIXME: move to "indexed" CAN interfaces, to allow for up to 10 or more without new code.
        bkmk_index = self.bookmarks_iso.index(msg_index)
        return bkmk_index

    def setCanBookmarkNameIso(self, bkmk_index, name):
        # FIXME: move to "indexed" CAN interfaces, to allow for up to 10 or more without new code.
        info = self.bookmark_info_iso[bkmk_index]
        info[name] = name

    def setCanBookmarkCommentIso(self, bkmk_index, comment):
        # FIXME: move to "indexed" CAN interfaces, to allow for up to 10 or more without new code.
        info = self.bookmark_info_iso[bkmk_index]
        info[name] = name

    def setCanBookmarkNameByMsgIndexIso(self, msg_index, name):
        # FIXME: move to "indexed" CAN interfaces, to allow for up to 10 or more without new code.
        bkmk_index = self.bookmarks_iso.index(msg_index)
        info = self.bookmark_info_iso[bkmk_index]
        info[name] = name

    def setCanBookmarkCommentByMsgIndexIso(self, msg_index, comment):
        # FIXME: move to "indexed" CAN interfaces, to allow for up to 10 or more without new code.
        bkmk_index = self.bookmarks_iso.index(msg_index)
        info = self.bookmark_info_iso[bkmk_index]
        info[name] = name

    def snapshotCanMessagesIso(self, name=None, comment=None):
        # FIXME: move to "indexed" CAN interfaces, to allow for up to 10 or more without new code.
        '''
        Save bookmarks at the start and end of some event you are about to do
        Bookmarks are named "Start_" + name and "Stop_" + name

        DON'T USE CANrecv or recv(CMD_CAN_RECV) with Bookmarks or Snapshots!!
        '''
        start_bkmk = self.placeCanBookmarkIso("Start_" + name, comment)
        input("Press Enter When Done...")
        stop_bkmk = self.placeCanBookmarkIso("Stop_" + name, comment)

    def filterCanMsgsByBookmarkIso(self, start_bkmk=None, stop_bkmk=None, start_baseline_bkmk=None, stop_baseline_bkmk=None,
                    arbids=None, ignore=[], advfilters=[]):
        # FIXME: move to "indexed" CAN interfaces, to allow for up to 10 or more without new code.

        if start_bkmk != None:
            start_msg = self.getMsgIndexFromBookmarkIso(start_bkmk)
        else:
            start_msg = 0

        if stop_bkmk != None:
            stop_msg = self.getMsgIndexFromBookmarkIso(stop_bkmk)
        else:
            stop_bkmk = -1

        if start_baseline_bkmk != None:
            start_baseline_msg = self.getMsgIndexFromBookmarkIso(start_baseline_bkmk)
        else:
            start_baseline_msg = None

        if stop_baseline_bkmk != None:
            stop_baseline_msg = self.getMsgIndexFromBookmarkIso(stop_baseline_bkmk)
        else:
            stop_baseline_msg = None

        return self.filterCanMsgsIso(start_msg, stop_msg, start_baseline_msg, stop_baseline_msg, arbids, ignore, advfilters)

    def filterCanMsgsIso(self, start_msg=0, stop_msg=None, start_baseline_msg=None, stop_baseline_msg=None, arbids=None, ignore=[], advfilters=[]):
        # FIXME: move to "indexed" CAN interfaces, to allow for up to 10 or more without new code.
        '''
        Iso means the second CAN bus (M2's and DUE_CAN models have two CAN interfaces)

        returns the received CAN messages between indexes "start_msg" and "stop_msg"
        but only messages to ID's that *do not* appear in the the baseline indicated
        by "start_baseline_msg" and "stop_baseline_msg".

        for message indexes, you *will* want to look into the bookmarking subsystem!
        '''
        self.log("starting filtering messages...")
        if stop_baseline_msg != None:
            self.log("ignoring arbids from baseline...")
            # get a list of baseline arbids
            filter_ids = { arbid:1 for ts,arbid,data in self.genCanMsgs(start_baseline_msg, stop_baseline_msg)
                }.keys()
        else:
            filter_ids = None
        self.log("filtering messages...")

        if type(arbids) != list:
            arbids = [arbids]

        for idx,ts,arbid,msg in self.genCanMsgs(start_msg, stop_msg, arbids=arbids):
            if not ((arbids != None and arbid in arbids) or arbid not in ignore and (filter_ids==None or arbid not in filter_ids)):
                continue

            # advanced filters allow python code to be handed in.  if any of the python code snippits result in "False" or 0, skip this message
            skip = False
            for advf in advfilters:
                lcls = self._locals(idx, ts, arbid, msg)
                if not eval(advf, lcls):
                    skip = True

            if skip:
                continue

            yield (idx, ts,arbid,msg)

    def printCanMsgsByBookmarkIso(self, start_bkmk=None, stop_bkmk=None, start_baseline_bkmk=None, stop_baseline_bkmk=None,
                    arbids=None, ignore=[], advfilters=[]):
        '''
        deprecated: use printCanMsgs(start_bkmk=foo, stop_bkmk=bar)
        '''
        # FIXME: move to "indexed" CAN interfaces, to allow for up to 10 or more without new code.
        print(self.reprCanMsgsByBookmarkIso(start_bkmk, stop_bkmk, start_baseline_bkmk, stop_baseline_bkmk, arbids, ignore, advfilters))

    def reprCanMsgsByBookmarkIso(self, start_bkmk=None, stop_bkmk=None, start_baseline_bkmk=None, stop_baseline_bkmk=None, arbids=None, ignore=[], advfilters=[]):
        # FIXME: move to "indexed" CAN interfaces, to allow for up to 10 or more without new code.
        '''
        deprecated: use reprCanMsgs(start_bkmk=foo, stop_bkmk=bar)
        '''
        out = []

        if start_bkmk != None:
            start_msg = self.getMsgIndexFromBookmarkIso(start_bkmk)
        else:
            start_msg = 0

        if stop_bkmk != None:
            stop_msg = self.getMsgIndexFromBookmarkIso(stop_bkmk)
        else:
            stop_bkmk = -1

        if start_baseline_bkmk != None:
            start_baseline_msg = self.getMsgIndexFromBookmarkIso(start_baseline_bkmk)
        else:
            start_baseline_msg = None

        if stop_baseline_bkmk != None:
            stop_baseline_msg = self.getMsgIndexFromBookmarkIso(stop_baseline_bkmk)
        else:
            stop_baseline_msg = None

        return self.reprCanMsgsIso(start_msg, stop_msg, start_baseline_msg, stop_baseline_msg, arbids, ignore, advfilters)

    def printCanMsgsIso(self, start_msg=0, stop_msg=None, start_baseline_msg=None, stop_baseline_msg=None, arbids=None, ignore=[], advfilters=[]):
        # FIXME: move to "indexed" CAN interfaces, to allow for up to 10 or more without new code.
        print(self.reprCanMsgsIso(start_msg, stop_msg, start_baseline_msg, stop_baseline_msg, arbids, ignore, advfilters))

    def reprCanMsgsIso(self, start_msg=0, stop_msg=None, start_baseline_msg=None, stop_baseline_msg=None, arbids=None, ignore=[], advfilters=[]):
        # FIXME: move to "indexed" CAN interfaces, to allow for up to 10 or more without new code.
        '''
        String representation of a set of CAN Messages.
        These can be filtered by start and stop message indexes, as well as
        use a baseline (defined by start/stop message indexes),
        by a list of "desired" arbids as well as a list of
        ignored arbids

        Many functions wrap this one.
        '''
        out = []

        if start_msg in self.bookmarks_iso:
            bkmk = self.bookmarks_iso.index(start_msg)
            out.append("starting from bookmark %d: '%s'" %
                    (bkmk,
                    self.bookmark_info_iso[bkmk].get('name'))
                    )

        if stop_msg in self.bookmarks_iso:
            bkmk = self.bookmarks_iso.index(stop_msg)
            out.append("stoppng at bookmark %d: '%s'" %
                    (bkmk,
                    self.bookmark_info_iso[bkmk].get('name'))
                    )

        last_msg = None
        next_bkmk = 0
        next_bkmk_idx = 0

        msg_count = 0
        last_ts = None
        tot_delta_ts = 0
        counted_msgs = 0    # used for calculating averages, excluding outliers

        data_delta = None


        data_repeat = 0
        data_similar = 0

        for filtmsg in self.filterCanMsgsIso(start_msg, stop_msg, start_baseline_msg, stop_baseline_msg, arbids=arbids, ignore=ignore, advfilters=advfilters):
            # if we use "tail" we may yield Nones if we're waiting.
            if filtmsg is None:
                yield None
                continue

            idx, ts, arbid, msg = filtmsg
            diff = []

            # insert bookmark names/comments in appropriate places
            while next_bkmk_idx < len(self.bookmarks_iso) and idx >= self.bookmarks_iso[next_bkmk_idx]:
                out.append(self.reprBookmarkIso(next_bkmk_idx))
                next_bkmk_idx += 1

            msg_count += 1

            # check data
            byte_cnt_diff = 0
            if last_msg != None:
                if len(last_msg) == len(msg):
                    for bidx in range(len(msg)):
                        if last_msg[bidx] != msg[bidx]:
                            byte_cnt_diff += 1

                    if byte_cnt_diff == 0:
                        diff.append("REPEAT")
                        data_repeat += 1
                    elif byte_cnt_diff <=4:
                        diff.append("Similar")
                        data_similar += 1
                    # FIXME: make some better heuristic to identify "out of norm"

            # look for ASCII data (4+ consecutive bytes)
            if hasAscii(msg):
                diff.append("ASCII: %s" % repr(msg))

            # calculate timestamp delta and comment if out of whack
            if last_ts == None:
                last_ts = ts

            delta_ts = ts - last_ts
            if counted_msgs:
                avg_delta_ts = tot_delta_ts / counted_msgs
            else:
                avg_delta_ts = delta_ts


            if abs(delta_ts - avg_delta_ts) <= delta_ts:
                tot_delta_ts += delta_ts
                counted_msgs += 1
            else:
                diff.append("TS_delta: %.3f" % delta_ts)

            out.append(reprCanMsg(idx, ts, arbid, msg, comment='\t'.join(diff)))
            last_ts = ts
            last_msg = msg

        out.append("Total Messages: %d  (repeat: %d / similar: %d)" % (msg_count, data_repeat, data_similar))

        return "\n".join(out)

    def printCanSessionsIso(self, arbid_list=None, advfilters=[]):
        '''
        Split CAN messages into Arbitration ID's and prints entire
        sessions for each CAN id.
        Defaults to printing by least number of messages, including all IDs
        Or... provide your own list of ArbIDs in whatever order you like
        '''
        if arbid_list == None:
            arbids = self.getArbitrationIdsIso()
        else:
            arbids = [arbdata for arbdata in self.getArbitrationIdsIso() if arbdata[1] in arbid_list]
        for datalen,arbid,msgs in arbids:
            print(self.reprCanMsgsIso(arbids=[arbid], advfilters=advfilters))
            input("\nPress Enter to review the next Session...")
            print

    def printBookmarksIso(self):
        '''
        Print out the list of current Bookmarks and where they sit
        '''
        print(self.reprBookmarksIso())

    def printAsciiStringsIso(self, minbytes=4, strict=True):
        '''
        Search through messages looking for ASCII strings
        '''
        for idx, ts, arbid, msg in self.genCanMsgsIso():
            if hasAscii(msg, minbytes=minbytes, strict=strict):
                print(reprCanMsgIso(idx, ts, arbid, msg, repr(msg)))

    def reprBookmarksIso(self):
        '''
        get a string representation of the bookmarks
        '''
        out = []
        for bid in range(len(self.bookmarks_iso)):
            out.append(self.reprBookmarkIso(bid))
        return '\n'.join(out)

    def reprBookmarkIso(self, bid):
        '''
        get a string representation of one bookmark
        '''
        msgidx = self.bookmarks_iso[bid]
        info = self.bookmark_info_iso.get(bid)
        comment = info.get('comment')
        if comment == None:
            return "bkmkidx: %d\tmsgidx: %d\tbkmk: %s" % (bid, msgidx, info.get('name'))

    def restoreSession(self, me, force=False):
        '''
        Load a previous analysis session from a python dictionary object
        see: saveSession()
        '''
        if isinstance(self._io, serial.Serial) and force==False:
            print("Refusing to reload a session while active session!  use 'force=True' option")
            return

        self._messages = me.get('messages')
        self.bookmarks = me.get('bookmarks')
        self.bookmark_info = me.get('bookmark_info')
        self.comments = me.get('comments')
        self.bookmarks_iso = me.get('bookmarks_iso')
        self.bookmark_info_iso = me.get('bookmark_info_iso')

    def saveSession(self):
        '''
        Save the current analysis session to a python dictionary object
        What you do with it form there is your own business.
        This function is called by saveSessionToFile() to get the data
        to save to the file.
        '''
        savegame = { 'messages' : self._messages,
                'bookmarks' : self.bookmarks,
                'bookmark_info' : self.bookmark_info,
                'bookmarks_iso' : self.bookmarks_iso,
                'bookmark_info_iso' : self.bookmark_info_iso,
                'comments' : self.comments,
                'file_version' : 1.0,
                'class' : self.__class__,
                'config' : self._config,
                }
        return savegame


######### administrative, supporting code ##########
cs = []

def cleanupInteractiveAtExit():
    global cs
    for c in cs:
        try:
            c.__del__()
        except:
            pass

def getDeviceFile():
    import serial.tools.list_ports

    for n, (port, desc, hwid) in enumerate(sorted(serial.tools.list_ports.comports()), 1):
        if os.path.exists(port):
            return port

def interactive(port=None, InterfaceClass=CanInterface, intro='', load_filename=None, can_baud=None):
    global c
    import atexit

    c = InterfaceClass(port=port, load_filename=load_filename)
    atexit.register(cleanupInteractiveAtExit)

    if load_filename is None:
        if can_baud != None:
            c.setCanBaud(can_baud)
        else:
            c.setCanBaud(CAN_500KBPS)

    gbls = globals()
    lcls = locals()

    try:
        import IPython
        ipsh = IPython.embed(banner1=intro, colors="neutral")


    except ImportError as e:
        try:
            from IPython.terminal.interactiveshell import TerminalInteractiveShell
            from IPython.terminal.ipapp import load_default_config
            ipsh = TerminalInteractiveShell(config=load_default_config())
            ipsh.user_global_ns.update(gbls)
            ipsh.user_global_ns.update(lcls)
            ipsh.autocall = 2       # don't require parenthesis around *everything*.  be smart!
            ipsh.mainloop(intro)
        except ImportError as e:

            try:
                from IPython.frontend.terminal.interactiveshell import TerminalInteractiveShell
                ipsh = TerminalInteractiveShell()
                ipsh.user_global_ns.update(gbls)
                ipsh.user_global_ns.update(lcls)
                ipsh.autocall = 2       # don't require parenthesis around *everything*.  be smart!
                ipsh.mainloop(intro)
            except ImportError as e:
                print(e)
                shell = code.InteractiveConsole(gbls)
                shell.interact(intro)

