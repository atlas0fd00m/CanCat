import sys
import cmd
import time
import serial
import struct
import threading
import cPickle as pickle

# defaults for Linux:
serialdev = '/dev/ttyACM0'
baud = 115200


# command constants (used to identify messages between 
# python client and the CanCat transceiver
CMD_LOG                     = 0x2f
CMD_LOG_HEX                 = 0x2e

CMD_CAN_RECV                = 0x30
CMD_PING_RESPONSE           = 0x31
CMD_CHANGE_BAUD_RESULT      = 0x32
CMD_CAN_BAUD_RESULT         = 0x33
CMD_CAN_SEND_RESULT         = 0x34

CMD_PING                    = 0x41
CMD_CHANGE_BAUD             = 0x42
CMD_CAN_BAUD                = 0x43
CMD_CAN_SEND                = 0x44


# constants for setting baudrate for the CAN bus
CAN_5KBPS       = 1
CAN_10KBPS      = 2
CAN_20KBPS      = 3
CAN_31K25BPS    = 4
CAN_33KBPS      = 5
CAN_40KBPS      = 6
CAN_50KBPS      = 7
CAN_80KBPS      = 8
CAN_95KBPS      = 9
CAN_100KBPS     = 10
CAN_125KBPS     = 11
CAN_200KBPS     = 12
CAN_250KBPS     = 13
CAN_500KBPS     = 14
CAN_1000KBPS    = 15

# state constants for the Receiver thread
RXTX_DISCONN    = -1
RXTX_SYNC       = 0
RXTX_GO         = 1

# constants for CANreplay mode
TIMING_FAST         = 0
TIMING_REAL         = 1
TIMING_INTERACTIVE  = 2

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

def handleCanMsgsDuringSniff(message, canbuf):
    idx, ts = canbuf._submitMessage(CMD_CAN_RECV, message)
    ts = time.time()
    arbid, data = self.splitCanMsg(message)

    print reprCanMsg(ts, arbid, data)

default_cmdhandlers = {
        CMD_LOG : handleLogToScreen,
        CMD_LOG_HEX: handleLogHexToScreen,
        }


def loadCanBuffer(filename):
    return pickle.load(file(filename))

class CanInterface:
    def __init__(self, port=serialdev, baud=baud, verbose=False, cmdhandlers=None, comment='', load_filename=None):
        '''
        CAN Analysis Workspace
        This can be subclassed by vendor to allow more vendor-specific code 
        based on the way each vendor uses the varios Buses
        '''
        self._inbuf = ''
        self.trash = []
        self.messages = {}
        self.queuelock = threading.Lock()
        self._shutdown = False
        self.verbose = verbose
        self.port = port
        self.baud = baud
        self.io = None
        self._in_lock = None
        self._out_lock = None
        self.name = port
        self.commsthread = None
        self._last_can_msg = None

        self.bookmarks = []
        self.bookmark_info = {}

        self.comments = []
        if cmdhandlers == None:
            cmdhandlers = default_cmdhandlers
        self.cmdhandlers = cmdhandlers

        if load_filename != None:
            self.loadFromFile(load_filename)
            return

        self.reconnect()

        self.commsthread = threading.Thread(target=self._rxtx)
        self.commsthread.setDaemon(True)
        self.commsthread.start()

    def register_handler(self, cmd, handler):
        self.cmdhandlers[cmd] = handler

    def remove_handler(self, cmd):
        self.cmdhandlers[cmd] = None

    def reconnect(self, port=None, baud=None):
        '''
        Attempt to connect/reconnect to the CanCat Transceiver
        '''
        if self.port == None and port == None:
            print "cannot connect to an unspecified port"
            return

        if self.io != None:
            self.io.close()

        self.io = serial.Serial(port=self.port, baudrate=self.baud, dsrdtr=True)
        self.io.setDTR(True)

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

        return self.io

    def __del__(self):
        '''
        Destructor, called when the CanInterface object is being garbage collected
        '''
        print "shutting down serial connection"
        if isinstance(self.io, serial.Serial):
            self.io.close()
        self._shutdown = True
        if self.commsthread != None:
            self.commsthread.wait()

    def clearCanMsgs(self):
        '''
        Clear out all messages currently received on the CAN bus, allowing for 
        basically a new analysis session without creating a new object/connection

        returns a list of the messages
        '''
        return self.recvall(CMD_CAN_RECV)

    def _rxtx(self):
        '''
        Receiver thread runner.  Internal use only.
        Processes data from the CanCat transceiver, parses and places messages
        into correct mailboxes and/or hands off to pre-configured handlers.
        '''
        self._rxtx_state = RXTX_SYNC

        while not self._shutdown:
            try:    
                if self.verbose > 4:
                    if self.verbose > 5: 
                        print "STATE: %s" % self._rxtx_state
                    else:
                        sys.stderr.write('.')

                # try to reconnect to disconnected unit (FIXME: not working right yet)
                if self._rxtx_state == RXTX_DISCONN:
                    print "FIXME: reconnect disconnected serial port..."
                    time.sleep(1)
                    self.reconnect()
                    self._rxtx_state = RXTX_SYNC
                    continue

                # fill the queue
                self._in_lock.acquire()
                try:
                    char = self.io.read()

                except serial.serialutil.SerialException, e:
                    self.errorcode = e
                    self.log("serial exception")
                    if "disconnected" in e.message:
                        self.io.close()
                        self._rxtx_state = RXTX_DISCONN
                    continue

                finally:
                    if self._in_lock.locked_lock():
                        self._in_lock.release()

                self._inbuf += char
                self.log("RECV: %s" % repr(self._inbuf))

                # make sure we're synced
                if self._rxtx_state == RXTX_SYNC:
                    if self._inbuf[0] != "@":
                        self.queuelock.acquire()
                        try:
                            idx = self._inbuf.find('@')
                            if idx == -1:
                                self.log("sitting on garbage...", 3)
                                continue

                            trash = self._inbuf[:idx]
                            self.trash.append(trash)

                            self._inbuf = self._inbuf[idx:]
                        finally:
                            self.queuelock.release()

                    self._rxtx_state = RXTX_GO

                # handle buffer if we have anything in it
                if self._rxtx_state == RXTX_GO:
                    if len(self._inbuf) < 3: continue
                    if self._inbuf[0] != '@': 
                        self._rxtx_state = RXTX_SYNC
                        continue

                    pktlen = ord(self._inbuf[1]) + 2        # <size>, doesn't include "@"

                    if len(self._inbuf) >= pktlen:
                        self.queuelock.acquire()
                        try:
                            cmd = ord(self._inbuf[2])                # first bytes are @<size>
                            message = self._inbuf[3:pktlen]  
                            self._inbuf = self._inbuf[pktlen:]
                        finally:
                            self.queuelock.release()

                        #if we have a handler, use it
                        cmdhandler = self.cmdhandlers.get(cmd)
                        if cmdhandler != None:
                            cmdhandler(message, self)

                        # otherwise, file it
                        else:
                            self._submitMessage(cmd, message)
                        self._rxtx_state = RXTX_SYNC

                
            except:
                if self.verbose:
                    sys.excepthook(*sys.exc_info())

    def _submitMessage(self, cmd, message):
        '''
        submits a message to the cmd mailbox.  creates mbox if doesn't exist.
        *threadsafe*
        '''
        timestamp = time.time()

        self.queuelock.acquire()
        try:
            mbox = self.messages.get(cmd)
            if mbox == None:
                mbox = []
                self.messages[cmd] = mbox
            mbox.append((timestamp, message))
        finally:
            self.queuelock.release()
        return len(mbox)-1, timestamp

    def log(self, message, verbose=1):
        '''
        print a log message.  Only prints if CanCat's verbose setting >=verbose
        '''
        if self.verbose >= verbose:
            print "%.2f %s: %s" % (time.time(), self.name, message)

    def recv(self, cmd, wait=None):
        '''
        Warning: Destructive:
            removes a message from a mailbox and returns it.
            For CMD_CAN_RECV mailbox, this will alter analysis results!
        '''
        start = time.time()
        while (time.time() - start) < wait:
            mbox = self.messages.get(cmd)
            if mbox != None and len(mbox):
                self.queuelock.acquire()
                try:
                    timestamp, message = mbox.pop(0)
                finally:
                    self.queuelock.release()

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
        mbox = self.messages.get(cmd)
        if mbox == None:
            return []

        self.queuelock.acquire()
        try:
            messages = list(mbox)
            self.messages[cmd] = []
        finally:
            self.queuelock.release()

        return messages

    def inWaiting(self, cmd):
        '''
        Does the given cmd mailbox have any messages??
        '''
        mbox = self.messages.get(cmd)
        if mbox == None:
            return 0
        return len(mbox)

    def send(self, cmd, message):
        '''
        Send a message to the CanCat transceiver (not the CAN bus)
        '''
        msgchar = chr(len(message) + 2)
        msg = msgchar + chr(cmd) + message
        self.log("XMIT: %s" % repr(msg))

        self._out_lock.acquire()
        try:
            self.io.write(msg)
        finally:
            self._out_lock.release()
        # FIXME: wait for response?

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

    def CANxmit(self, arbid, message, extflag=0):
        '''
        Transmit a CAN message on the attached CAN bus
        '''
        msg = struct.pack('>I', arbid) + chr(extflag) + message
        return self.send(CMD_CAN_SEND, msg)

    def CANsniff(self):
        '''
        set a handler for CMD_CAN_RECV messages that print them to stdout.
        Messages are still stored in the CMD_CAN_RECV mailbox for analysis,
        this simply allows you to see the as they are received... not always
        advisable, as there are *MANY* almost all the time :)
        '''
        self.register_handler(CMD_CAN_RECV, handleCanMsgsDuringSniff)
        raw_input("Press Enter to stop sniffing")
        self.remove_handler(CMD_CAN_RECV)

    def CANreplay(self, bkmk_start=None, bkmk_stop=None, start_msg=0, stop_msg=None, arbids=None, timing=TIMING_FAST):
        '''
        Replay packets between two bookmarks.
        timing = TIMING_FAST: just slam them down the CAN bus as fast as possible
        timing = TIMING_READ: send the messages using similar timing to how they 
                    were received
        timing = TIMING_INTERACTIVE: wait for the user to press Enter between each
                    message being transmitted
        '''
        if start_bkmk != None:
            start_msg = self.getMsgIndexFromBookmark(start_bkmk)

        if stop_bkmk != None:
            stop_msg = self.getMsgIndexFromBookmark(stop_bkmk)

        last_time = -1
        for idx,ts,arbid,data in self.genCanMsgs(start_msg, stop_msg, arbids=arbids):
            if timing == TIMING_INTERACTIVE:
                raw_input("%s\nPress Enter to Transmit" % self.reprCanMsg(idx, ts, arbid, data))

            elif timing == TIMING_REAL:
                if last_time != -1:
                    delta = ts - last_time
                    time.sleep(delta)
                last_time = ts

            self.CANxmit(arbid, data)

    def setCanBaud(self, baud_const=CAN_500KBPS):
        '''
        set the baud rate for the CAN bus.  this has nothing to do with the 
        connection from the computer to the tool
        '''
        self.send(CMD_CAN_BAUD, chr(baud_const))

    def ping(self, buf='ABCDEFGHIJKL'):
        '''
        Utility function, only to send and receive data from the 
        CanCat Transceiver.  Has no effect on the CAN bus
        '''
        self.send(CMD_PING, buf)
        response = self.recv(CMD_PING_RESPONSE, wait=3)
        return response

    def genCanMsgs(self, start=0, stop=None, arbids=None):
        '''
        CAN message generator.  takes in start/stop indexes as well as a list
        of desired arbids (list)
        '''
        messages = self.messages.get(CMD_CAN_RECV, [])
        if stop == None:
            stop = len(messages)

        for idx in xrange(start, stop):
            ts, msg = messages[idx]

            arbid, data = self.splitCanMsg(msg)

            if arbids != None and arbid not in arbids:
                # allow filtering of arbids
                continue

            yield((idx, ts, arbid, data))

    def splitCanMsg(self, msg):
        '''
        takes in captured message
        returns arbid and data

        does not check msg size.  MUST be at least 4 bytes in length as the 
        tool should send 4 bytes for the arbid
        '''
        arbid = struct.unpack(">I", msg[:4])[0]
        data = msg[4:]
        return arbid, data

    def getCanMsgCount(self):
        '''
        the number of CAN messages we've received this session
        '''
        canmsgs = self.messages.get(CMD_CAN_RECV, [])
        return len(canmsgs)

    def printSessionStatsByBookmark(self, start=None, stop=None):
        '''
        Prints session stats only for messages between two bookmarks
        '''
        print self.getSessionStatsByBookmark(start, stop)

    def printSessionStats(self, start=0, stop=None):
        '''
        Print session stats by Arbitration ID (aka WID/PID/CANID/etc...)
        between two message indexes (where they sit in the CMD_CAN_RECV
        mailbox)
        '''
        print self.getSessionStats(start, stop)

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

        return self.getSessionStats(start=start_msg, stop=stop_msg)

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
        
        arbid_list = self.getArbitrationIds(reverse=True)

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

    def loadFromFile(self, filename):
        '''
        Load a previous analysis session from a saved file
        see: saveSessionToFile()
        '''
        me = pickle.load(file(filename))
        self.restoreSession(me)
        self._filename = filename

    def restoreSession(self, me, force=False):
        '''
        Load a previous analysis session from a python dictionary object
        see: saveSession()
        '''
        if isinstance(self.io, serial.Serial) and force==False:
            print("Refusing to reload a session while active session!  use 'force=True' option")
            return

        self.messages = me.get('messages')
        self.bookmarks = me.get('bookmarks')
        self.bookmark_info = me.get('bookmark_info')
        self.comments = me.get('comments')

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

        outfile = file(filename, 'w')
        outfile.write(me)
        outfile.close()
    
    def saveSession(self):
        '''
        Save the current analysis session to a python dictionary object
        What you do with it form there is your own business.
        This function is called by saveSessionToFile() to get the data
        to save to the file.
        '''
        savegame = { 'messages' : self.messages,
                'bookmarks' : self.bookmarks,
                'bookmark_info' : self.bookmark_info,
                'comments' : self.comments,
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
        mbox = self.messages.get(CMD_CAN_RECV)
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
        raw_input("Press Enter When Done...")
        stop_bkmk = self.placeCanBookmark("Stop_" + name, comment)

    def filterCanMsgsByBookmark(self, start_bkmk=None, stop_bkmk=None, start_baseline_bkmk=None, stop_baseline_bkmk=None, 
                    arbids=None, ignore=[]):

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

        return self.filterCanMsgs(start_msg, stop_msg, start_baseline_msg, stop_baseline_msg, arbids, ignore)

    def filterCanMsgs(self, start_msg=0, stop_msg=None, start_baseline_msg=None, stop_baseline_msg=None, arbids=None, ignore=[]):
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
            filter_ids = { arbid:1 for ts,arbid,data in self.genCanMsgs(start_baseline_msg, stop_baseline_msg) 
                }.keys()
        else:
            filter_ids = None
        self.log("filtering messages...")
        filteredMsgs = [(idx, ts,arbid,msg) for idx,ts,arbid,msg in self.genCanMsgs(start_msg, stop_msg, arbids=arbids) \
                if (type(arbids) == list and arbid in arbids) or arbid not in ignore and (filter_ids==None or arbid not in filter_ids)]

        return filteredMsgs
        
    def printCanMsgsByBookmark(self, start_bkmk=None, stop_bkmk=None, start_baseline_bkmk=None, stop_baseline_bkmk=None, 
                    arbids=None, ignore=[]):
        print self.reprCanMsgsByBookmark(start_bkmk, stop_bkmk, start_baseline_bkmk, stop_baseline_bkmk, arbids, ignore)

    def reprCanMsgsByBookmark(self, start_bkmk=None, stop_bkmk=None, start_baseline_bkmk=None, stop_baseline_bkmk=None, arbids=None, ignore=[]):
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

        return self.reprCanMsgs(start_msg, stop_msg, start_baseline_msg, stop_baseline_msg, arbids, ignore)

    def printCanMsgs(self, start_msg=0, stop_msg=None, start_baseline_msg=None, stop_baseline_msg=None, arbids=None, ignore=[]):
        print self.reprCanMsgs(start_msg, stop_msg, start_baseline_msg, stop_baseline_msg, arbids, ignore)

    def reprCanMsgs(self, start_msg=0, stop_msg=None, start_baseline_msg=None, stop_baseline_msg=None, arbids=None, ignore=[]):
        '''
        String representation of a set of CAN Messages.
        These can be filtered by start and stop message indexes, as well as
        use a baseline (defined by start/stop message indexes), 
        by a list of "desired" arbids as well as a list of 
        ignored arbids

        Many functions wrap this one.
        '''
        out = []

        if start_msg in self.bookmarks:
            bkmk = self.bookmarks.index(start_msg)
            out.append("starting from bookmark %d: '%s'" % 
                    (bkmk,
                    self.bookmark_info[bkmk].get('name'))
                    )

        if stop_msg in self.bookmarks:
            bkmk = self.bookmarks.index(stop_msg)
            out.append("stoppng at bookmark %d: '%s'" % 
                    (bkmk,
                    self.bookmark_info[bkmk].get('name'))
                    )

        last_msg = None
        last_bkmk = 0
        next_bkmk_idx = 0

        msg_count = 0
        last_ts = None
        tot_delta_ts = 0
        counted_msgs = 0    # used for calculating averages, excluding outliers
        
        data_delta = None


        for idx, ts, arbid, msg in self.filterCanMsgs(start_msg, stop_msg, start_baseline_msg, stop_baseline_msg, arbids=arbids, ignore=ignore):
            diff = []

            while idx > last_bkmk and next_bkmk_idx < len(self.bookmarks):
                out.append(self.reprBookmark(next_bkmk_idx))
                last_bkmk = self.bookmarks[next_bkmk_idx]
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
                    elif byte_cnt_diff <=4:
                        diff.append("Similar")
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

        out.append("Total Messages: %d" % msg_count)

        return "\n".join(out)

    def printCanSessions(self, arbid_list=None):
        '''
        Split CAN messages into Arbitration ID's and prints entire
        sessions for each CAN id.
        Defaults to printing by least number of messages, including all IDs
        Or... provide your own list of ArbIDs in whatever order you like
        '''
        if arbid_list == None:
            arbid_list = self.getArbitrationIds()
        for datalen,arbid,msgs in arbid_list:
            print self.reprCanMsgs(arbids=[arbid])
            raw_input("\nPress Enter to review the next Session...")
            print 

    def printBookmarks(self):
        '''
        Print out the list of current Bookmarks and where they sit
        '''
        print(self.reprBookmarks())

    def printAsciiStrings(self, minbytes=4):
        '''
        Search through messages looking for ASCII strings
        '''
        for idx, ts, arbid, msg in self.genCanMsgs():
            if hasAscii(msg, minbytes=minbytes):
                print reprCanMsg(idx, ts, arbid, msg, repr(msg))

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

class CanControl(cmd.Cmd):
    '''
    Command User Interface (as if ipython wasn't enough!)
    '''
    def __init__(self, serialdev=serialdev, baud=baud):
        cmd.Cmd.__init__(self)
        self.serialdev = serialdev
        self.canbuf = CanBuffer(self.serialdev, self.baud)


def hasAscii(msg, minbytes=4):
    ascii_match = 0
    ascii_count = 0
    for byte in msg:
        if 0x30 <= ord(byte) < 0x7f:
            ascii_count +=1
            if ascii_count >= minbytes:
                ascii_match = 1
        else:
            ascii_count = 0
    return ascii_match

def reprCanMsg(idx, ts, arbid, data, comment=None):
    #TODO: make some repr magic that spits out known ARBID's and other subdata
    if comment == None:
        comment = ''
    return "%.8d %8.3f ID: %.3x,  Len: %.2x, Data: %s\t%s" % (idx, ts, arbid, len(data), data.encode('hex'), comment)


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
