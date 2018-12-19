import cancat
import struct
from J1939db import *
from J1939namedb import *
from cancat import *

import vstruct
from vstruct.bitfield import *

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


def reprExtMsgs(msgs):
    out = ['Ext Msg: %.2x->%.2x' % (msgs['sa'], msgs['da'])]
    for arbtup, msg in msgs.get('msgs'):
        out.append(msg.encode('hex'))

    return ' '.join(out)

def meldExtMsgs(msgs):
    out = []
    for arbtup, msg in msgs.get('msgs'):
        out.append(msg)

    return ''.join(out)

### renderers for specific PF numbers
def pf_c9(arbtup, data, j1939):
    b4 = data[3]
    req = "%.2x %.2x %.2x" % ([ord(d) for d in data[:3]])
    usexferpfn = ('', 'Use_Transfer_PGN', 'undef', 'NA')[b4 & 3]
    
    return "Request2: %s %s" % (req,  usexferpgn)

def pf_eb(arbtup, data, j1939):
    (prio, edp, dp, pf, da, sa) = arbtup
    if len(data) < 1:
        return 'TP ERROR: NO DATA!'

    idx = ord(data[0])

    msgdata = ''
    extmsgs = j1939.getExtMsgs(sa, da)
    extmsgs['msgs'].append((arbtup, data))
    if len(extmsgs['msgs']) >= extmsgs['length']:
        if extmsgs['type'] == 'BAM':
            j1939.clearExtMsgs(sa, da)
            msgdata = '\n\t%s\n' % reprExtMsgs(extmsgs)
            # FIXME: do both here??

    if j1939.skip_TPDT and not len(msgdata):
        #print "pf_eb: DONT_PRINT_THIS_MESSAGE"
        return cancat.DONT_PRINT_THIS_MESSAGE 

    if len(extmsgs['msgs']) > extmsgs['length']:
            #print "ERROR: too many messages in Extended Message between %.2x -> %.2x\n\t%r" % (sa, da, extmsgs['msgs'])
            pass

    return 'TP.DT idx: %.x%s' % (idx, msgdata)

def pf_ec(arbtup, data, j1939):
    def tp_cm_10(arbtup, data, j1939):
        (prio, edp, dp, pf, da, sa) = arbtup

        (cb, totsize, pktct, maxct,
                pgn2, pgn1, pgn0) = struct.unpack('<BHBBBBB', data)
        
        # check for old stuff
        prefix = ''
        extmsgs = j1939.getExtMsgs(sa, da)
        if len(extmsgs['msgs']):
            extmsgs['sa'] = sa
            extmsgs['da'] = da
            prefix = " new TP message, without closure...: \n\t%r\n" % reprExtMsgs(extmsgs)

        j1939.clearExtMsgs(sa, da)

        # store extended message information for other stuff...
        extmsgs = j1939.getExtMsgs(sa, da)
        extmsgs['sa'] = sa
        extmsgs['da'] = da
        extmsgs['pgn2'] = pgn2
        extmsgs['pgn1'] = pgn1
        extmsgs['pgn0'] = pgn0
        extmsgs['length'] = pktct
        extmsgs['totsize'] = totsize
        extmsgs['type'] = 'direct'
        extmsgs['adminmsgs'].append((arbtup, data))

        return prefix + 'TP.CM_RTS size:%.2x pktct:%.2x maxpkt:%.2x PGN: %.2x%.2x%.2x' % \
                (totsize, pktct, maxct, pgn2, pgn1, pgn0)

    def tp_cm_11(arbtup, data, j1939):
        (prio, edp, dp, pf, da, sa) = arbtup

        (cb, maxpkts, nextpkt, reserved,
                pgn2, pgn1, pgn0) = struct.unpack('<BBBHBBB', data)

        # store extended message information for other stuff...
        extmsgs = j1939.getExtMsgs(sa, da)
        extmsgs['adminmsgs'].append((arbtup, data))

        return 'TP.CM_CTS        maxpkt:%.2x nxtpkt:%.2x PGN: %.2x%.2x%.2x' % \
                (maxpkts, nextpkt, pgn2, pgn1, pgn0)

    def tp_cm_13(arbtup, data, j1939):
        (prio, edp, dp, pf, da, sa) = arbtup

        (cb, totsize, pktct, maxct,
                pgn2, pgn1, pgn0) = struct.unpack('<BHBBBBB', data)

        # print out extended message and clear the buffers.
        extmsgs = j1939.getExtMsgs(sa, da)
        extmsgs['adminmsgs'].append((arbtup, data))

        j1939.clearExtMsgs(sa, da)
        msgdata = reprExtMsgs(extmsgs)

        return 'TP.EndOfMsgACK PGN: %.2x%.2x%.2x\n\t%r' % \
                (pgn2, pgn1, pgn0, msgdata)

    def tp_cm_20(arbtup, data, j1939):
        (prio, edp, dp, pf, da, sa) = arbtup

        (cb, totsize, pktct, reserved,
                pgn2, pgn1, pgn0) = struct.unpack('<BHBBBBB', data)

        # check for old stuff
        prefix=''
        extmsgs = j1939.getExtMsgs(sa, da)
        if len(extmsgs['msgs']):
            extmsgs['sa'] = sa
            extmsgs['da'] = da
            prefix = " new TP message, without closure...: \n\t%r\n" % reprExtMsgs(extmsgs)

        j1939.clearExtMsgs(sa, da)

        # store extended message information for other stuff...
        extmsgs = j1939.getExtMsgs(sa, da)
        extmsgs['sa'] = sa
        extmsgs['da'] = da
        extmsgs['length'] = pktct
        extmsgs['type'] = 'BAM'
        extmsgs['adminmsgs'].append((arbtup, data))

        return prefix + 'TP.CM_BAM-Broadcast size:%.2x pktct:%.2x PGN: %.2x%.2x%.2x' % \
                (totsize, pktct, pgn2, pgn1, pgn0)

    tp_cm_handlers = {
            CM_RTS:     ('RTS',           tp_cm_10),
            CM_CTS:     ('CTS',           tp_cm_11),
            CM_EOM:     ('EndOfMsgACK',   None),
            CM_BAM:     ('BAM-Broadcast', tp_cm_20),
            CM_ABORT:   ('Abort',         None),
            }

    cb = ord(data[0])

    htup = tp_cm_handlers.get(cb)
    if htup != None:
        subname, cb_handler = htup

        if cb_handler == None:
            return 'TP.CM_%s' % subname

        newmsg = cb_handler(arbtup, data, j1939)
        if newmsg == None:
            return 'TP.CM_%s' % subname

        return newmsg

    return 'TP.CM_%.2x' % cb

def pf_ee((prio, edp, dp, pf, ps, sa), data, j1939):
    if ps == 255 and sa == 254:
        return 'CANNOT CLAIM ADDRESS'
    
    addrinfo = parseName(data).minrepr()
    return "Address Claim: %s" % addrinfo

def pf_ef((prio, edp, dp, pf, ps, sa), data, j1939):
    if dp:
        return 'Proprietary A2'

    return 'Proprietary A1'
    
def pf_ff((prio, edp, dp, pf, ps, sa), data, j1939):
    pgn = "%.2x :: %.2x:%.2x - %s" % (sa, pf,ps, data.encode('hex'))
    return "Proprietary B %s" % pgn

pgn_pfs = {
        0x93:   ("Name Management", None),
        0xc9:   ("Request2",        pf_c9),
        0xca:   ('Transfer',        None),
        0xe8:   ("ACK        ",     None),
        0xea:   ("Request      ",   None),
        0xeb:   ("TP.DT",           pf_eb),
        0xec:   ("TP.CM",           pf_ec),
        0xee:   ("Address Claim",   pf_ee),
        0xef:   ("Proprietary",     pf_ef),
        #0xfe:   ("Command Address", None),
        0xff:   ("Proprietary B",   pf_ff),
        }

def parseArbid(arbid):
    (prioPlus,
        pf,
        ps,
        sa) = struct.unpack('BBBB', struct.pack(">I", arbid))

    prio = prioPlus >> 2
    edp = (prioPlus >> 1) & 1
    dp = prioPlus & 1

    return prio, edp, dp, pf, ps, sa

def emitArbid(prio, edp, dp, pf, ps, sa):
    prioPlus = prio<<2 | (edp<<1) | dp
    return struct.unpack(">I", struct.pack('BBBB', prioPlus, pf, ps, sa))[0]


def ec_handler(j1939, idx, ts, arbtup, data):
    def tp_cm_10(arbtup, data, j1939, idx, ts):
        (prio, edp, dp, pf, da, sa) = arbtup

        (cb, totsize, pktct, maxct,
                pgn2, pgn1, pgn0) = struct.unpack('<BHBBBBB', data)
        
        # check for old stuff
        extmsgs = j1939.getRealExtMsgs(sa, da)  # HAVE TO MAKE THIS SEPARATE FROM reprCanMsgs!
        if len(extmsgs['msgs']):
            extmsgs['sa'] = sa
            extmsgs['da'] = da
            j1939.saveRealExtMsg(idx, ts, sa, da, meldExtMsgs(extmsgs), TP_DIRECT_BROKEN)

        j1939.clearRealExtMsgs(sa, da)

        # store extended message information for other stuff...
        extmsgs = j1939.getRealExtMsgs(sa, da)
        extmsgs['sa'] = sa
        extmsgs['da'] = da
        extmsgs['pgn2'] = pgn2
        extmsgs['pgn1'] = pgn1
        extmsgs['pgn0'] = pgn0
        extmsgs['maxct'] = maxct
        extmsgs['length'] = pktct
        extmsgs['totsize'] = totsize
        extmsgs['type'] = 'direct'
        extmsgs['adminmsgs'].append((arbtup, data))

        # RESPOND!
        if da in j1939.myIDs:
            response = struct.pack('<BBBHBBB', CM_CTS, pktct, 1, 0, pgn2, pgn1, pgn0)
            j1939.J1939xmit(0xec, sa, da, response, prio)

    def tp_cm_11(arbtup, data, j1939, idx, ts):
        (prio, edp, dp, pf, da, sa) = arbtup

        (cb, maxpkts, nextpkt, reserved,
                pgn2, pgn1, pgn0) = struct.unpack('<BBBHBBB', data)

        # store extended message information for other stuff...
        extmsgs = j1939.getRealExtMsgs(sa, da)
        extmsgs['adminmsgs'].append((arbtup, data))

        # SOMEHOW WE TRIGGER THE CONTINUAITON OF TRANSMISSION

    def tp_cm_13(arbtup, data, j1939, idx, ts):
        (prio, edp, dp, pf, da, sa) = arbtup

        (cb, totsize, pktct, maxct,
                pgn2, pgn1, pgn0) = struct.unpack('<BHBBBBB', data)

        # print out extended message and clear the buffers.
        extmsgs = j1939.getRealExtMsgs(sa, da)
        extmsgs['adminmsgs'].append((arbtup, data))

        j1939.clearRealExtMsgs(sa, da)
        # Coolio, they just confirmed receipt, we're done!
        # Probably need to trigger some mechanism telling the originator

    def tp_cm_20(arbtup, data, j1939, idx, ts):
        (prio, edp, dp, pf, da, sa) = arbtup

        (cb, totsize, pktct, reserved,
                pgn2, pgn1, pgn0) = struct.unpack('<BHBBBBB', data)

        # check for old stuff
        extmsgs = j1939.getRealExtMsgs(sa, da)
        if len(extmsgs['msgs']):
            extmsgs['sa'] = sa
            extmsgs['da'] = da
            j1939.saveRealExtMsg(idx, ts, sa, da, meldExtMsgs(extmsgs), TP_DIRECT_BROKEN)

        j1939.clearRealExtMsgs(sa, da)

        # store extended message information for other stuff...
        extmsgs = j1939.getRealExtMsgs(sa, da)
        extmsgs['sa'] = sa
        extmsgs['da'] = da
        extmsgs['length'] = pktct
        extmsgs['type'] = 'BAM'
        extmsgs['adminmsgs'].append((arbtup, data))

    tp_cm_handlers = {
            CM_RTS:     ('RTS',           tp_cm_10),
            CM_CTS:     ('CTS',           tp_cm_11),
            CM_EOM:     ('EndOfMsgACK',   tp_cm_13),
            CM_BAM:     ('BAM-Broadcast', tp_cm_20),
            CM_ABORT:   ('Abort',         None),
            }

    cb = ord(data[0])
    #print "ec: %.2x%.2x %.2x" % (arbtup[3], arbtup[4], cb)

    htup = tp_cm_handlers.get(cb)
    if htup != None:
        subname, cb_handler = htup

        if cb_handler != None:
            cb_handler(arbtup, data, j1939, idx, ts)

def eb_handler(j1939, idx, ts, arbtup, data):
    (prio, edp, dp, pf, da, sa) = arbtup
    if len(data) < 1:
        j1939.log('pf=0xeb: TP ERROR: NO DATA!')
        return

    idx = ord(data[0])

    extmsgs = j1939.getRealExtMsgs(sa, da)
    extmsgs['msgs'].append((arbtup, data))
    if len(extmsgs['msgs']) >= extmsgs['length']:
        #print "eb_handler: saving: %r %r" % (len(extmsgs['msgs']) , extmsgs['length'])
        j1939.saveRealExtMsg(idx, ts, sa, da, meldExtMsgs(extmsgs), TP_BAM)
        j1939.clearRealExtMsgs(sa, da)

        # if this is the end of a message to *me*, reply accordingly
        if da in j1939.myIDs:
            print "responding...  extmsgs: %r" % extmsgs
            pgn2 = extmsgs['pgn2']
            pgn1 = extmsgs['pgn1']
            pgn0 = extmsgs['pgn0']
            totsize = extmsgs['totsize']
            maxct = extmsgs['maxct']
            pktct = extmsgs['length']
            data = struct.pack('<BHBBBBB', CM_EOM, totsize, pktct, maxct, pgn2, pgn1, pgn0)
            j1939.J1939xmit(PF_TP_CM, sa, da,  data, prio=prio)

pfhandlers = {
        PF_TP_CM : ec_handler,
        PF_TP_DT : eb_handler,
        }
TP_BAM = 20
TP_DIRECT = 10
TP_DIRECT_BROKEN=9

class J1939(cancat.CanInterface):
    def __init__(self, port=serialdev, baud=baud, verbose=False, cmdhandlers=None, comment='', load_filename=None, orig_iface=None):
        self.myIDs = []
        self.extMsgs = {}
        self._RealExtMsgs = {}
        self._RealExtMsgParts = {}
        self.skip_TPDT = False

        CanInterface.__init__(self, port=port, baud=baud, verbose=verbose, cmdhandlers=cmdhandlers, comment=comment, load_filename=load_filename, orig_iface=orig_iface)

        self.register_handler(CMD_CAN_RECV, self._j1939_can_handler)

    def _reprCanMsg(self, idx, ts, arbid, data, comment=None):
        if comment == None:
            comment = ''

        arbtup = parseArbid(arbid)
        prio, edp, dp, pf, ps, sa = arbtup

        # give name priority to the Handler, then the manual name (this module), then J1939PGNdb
        pfmeaning, handler = pgn_pfs.get(pf, ('',None))

        if handler != None:
            enhanced = handler(arbtup, data, self)
            if enhanced == cancat.DONT_PRINT_THIS_MESSAGE:
                #print "_reprCanMsg: DONT_PRINT_THIS_MESSAGE"
                return enhanced

            if enhanced != None:
                pfmeaning = enhanced

        elif not len(pfmeaning):
            pgn = (pf<<8) | ps
            res = J1939PGNdb.get(pgn)
            if res == None:
                res = J1939PGNdb.get(pf<<8)
            if res != None:
                pfmeaning = res.get("Name")

        return "%.8d %8.3f pri/edp/dp: %d/%d/%d, PG: %.2x %.2x  Source: %.2x  Data: %-18s  %s\t\t%s" % \
                (idx, ts, prio, edp, dp, pf, ps, sa, data.encode('hex'), pfmeaning, comment)


    def _getLocals(self, idx, ts, arbid, data):
        prio, edp, dp, pf, ps, sa = parseArbid(arbid)
        pgn = (pf<<8) | ps
        lcls = {'idx':idx, 'ts':ts, 'arbid':arbid, 'data':data, 'priority':prio, 'edp':edp, 'dp':dp, 'pf':pf, 'ps':ps, 'sa':sa, 'pgn':pgn}

        return lcls

    def _j1939_can_handler(self, message, none):
        #print repr(self), repr(cmd), repr(message)
        arbid, data = self._splitCanMsg(message)
        idx, ts = self._submitMessage(CMD_CAN_RECV, message)

        arbtup = parseArbid(arbid)
        prio, edp, dp, pf, ps, sa = arbtup

        pfhandler = pfhandlers.get(pf)
        if pfhandler != None:
            pfhandler(self, idx, ts, arbtup, data)

        #print "submitted message: %r" % (message.encode('hex'))


    # functions to support the J1939TP Stack (real stuff, not just repr)
    def getRealExtMsgs(self, sa, da):
        '''
        # functions to support the J1939TP Stack (real stuff, not just repr)
        returns a message list for a given source and destination (sa, da)

        if no list exists for this pairing, one is created and an empty list is returned
        '''
        msglists = self._RealExtMsgParts.get(sa)
        if msglists == None:
            msglists = {}
            self._RealExtMsgParts[sa] = msglists

        mlist = msglists.get(da)
        if mlist == None:
            mlist = {'length':0, 
                    'msgs':[], 
                    'type':None, 
                    'adminmsgs':[], 
                    'pgn0':None, 
                    'pgn1':None, 
                    'pgn2':None,   
                    'totsize':0,
                    }
            msglists[da] = mlist

        return mlist

    def clearRealExtMsgs(self, sa, da=None):
        '''
        # functions to support the J1939TP Stack (real stuff, not just repr)
        clear out extended messages metadata.

        if da == None, this clears *all* message data for a given source address

        returns whether the thing deleted exists previously
        * if da == None, returns whether the sa had anything previously
        * otherwise, if the list 
        '''
        exists = False
        if da != None:
            msglists = self._RealExtMsgParts.get(sa)
            exists = bool(msglists != None and len(msglists))
            self._RealExtMsgParts[sa] = {}
            return exists

        msglists = self._RealExtMsgParts.get(sa)
        if msglists == None:
            msglists = {}
            self._RealExtMsgParts[sa] = msglists

        mlist = msglists.get(da, {'length':0})
        msglists[da] = {'length':0, 'msgs':[], 'type':None, 'adminmsgs':[]}
        return bool(mlist['length'])

    def saveRealExtMsg(self, idx, ts, sa, da, msg, tptype):
        '''
        # functions to support the J1939TP Stack (real stuff, not just repr)
        store a TP message.
        '''
        # FIXME: do we need thread-safety wrappers here?
        msglist = self._RealExtMsgs.get((sa,da))
        if msglist == None:
            msglist = []
            self._RealExtMsgs[(sa,da)] = msglist

        msglist.append((idx, ts, sa, da, msg, tptype))

    # This is for the pretty printing stuff...
    def getExtMsgs(self, sa, da):
        '''
        returns a message list for a given source and destination (sa, da)

        if no list exists for this pairing, one is created and an empty list is returned
        '''
        msglists = self.extMsgs.get(sa)
        if msglists == None:
            msglists = {}
            self.extMsgs[sa] = msglists

        mlist = msglists.get(da)
        if mlist == None:
            mlist = {'length':0, 'msgs':[], 'type':None, 'adminmsgs':[]}
            msglists[da] = mlist

        return mlist

    def clearExtMsgs(self, sa, da=None):
        '''
        clear out extended messages metadata.

        if da == None, this clears *all* message data for a given source address

        returns whether the thing deleted exists previously
        * if da == None, returns whether the sa had anything previously
        * otherwise, if the list 
        '''
        exists = False
        if da != None:
            msglists = self.extMsgs.get(sa)
            exists = bool(msglists != None and len(msglists))
            self.extMsgs[sa] = {}
            return exists

        msglists = self.extMsgs.get(sa)
        if msglists == None:
            msglists = {}
            self.extMsgs[sa] = msglists

        mlist = msglists.get(da, {'length':0})
        msglists[da] = {'length':0, 'msgs':[], 'type':None, 'adminmsgs':[]}
        return bool(mlist['length'])

    def addID(self, newid):
        if newid not in self.myIDs:
            self.myIDs.append(newid)

    def delID(self, curid):
        if curid in self.myIDs:
            self.myIDs.remove(curid)

    def J1939xmit(self, pf, ps, sa, data, prio=6, edp=0, dp=0):
        arbid = emitArbid(prio, edp, dp, pf, ps, sa)
        return self.CANxmit(arbid, data, extflag=1)

    def J1939recv_tp(self, pgn, sa=0xfa, msgcount=1, timeout=1, advfilters=[]):
        extct = 256*msgcount
        out = []
        ext_out = []
        advfilters.append('pf in (0xeb, 0xec)')

        count = 0
        for msg in self.filterCanMsgs(start_msg=None, advfilters=advfilters, tail=True, maxsecs=timeout):
            (idx, ts, arbid, msg) = msg
            out.append(msg)

            if len(ext_out):
                return ext_out

        return out

    def J1939recv(self, msgcount=1, timeout=1, advfilters=[], start_msg=None):
        out = []

        for msg in self.filterCanMsgs(start_msg=start_msg, advfilters=advfilters, tail=True, maxsecs=timeout):
            #(idx, ts, arbid, data) = msg
            out.append(msg)

            if len(out) >= msgcount:
                return out

        return out

    def J1939xmit_recv(self, pf, ps, sa, data, recv_arbid=None, recv_count=1, prio=6, edp=0, dp=0, timeout=1, advfilters=[]):
        msgidx = self.getCanMsgCount()

        res = self.J1939xmit(pf, ps, sa, data, prio, edp, dp)
        res = self.J1939recv(recv_count, timeout, advfilters, start_msg=msgidx)

        return res


    def J1939_Request(self, rpf, rda_ge=0, redp=0, rdp=0, da=0xff, sa=0xfe, prio=0x6, recv_count=255, timeout=2, advfilters=[]):
        pgnbytes = [rda_ge, rpf, redp<<1 | rdp]
        data = ''.join([chr(x) for x in pgnbytes])
        data += '\xff' * (8-len(data))

        if not len(advfilters):
            advfilters = 'pf in (0x%x, 0xeb, 0xec)' % rpf

        # FIXME: this is only good for short requests... anything directed is likely to send back a TP message
        msgs = self.J1939xmit_recv(PF_RQST, da, sa, data, recv_count=recv_count, prio=prio, timeout=timeout, advfilters=advfilters)
        return msgs

    def J1939_ClaimAddress(self, addr, name=0x4040404040404040, prio=6):
        data = struct.pack(">Q", name)
        out = self.J1939xmit_recv(pf=PF_ADDRCLAIM, ps=0xff, sa=addr, data=data, recv_count=10, prio=prio<<2, timeout=2, advfilters=['pf==0xee'])
        self.addID(addr)
        return out

    def J1939_ArpAddresses(self):
        '''
        Sends a request for all used addresses... not fully tested
        '''
        #idx = self.getCanMsgCount()
        msgs = self.J1939_Request(PF_ADDRCLAIM, recv_count=255, advfilters=['pf==0xee'])

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
                    print msgrepr
            except Exception, e:
                print e
        '''
        example (from start of ECU):
        00000000 1545142410.990 pri/edp/dp: 6/0/0, PG: ea ff  Source: fe  Len: 03, Data: 00ee00              Request
        00000001 1545142411.077 pri/edp/dp: 6/0/0, PG: ee ff  Source: 00  Len: 08, Data: 4cca4d0100000000    Address Claim: id: 0xdca4c mfg: Cummins Inc (formerly Cummins Engine Co) Columbus, IN USA
    
        currently ours:
        00001903 1545142785.127 pri/edp/dp: 6/0/0, PG: ea ff  Source: fe  Len: 03, Data: 00ee00              Request

        '''


