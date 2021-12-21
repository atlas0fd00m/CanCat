import traceback
from binascii import hexlify

#from cancat.j1939 import *
# we can move things into here if we decide this replaces the exiting j1939 modules
import cancat
import struct
from cancat.J1939db import *
from cancat import *
from cancat.vstruct.bitfield import *

import queue
import threading
''' 
This is a J1939 Stack module.
It's purpose is to provide a J1939-capable object which extends (consumes) CanCat's CanInterface module, and provides a J1939 interface.
In the original J1939 module, extended messages were treated like oddities.  This module will work on the premise that all messages (except TP messages) are created equal, and are available in the same queue.  TP messages will be the "specialty" messages which create new, arbitrary sized messages from smaller ones.  If they don't make it through, they don't.  This module is intended to make J1939 attack clients easier to work with, whereas the first module was focused on reverse engineering.  Let's see if we can't come up with something awesome, then possible merge them together in the future.

This module focuses around PGNs.  All messages are handled and sorted by their PS/DA.
'''

J1939MSGS = 1939

PF_RQST =       0xea
PF_TP_DT =      0xeb
PF_TP_CM =      0xec
PF_ADDRCLAIM =  0xee
PF_PROPRIETRY=  0xef
PF_KWP1 =       0xdb
PF_KWP2 =       0xda
PF_KWP3 =       0xce
PF_KWP4 =       0xcd

CM_RTS   =       0x10
CM_CTS   =       0x11
CM_EOM   =       0x13
CM_ABORT =       0xff
CM_BAM   =       0x20

TP_BAM = 20
TP_DIRECT = 10
TP_DIRECT_BROKEN=9

class NAME(VBitField):
    def __init__(self):
        VBitField.__init__(self)
        self.arbaddrcap = v_bits(1)
        self.ind_group = v_bits(3)
        self.vehicle_system_instance = v_bits(4)
        self.vehicle_system = v_bits(7)
        self.reserved = v_bits(1)
        self.function = v_bits(8)
        self.function_instance = v_bits(5)
        self.ecu_instance = v_bits(3)
        self.mfg_code = v_bits(11)
        self.identity_number = v_bits(21)

    def minrepr(self):
        mfgname = mfg_lookup.get(self.mfg_code)
        return "id: 0x%x mfg: %s" % (self.identity_number, mfgname)


def parseName(name):
    namebits= NAME()
    rname = name[::-1]
    namebits.vsParse(rname)
    return namebits

def parseArbid(arbid):
    (prioPlus,
        pf,
        ps,
        sa) = struct.unpack(b'BBBB', struct.pack(b">I", arbid))

    prio = prioPlus >> 2
    edp = (prioPlus >> 1) & 1
    dp = prioPlus & 1

    return prio, edp, dp, pf, ps, sa


def meldExtMsgs(msgs):
    out = []
    length = msgs.get('totsize')
    for arbtup, msg in msgs.get('msgs'):
        out.append(msg[1:])

    outval = b''.join(out)
    outval = outval[:length]

    return outval

### renderers for specific PF numbers
def pf_c9(idx, ts, arbtup, data, j1939):
    b4 = data[3]
    req = "%.2x %.2x %.2x" % ([ord(d) for d in data[:3]])
    usexferpfn = ('', 'Use_Transfer_PGN', 'undef', 'NA')[b4 & 3]
    
    return "Request2: %s %s" % (req,  usexferpgn)

def pf_ea(idx, ts, arbtup, data, j1939):
    (prio, edp, dp, pf, ps, sa) = arbtup
    return "Request: %s" % (hexlify(data[:3]))

# no pf_eb or pf_ec since those are handled at a lower-level in this stack

def pf_ee(idx, ts, arbtup, data, j1939):
    prio, edp, dp, pf, ps, sa = arbtup
    if ps == 255 and sa == 254:
        return 'CANNOT CLAIM ADDRESS'
    
    addrinfo = parseName(data).minrepr()
    return "Address Claim: %s" % addrinfo

def pf_ef(idx, ts, arbtup, data, j1939):
    prio, edp, dp, pf, ps, sa = arbtup
    if dp:
        return 'Proprietary A2'

    return 'Proprietary A1'
    
def pf_ff(idx, ts, arbtup, data, j1939):
    prio, edp, dp, pf, ps, sa = arbtup
    pgn = "%.2x :: %.2x:%.2x - %s" % (sa, pf,ps, hexlify(data))
    return "Proprietary B %s" % pgn

pgn_pfs = {
        0x93:   ("Name Management", None),
        0xc9:   ("Request2",        pf_c9),
        0xca:   ('Transfer',        None),
        0xe8:   ("ACK        ",     None),
        0xea:   ("Request      ",   pf_ea),
        0xeb:   ("TP.DT (WTF?)",    None),
        0xec:   ("TP.CM (WTF?)",    None),
        0xee:   ("Address Claim",   pf_ee),
        0xef:   ("Proprietary",     pf_ef),
        #0xfe:   ("Command Address", None),
        0xff:   ("Proprietary B",   pf_ff),
        }


class J1939Interface(cancat.CanInterface):
    _msg_source_idx = J1939MSGS
    def __init__(self, port=None, baud=cancat.baud, verbose=False, cmdhandlers=None, comment='', load_filename=None, orig_iface=None, process_can_msgs=True, promisc=True):
        self._last_recv_idx = -1
        self._threads = []
        self._j1939_filters = []
        self._j1939_msg_events = {}
        self._j1939queuelock = threading.Lock()
        self._TPmsgParts = {}
        self.maxMsgsPerPGN = 0x200
        self._j1939_msg_listeners = []
        self.promisc = promisc

        cancat.CanInterface.__init__(self, port=port, baud=baud, verbose=verbose, cmdhandlers=cmdhandlers, comment=comment, load_filename=load_filename, orig_iface=orig_iface)

        # setup the message handler event offload thread
        if self._config.get('myIDs') is None:
            self._config['myIDs'] = []

        self._mhe_queue = queue.Queue()
        mhethread = threading.Thread(target=self._mhe_runner)
        mhethread.setDaemon(True)
        mhethread.start()
        self._threads.append(mhethread)

        self.register_handler(CMD_CAN_RECV, self._j1939_can_handler)

        if process_can_msgs:
            self.processCanMessages()

        # restore other config items

    def processCanMessages(self, delete=True):
        for msg in self.recvall(CMD_CAN_RECV):
            self._j1939_can_handler(msg, None)

    def setPromiscuous(self, promisc=True):
        '''
        Determines whether messages not destined for an ID I currently own (self._config['myIDs'] are kept/handled or discarded
        '''
        self.promisc = promisc

    def addID(self, newid):
        if newid not in self._config['myIDs']:
            self._config['myIDs'].append(newid)

    def delID(self, curid):
        if curid in self._config['myIDs']:
            self._config['myIDs'].remove(curid)

    def J1939xmit(self, pf, ps, sa, data, prio=6, edp=0, dp=0):
        if len(data) < 8:
            arbid = emitArbid(prio, edp, dp, pf, ps, sa)
            # print("TX: %x : %r" % (arbid, hexlify(data)))
            self.CANxmit(arbid, data, extflag=1)
            return

        self._j1939xmit_tp(pf, ps, sa, data, prio, edp, dp)

    def _j1939xmit_tp(self, pf, ps, sa, message, prio=6, edp=0, dp=0):
        pgn2 = (edp << 1) | dp
        pgn1 = pf
        if pgn1 < 240:
            pgn0 = 0
        else:
            pgn0 = ps

        msgs = ['%c'%(x+1) + message[x*7:(x*7)+7] for x in range((len(message)+6)//7)]
        if len(msgs) > 255:
            raise Exception("J1939xmit_tp: attempt to send message that's too large")

        cm_msg = struct.pack('<BHBBBBB', CM_RTS, len(message), len(msgs), 0xff, 
                pgn2, pgn1, pgn0)

        arbid = emitArbid(prio, edp, dp, PF_TP_CM, ps, sa)
        # print("TXe: %x : %r" % (arbid, hexlify(cm_msg)))
        self.CANxmit(arbid, cm_msg, extflag=1)
        time.sleep(.01)  # hack: should watch for CM_CTS
        for msg in msgs:
            #self.J1939xmit(PF_TP_DT, ps, sa, msg, prio=prio)
            arbid = emitArbid(prio, edp, dp, PF_TP_DT, ps, sa)
            print("TXe: %x : %r" % (arbid, hexlify(msg)))
            self.CANxmit(arbid, msg, extflag=1)

        # hack: should watch for CM_EOM

    def _reprCanMsg(self, idx, ts, arbtup, data, comment=None):
        #print("_reprCanMsg: %r   %r" % (args, kwargs))

        if comment is None:
            comment = ''

        prio, edp, dp, pf, ps, sa = arbtup

        # give name priority to the Handler, then the manual name (this module), then J1939PGNdb
        pfmeaning, handler = pgn_pfs.get(pf, ('',None))
        nextline = ''

        if handler is not None:
            enhanced = handler(idx, ts, arbtup, data, self)
            if enhanced == cancat.DONT_PRINT_THIS_MESSAGE:
                return enhanced

            if enhanced is not None:
                if type(enhanced) in (list, tuple) and len(enhanced):
                    pfmeaning = enhanced[0]
                    if len(enhanced) > 1:
                        nextline = '\n'.join(list(enhanced[1:]))

                    # if we get multiple lines and the first is DONT_PRINT_THIS_MESSAGE, 
                    # then just return nextline
                    if pfmeaning == cancat.DONT_PRINT_THIS_MESSAGE:
                        return nextline

                    nextline = '\n' + nextline

                else:
                    pfmeaning = enhanced

        elif not len(pfmeaning):
            pgndata = parsePGNData(pf, ps, data)
            pfmeaning = pgndata.get('pgndata').get('Name')
            lines = []

            if self.verbose:
                for spnum, spdict, spunit, spdata, sprepr in pgndata.get('spns'):
                    spnName = spdict.get('Name')
                    lines.append('      SPN(%d): %-20s \t %s' % (spnum, sprepr, spnName))

                if len(lines):
                    nextline = '\n' + '\n'.join(lines)

        return "%.8d %8.3f pri/edp/dp: %d/%d/%d, PG: %.2x %.2x  Source: %.2x  Data: %-18s  %s\t\t%s%s" % \
                (idx, ts, prio, edp, dp, pf, ps, sa, hexlify(data), pfmeaning, comment, nextline)

    def _j1939_can_handler(self, tsmsg, none):
        '''
        this function is run for *Every* received CAN message... and is executed from the 
        XMIT/RECV thread.  it *must* be fast!
        '''
        #print(repr(self), repr(cmd), repr(tsmsg))
        ts, message = tsmsg
        arbid, data = self._splitCanMsg(message)
        arbtup = parseArbid(arbid)
        prio, edp, dp, pf, ps, sa = arbtup

        # if i don't care about this message... bail. (0xef+ is multicast)
        if pf < 0xef and ps not in self._config['myIDs'] and not self.promisc:
            return

        if pf == 0xeb:
            self.queueMessageHandlerEvent(self.eb_handler, arbtup, data, ts)
        elif pf == 0xec:
            self.queueMessageHandlerEvent(self.ec_handler, arbtup, data, ts)
        else:
            self.queueMessageHandlerEvent(self._submitJ1939Message, arbtup, data, ts)

        #print("submitted message: %r" % (hexlify(message)))


    def queueMessageHandlerEvent(self, pfhandler, arbtup, data, ts):
        ''' 
        this is run in the XMIT/RECV thread and is intended to handle offloading the data fast
        '''
        self._mhe_queue.put((pfhandler, arbtup, data, ts))

    def _mhe_runner(self):
        ''' 
        runs the mhe thread, which is offloaded so that the message-handling thread can keep going
        '''
        while not self._config.get('shutdown'):
            while self._config['go']:
                worktup = None
                try:
                    worktup = self._mhe_queue.get(1)
                    if worktup is None:
                        continue

                    pfhandler, arbtup, data, ts = worktup
                    pfhandler(arbtup, data, ts)

                except Exception as e:
                    print("(j1939stack)MsgHandler ERROR: %r (%r)" % (e, worktup))
                    if self.verbose:
                        sys.excepthook(*sys.exc_info())

            time.sleep(1)

    def _submitJ1939Message(self, arbtup, message, timestamp=None):
        '''
        submits a message to the cmd mailbox.  creates mbox if doesn't exist.
        *threadsafe*
        often runs in the MHE thread
        '''
        #print("_submitJ1939Message")
        if timestamp is None:
            timestamp = time.time()

        prio, edp, dp, pf, ps, sa = arbtup
        pgn = (pf<<8) | ps
        datarange = (edp<<1) | dp

        if len(self._j1939_filters):
            lcls = locals()
            for advf in self._j1939_filters:
                try:
                    if not eval(advf, lcls):
                        return
                except Exception as e:
                    print("_submitJ1939Message advfilter ERROR: %r" % e)
                    return

        self._j1939queuelock.acquire()
        try:
            # do we want to break things apart into PGN mboxes at this point?  if so, we have to also allow 
            # subscription at this level for things like sniffing.  Like this:
            handled = False
            for listener in self._j1939_msg_listeners:
                try:
                    contnu = listener(arbtup, message)
                    if contnu: 
                        handled = True

                except Exception as e:
                    self.log('_submitJ1939Message: ERROR: %r' % e)
            
            # check for any J1939 registered handlers (using the default system handlers):
            cmdhandler = self._cmdhandlers.get(J1939MSGS)
            if cmdhandler is not None:
                handled2 = cmdhandler(tsmsg, self)

            if handled and handled2:
                #print("handled")
                return

            ##::: TODO, make this a listener.  if at all...
            #dr = self._messages.get(datarange)
            #if dr is None:
                #dr = {}
                #self._messages[datarange] = dr
            #
            ## factor in multicast vs. unicast...
            #mbox = dr.get(pf)
            #if mbox is None:
                #mbox = []
                #dr[pf] = mbox
                #self._j1939_msg_events[pf] = threading.Event()

            # file in the mailbox
            mbox = self._messages.get(J1939MSGS)
            if mbox is None:
                mbox = []
                self._messages[J1939MSGS] = mbox

            msgevt = self._j1939_msg_events.get(J1939MSGS)
            if msgevt is None:
                msgevt = threading.Event()
                self._j1939_msg_events[J1939MSGS] = msgevt

            #mbox.append((pf, ps, sa, edp, dp, prio, timestamp, message))
            mbox.append((timestamp, arbtup, message))
            msgevt.set()
            ##self._j1939_msg_events[pf].set()
            # note: this event will trigger for any of the data ranges, as long as the PF is correct... this may be a problem.
            # FIXME: come back to this...

        except Exception as e:
            self.log("_submitMessage: ERROR: %r" % e, -1)
            if self.verbose:
                sys.excepthook(*sys.exc_info())

        finally:
            self._j1939queuelock.release()

    def getJ1939MsgCount(self):
        j1939Msgs = self._messages.get(J1939MSGS)
        if j1939Msgs is None:
            return 0
        return len(j1939Msgs)

    def subscribe(self, msg_handler):
        if msg_handler not in self._j1939_msg_listeners:
            self._j1939_msg_listeners.append(msg_handler)

    def unsubscribe(self, msg_handler):
        if msg_handler in self._j1939_msg_listeners:
            self._j1939_msg_listeners.remove(msg_handler)

    def ec_handler(j1939, arbtup, data, ts):
        '''
        special handler for TP_CM messages

        pgn2 is PS/DA
        pgn1 is PF
        pgn0 is prio/edp/dp
        '''
        def tp_cm_10(arbtup, data, j1939):     # RTS
            (prio, edp, dp, pf, da, sa) = arbtup

            (cb, totsize, pktct, maxct,
                    pgn2, pgn1, pgn0) = struct.unpack('<BHBBBBB', data)
            
            # check for old stuff
            extmsgs = j1939.getTPmsgParts(da, sa)
            if extmsgs is not None and len(extmsgs['msgs']):
                pgn2 = extmsgs['pgn2']
                pgn1 = extmsgs['pgn1']
                pgn0 = extmsgs['pgn0']
                j1939.saveTPmsg(da, sa, (pgn2, pgn1, pgn0), meldExtMsgs(extmsgs), TP_DIRECT_BROKEN)
                j1939.clearTPmsgParts(da, sa)

            # store extended message information for other stuff...
            extmsgs = j1939.getTPmsgParts(da, sa, create=True)
            extmsgs['ts'] = ts
            extmsgs['sa'] = sa
            extmsgs['da'] = da
            extmsgs['pgn2'] = pgn2
            extmsgs['pgn1'] = pgn1
            extmsgs['pgn0'] = pgn0
            extmsgs['maxct'] = maxct
            extmsgs['length'] = pktct
            extmsgs['totsize'] = totsize
            extmsgs['type'] = TP_DIRECT
            extmsgs['adminmsgs'].append((arbtup, data))

            # RESPOND!
            if da in j1939._config['myIDs']:
                response = struct.pack('<BBBHBBB', CM_CTS, pktct, 1, 0, pgn2, pgn1, pgn0)
                j1939.J1939xmit(0xec, sa, da, response, prio)

        def tp_cm_11(arbtup, data, j1939):     # CTS
            (prio, edp, dp, pf, da, sa) = arbtup

            (cb, maxpkts, nextpkt, reserved,
                    pgn2, pgn1, pgn0) = struct.unpack('<BBBHBBB', data)

            # store extended message information for other stuff...
            extmsgs = j1939.getTPmsgParts(da, sa)
            if extmsgs is None:
                return

            extmsgs['adminmsgs'].append((arbtup, data))

            # SOMEHOW WE TRIGGER THE CONTINUATION OF TRANSMISSION

        def tp_cm_13(arbtup, data, j1939):     # EOM
            (prio, edp, dp, pf, da, sa) = arbtup

            (cb, totsize, pktct, maxct,
                    pgn2, pgn1, pgn0) = struct.unpack('<BHBBBBB', data)

            # print(out extended message and clear the buffers.)
            extmsgs = j1939.getTPmsgParts(da, sa)
            if extmsgs is None:
                return 

            extmsgs['adminmsgs'].append((arbtup, data))

            j1939.clearTPmsgParts(da, sa)
            # Coolio, they just confirmed receipt, we're done!
            # Probably need to trigger some mechanism telling the originator

        def tp_cm_20(arbtup, data, j1939):     # BROADCAST MESSAGE (BAM)
            (prio, edp, dp, pf, da, sa) = arbtup

            (cb, totsize, pktct, reserved,
                    pgn2, pgn1, pgn0) = struct.unpack('<BHBBBBB', data)

            # check for old stuff
            extmsgs = j1939.getTPmsgParts(da, sa)
            if extmsgs is not None and len(extmsgs['msgs']):
                pgn2 = extmsgs['pgn2']
                pgn1 = extmsgs['pgn1']
                pgn0 = extmsgs['pgn0']
                j1939.saveTPmsg(da, sa, (pgn2, pgn1, pgn0), meldExtMsgs(extmsgs), TP_DIRECT_BROKEN)

                j1939.clearTPmsgParts(da, sa)

            # store extended message information for other stuff...
            extmsgs = j1939.getTPmsgParts(da, sa, create=True)
            extmsgs['ts'] = ts
            extmsgs['sa'] = sa
            extmsgs['da'] = da
            extmsgs['pgn2'] = pgn2
            extmsgs['pgn1'] = pgn1
            extmsgs['pgn0'] = pgn0
            extmsgs['maxct'] = 0
            extmsgs['length'] = pktct
            extmsgs['totsize'] = totsize
            extmsgs['type'] = TP_BAM
            extmsgs['adminmsgs'].append((arbtup, data))

        # call the right TP_CM handler
        tp_cm_handlers = {
                CM_RTS:     ('RTS',           tp_cm_10),
                CM_CTS:     ('CTS',           tp_cm_11),
                CM_EOM:     ('EndOfMsgACK',   tp_cm_13),
                CM_BAM:     ('BAM-Broadcast', tp_cm_20),
                CM_ABORT:   ('Abort',         None),
                }

        cb = data[0]
        #print("ec: %.2x%.2x %.2x" % (arbtup[3], arbtup[4], cb))

        htup = tp_cm_handlers.get(cb)
        if htup is not None:
            subname, cb_handler = htup

            if cb_handler is not None:
                cb_handler(arbtup, data, j1939)

    def eb_handler(j1939, arbtup, data, ts):
        '''
        special handler for TP_DT messages
        '''
        (prio, edp, dp, pf, da, sa) = arbtup
        if len(data) < 1:
            j1939.log('pf=0xeb: TP ERROR: NO DATA!')
            return

        extmsgs = j1939.getTPmsgParts(da, sa)
        if extmsgs is None:
            j1939.log("TP_DT: haven't received TP_CM control setup, skipping")
            return

        extmsgs['msgs'].append((arbtup, data))
        if len(extmsgs['msgs']) >= extmsgs['length']:
            # we're done building this message, submit it!
            #print("eb_handler: saving: %r %r" % (len(extmsgs['msgs']) , extmsgs['length']))
            pgn2 = extmsgs['pgn2']
            pgn1 = extmsgs['pgn1']
            pgn0 = extmsgs['pgn0']
            mtype = extmsgs['type']

            j1939.saveTPmsg(da, sa, (pgn2, pgn1, pgn0), meldExtMsgs(extmsgs), mtype)
            j1939.clearTPmsgParts(da, sa)

            # if this is the end of a message to *me*, reply accordingly
            if da in j1939._config['myIDs']:
                if mtype is None:
                    j1939.log("TP_DT_handler: missed beginning of message, not sending EOM: %r" % \
                            repr(extmsgs), 1)
                    return

                j1939.log("tp_stack: sending EOM  extmsgs: %r" % extmsgs, 1)
                pgn2 = extmsgs['pgn2']
                pgn1 = extmsgs['pgn1']
                pgn0 = extmsgs['pgn0']
                totsize = extmsgs['totsize']
                maxct = extmsgs['maxct']
                pktct = extmsgs['length']

                data = struct.pack(b'<BHBBBBB', CM_EOM, totsize, pktct, maxct, pgn2, pgn1, pgn0)
                j1939.J1939xmit(PF_TP_CM, sa, da,  data, prio=prio)

    # functions to support the J1939TP Stack (real stuff, not just repr)
    '''
    these functions support TP messaging.  Message parts are stored as PF lists within DA dicts within SA dicts.
    ie.:
        self_TPmsgParts[sa][da][pf]

    this allows for clearing of entire parts of the transient stack easily by SA.
    The main message stack has a *different* hierarchy based on what's easiest for developing client code to access.
    '''
    def getTPmsgParts(self, da, sa, create=False):
        '''
        # functions to support the J1939TP Stack (real stuff, not just repr)
        returns a message list for a given source and destination (sa, da)

        if no list exists for this pairing, one is created and an empty list is returned
        '''
        msglists = self._TPmsgParts.get(sa)
        if msglists is None:
            msglists = {}
            self._TPmsgParts[sa] = msglists

        mlist = msglists.get(da)
        if mlist is None and create:
            # create something new
            mlist = {'length':0, 
                    'msgs':[], 
                    'type':None, 
                    'adminmsgs':[], 
                    'pgn0':None, 
                    'pgn1':None, 
                    'pgn2':None,   
                    'totsize':0,
                    'maxct':0xff,
                    'sa' : sa,
                    'da' : da,
                    }
            msglists[da] = mlist

        return mlist

    def clearTPmsgParts(self, da, sa):
        '''
        # functions to support the J1939TP Stack (real stuff, not just repr)
        clear out extended messages metadata.

        if da is None, this clears *all* message data for a given source address

        returns whether the thing deleted exists previously
        * if da is None, returns whether the sa had anything previously
        * otherwise, if the list 
        '''
        exists = False
        if da is None:
            msglists = self._TPmsgParts.get(sa)
            exists = bool(msglists is not None and len(msglists))
            self._TPmsgParts[sa] = {}
            return exists

        msglists = self._TPmsgParts.get(sa)
        if msglists is None:
            msglists = {}
            self._TPmsgParts[sa] = msglists

        if da in msglists:
            msglists.pop(da)
            return True

        return False

    def saveTPmsg(self, da, sa, pgn, msg, tptype):
        '''
        # functions to support the J1939TP Stack (real stuff, not just repr)
        store a TP message.
        '''
        pgn2, pgn1, pgn0 = pgn

        ps = pgn2
        pf = pgn1

        prio = pgn0 >> 2
        edp = (pgn0 >> 1) & 1
        dp = pgn0 & 1

        if da != ps and self.verbose:
            print("saveTPmsg: WARNING: da: 0x%x  but ps: 0x%x.  using ps" % (da, ps))
            print(da, sa, pgn, repr(msg))
        arbtup = prio, edp, dp, pf, ps, sa
        self._submitJ1939Message(arbtup, msg)

    def _getLocals(self, idx, ts, arbtup, data):
        #print("getLocals:",idx, ts, arbtup, data)
        prio, edp, dp, pf, ps, sa = arbtup
        pgn = (pf << 8) | ps
        lcls = {'idx': idx,
                'ts': ts,
                'data': data,
                'priority': prio,
                'edp': edp,
                'dp': dp,
                'pf': pf,
                'ps': ps,
                'sa': sa,
                'pgn': pgn,
                'da': ps,
                'ge': ps,
                }

        return lcls

    def genCanMsgs(self, start=0, stop=None, arbids=None, tail=False, maxsecs=None):
        '''
        CAN message generator.  takes in start/stop indexes as well as a list
        of desired arbids (list)

        maxsecs limits the number of seconds this generator will go for.  it's intended
        for use with tail
        '''

        messages = self.getCanMsgQueue()
        if messages is None and not tail:
            return

        # get the ts of the first received message
        if messages is not None and len(messages):
            startts = messages[0][0]
        else:
            startts = time.time()

        if start is None:
            start = self.getJ1939MsgCount()

        if stop is None or tail:
            stop = len(messages)
        else:
            stop = stop + 1 # This makes the stop index inclusive if specified

        starttime = time.time()

        idx = start
        while tail or idx < stop:
            # obey our time restrictions
            # placed here to ensure checking whether we're receiving messages or not
            if maxsecs is not None and time.time() > maxsecs+starttime:
                return
        
            # If we start sniffing before we receive any messages, 
            # messages will be "None". In this case, each time through
            # this loop, check to see if we have messages, and if so,
            # re-create the messages handle
            if messages is None:
                messages = self.getCanMsgQueue()
        
            # if we're off the end of the original request, and "tailing"
            if tail and idx >= stop:
                msgqlen = len(messages) 
                self.log("stop=%d  len=%d" % (stop, msgqlen), 3)

                if stop == msgqlen:
                    self.log("waiting for messages", 3)
                    # wait for trigger event so we're not constantly polling
                    self._msg_events[self._msg_source_idx].wait(1)
                    self._msg_events[self._msg_source_idx].clear()
                    self.log("received 'new messages' event trigger", 3)

                # we've gained some messages since last check...
                stop = len(messages)
                continue    # to the big message loop.

            # now actually handle messages
            # here's where we get J1939 specific...
            #print(messages[idx])
            ts, arbtup, data = messages[idx]
            #datatup = self._splitCanMsg(msg)

            # make ts an offset instead of the real time.
            ts -= startts

            #if arbids is not None and arbid not in arbids:
            #    # allow filtering of arbids
            #    idx += 1
            #    continue

            yield((idx, ts, arbtup, data))
            idx += 1


    def J1939recv(self, pf, ps, sa, msgcount=1, timeout=1, start_msg=None, update_last_recv=True):
        out = []

        if start_msg is None:
            start_msg = self._last_recv_idx

        #for msg in self.filterCanMsgs(start_msg=start_msg, advfilters=advfilters, tail=True, maxsecs=timeout):
            #(idx, ts, arbid, data) = msg
            #out.append(msg)
            #self._last_recv_idx = msg[0]
        # FIXME: add in the wait/set interaction for lower perf impact.
        startts = time.time()
        cur = start_msg
        mque = self._messages[J1939MSGS]
        while time.time() < (startts + timeout):
            if cur >= len(mque):
                time.sleep(.001)
                continue

            ts, arbtup, msg = mque[cur]
            cur += 1
           
            # we have a message now, does the PGN match?
            mprio, medp, mdp, mpf, mps, msa = arbtup
            if mpf != pf or mps != ps or msa != sa:
                continue

            # it's passed the checks... add it to the queue
            out.append((ts, arbtup, msg))

            if len(out) >= msgcount:
                break


        # if we actually found something, and we wanted to update last recvd...
        if len(out) and update_last_recv:
            self._last_recv_idx = cur

        return out
    def J1939recv_loose(self, pf=(), ps=None, sa=None, msgcount=1, timeout=1, start_msg=None, update_last_recv=True):
        out = []

        if start_msg is None:
            start_msg = self._last_recv_idx

        #for msg in self.filterCanMsgs(start_msg=start_msg, advfilters=advfilters, tail=True, maxsecs=timeout):
            #(idx, ts, arbid, data) = msg
            #out.append(msg)
            #self._last_recv_idx = msg[0]
        # FIXME: add in the wait/set interaction for lower perf impact.
        startts = time.time()
        cur = start_msg
        mque = self._messages[J1939MSGS]
        while time.time() < (startts + timeout):
            if cur >= len(mque):
                time.sleep(.001)
                continue

            ts, arbtup, msg = mque[cur]
            cur += 1
           
            # we have a message now, does the PGN match? (loose matching)
            mprio, medp, mdp, mpf, mps, msa = arbtup
            if pf is not None:
                if type(pf) in (tuple, list):
                    if mpf not in pf:
                        continue
                else:
                    if mpf != pf:
                        continue

            if ps is not None:
                if type(ps) in (tuple, list):
                    if mps not in ps:
                        continue
                else:
                    if mps != ps:
                        continue

            if sa is not None:
                if type(sa) in (tuple, list):
                    if msa not in sa:
                        continue
                else:
                    if msa != sa:
                        continue

            # it's passed the checks... add it to the queue
            out.append((ts, arbtup, msg))

            if len(out) >= msgcount:
                break


        # if we actually found something, and we wanted to update last recvd...
        if len(out) and update_last_recv:
            self._last_recv_idx = cur

        return out

    def J1939xmit_recv(self, pf, ps, sa, data, recv_count=1, prio=6, edp=0, dp=0, timeout=1, expected_pf=None):
        msgidx = self.getCanMsgCount()
        # FIXME: filter on the expected response PGN
        if expected_pf is None:
            expected_pf = pf

        res = self.J1939xmit(pf, ps, sa, data, prio, edp, dp)
        res = self.J1939recv(expected_pf, sa, ps, recv_count, timeout, start_msg=msgidx)

        return res


    def J1939_Request(self, rpf, rda_ge=0, redp=0, rdp=0, da=0xff, sa=0xfe, prio=0x6, recv_count=255, timeout=2, expected_pf=None):
        pgnbytes = [rda_ge, rpf, redp<<1 | rdp]
        data = ''.join([chr(x) for x in pgnbytes])
        data += '\xff' * (8-len(data))

        if expected_pf is None:
            expected_pf = rpf

        self.J1939xmit(PF_RQST, da, sa, data)
        msgs = self.J1939recv_loose(pf=expected_pf, msgcount=10, timeout=timeout)
        return msgs

    def J1939_ClaimAddress(self, addr, name=0x4040404040404040, prio=6):
        data = struct.pack(">Q", name)
        out = self.J1939xmit_recv(pf=PF_ADDRCLAIM, ps=0xff, sa=addr, data=data, recv_count=10, prio=prio<<2, timeout=2, expected_pf=0xee)
        self.addID(addr)
        return out

    def J1939_ArpAddresses(self):
        '''
        Sends a request for all used addresses... not fully tested
        '''
        #idx = self.getCanMsgCount()
        msgs = self.J1939_Request(PF_ADDRCLAIM, recv_count=255, timeout=3)

        '''
        # FIXME: these are way too loose, for discovery only. tighten down.
        recv_filters = [
                'pf < 0xf0',
                #'pf == 0xee',
                ]

        msgs = self.J1939recv(msgcount=200, timeout=3, advfilters=recv_filters, start_msg=idx)
        '''
        for msg in msgs:
            try:
                msgrepr = self._reprCanMsg(*msg)
                if msgrepr != cancat.DONT_PRINT_THIS_MESSAGE:
                    print(msgrepr)
            except Exception as e:
                print(e)
        '''
        example (from start of ECU):
        00000000 1545142410.990 pri/edp/dp: 6/0/0, PG: ea ff  Source: fe  Len: 03, Data: 00ee00              Request
        00000001 1545142411.077 pri/edp/dp: 6/0/0, PG: ee ff  Source: 00  Len: 08, Data: 4cca4d0100000000    Address Claim: id: 0xdca4c mfg: Cummins Inc (formerly Cummins Engine Co) Columbus, IN USA
    
        currently ours:
        00001903 1545142785.127 pri/edp/dp: 6/0/0, PG: ea ff  Source: fe  Len: 03, Data: 00ee00              Request

        '''

MAX_WORD = 64
bu_masks = [(2 ** (i)) - 1 for i in range(8*MAX_WORD+1)]

def parsePGNData(pf, ps, msg):

    # piece the correct PGN together from PF/PS
    if pf < 0xec:
        pgn = pf << 8
    else:
        pgn = (pf << 8) | ps

    # grab the PGN data
    res = J1939PGNdb.get(pgn)
    out = {'pgn': pgn, 'pgndata': res}

    spnlist = res.get('SPNs')
    spndata = []

    var_len_idx = 0
    for spnum in spnlist:
        # get SPN data
        spn = J1939SPNdb.get(spnum)
        if spn is None:
            continue

        # graciously refactored code from TruckDevil (hey LBD!)
        spnlen = spn.get('SPNLength')
        pgnlen = spn.get('PGNLength')
        spnName = spn.get('Name')
        spnRepr = ''
        datanum = -1
        units = spn.get("Units")

        # skip variable-length PGNs for now
        if (type(pgnlen) == str and 'ariable' in pgnlen):
            datablob = msg
            endBit = endBitO = startByte = startBitO = startBit = 0

        else:       # FIXME: Rework this section
            startBit = spn.get('StartBit')
            endBit = spn.get('EndBit')

            startByte = startBit // 8
            startBitO = startBit % 8
            endByte = (endBit + 7) // 8
            endBitO = endBit % 8

            datablob = msg[startByte:endByte]

        #print("sb: %d\t eb: %d\t sB:%d\t SBO:%d\t eB:%d\t eBO:%d\t %r" % (startBit, endBit, startByte, startBitO, endByte, endBitO, datablob))

        if units == 'ASCII':
            spnRepr = repr(datablob)
            datanum = datablob

        else:
            try:
                # carve out the number
                datanum = 0
                datafloat = 0.0
                numbytes = struct.unpack('%dB' % len(datablob), datablob)
                for i, n in enumerate(numbytes):
                    datanum |= (n << (8*i))
                    #print("datanum (working): 0x%x   ::  0x%x" % (n, datanum))
                    #datanum <<= 8

                datanum >>= (7 - endBitO)
                #print("datanum: %x" % datanum)

                mask = bu_masks[endBit - startBit + 1]
                datanum &= mask
                #print("datanum(2): %x" % datanum)

                offset = spn.get('Offset')
                if offset is not None:
                    datanum += int(offset)
                    datafloat += offset
                #print("datanum: %x (mask: %x)" % (datanum, mask))

                # make sense of the number based on units
                if units == 'bit':
                    meaning = ''
                    bitdecode = J1939BitDecodings.get(spnum)
                    if bitdecode is not None:
                        meaning = bitdecode.get(datanum)

                    spnRepr = '0x%x (%s)' % (datanum, meaning)

                elif units == 'binary':
                    spnRepr = "%s (%x)" % (bin(int(datanum)), datanum)

                elif units == '%':
                    spnRepr = "%d%%" % datanum

                else:
                    # some other unit with a resolution
                    resolution = spn.get('Resolution')
                    if resolution is not None:
                        datanum *= resolution

                    spnRepr = '%.3f %s' % (datafloat, units)

            except Exception as e:
                spnRepr = "ERROR"
                print("SPN: %r %r (%r)" % (e, msg, spn))
                traceback.print_exc()

        spndata.append((spnum, spn, units, datanum, spnRepr))

    out['spns'] = spndata
    return out

