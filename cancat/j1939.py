import cancat
import struct
from J1939db import *
from J1939namedb import *

import vstruct
from vstruct.bitfield import *

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


def meldExtMsgs(msgs):
    out = ['Ext Msg: %.2x->%.2x' % (msgs['sa'], msgs['da'])]
    for arbtup, msg in msgs.get('msgs'):
        out.append(msg.encode('hex'))

    return ' '.join(out)

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
            msgdata = '\n\t' + meldExtMsgs(extmsgs)
            # FIXME: do both here??

    if len(extmsgs['msgs']) > extmsgs['length']:
            #print "ERROR: too many messages in Extended Message between %.2x -> %.2x\n\t%r" % (sa, da, extmsgs['msgs'])
            pass

    return 'TP.DT idx: %.x%s' % (idx, msgdata)

def pf_ec(arbtup, data, j1939):
    def tp_cm_10(arbtup, data, j1939):
        (prio, edp, dp, pf, da, sa) = arbtup

        (cb, totsize, pktct, maxct,
                tpf, tps, tsa) = struct.unpack('<BHBBBBB', data)
        
        # check for old stuff
        extmsgs = j1939.getExtMsgs(sa, da)
        if len(extmsgs['msgs']):
            extmsgs['sa'] = sa
            extmsgs['da'] = da
            print "\n new extended message, without closure...: "
            print "\t" + meldExtMsgs(extmsgs)

        j1939.clearExtMsgs(sa, da)

        # store extended message information for other stuff...
        extmsgs = j1939.getExtMsgs(sa, da)
        extmsgs['sa'] = sa
        extmsgs['da'] = da
        extmsgs['length'] = pktct
        extmsgs['type'] = 'direct'
        extmsgs['adminmsgs'].append((arbtup, data))

        return 'TP.CM_RTS size:%.2x pktct:%.2x maxpkt:%.2x PGN: %.2x%.2x%.2x' % \
                (totsize, pktct, maxct, tpf, tps, tsa)

    def tp_cm_11(arbtup, data, j1939):
        (prio, edp, dp, pf, da, sa) = arbtup

        (cb, maxpkts, nextpkt, reserved,
                tpf, tps, tsa) = struct.unpack('<BBBHBBB', data)

        # store extended message information for other stuff...
        extmsgs = j1939.getExtMsgs(sa, da)
        extmsgs['adminmsgs'].append((arbtup, data))

        return 'TP.CM_CTS        maxpkt:%.2x nxtpkt:%.2x PGN: %.2x%.2x%.2x' % \
                (maxpkts, nextpkt, tpf, tps, tsa)

    def tp_cm_13(arbtup, data, j1939):
        (prio, edp, dp, pf, da, sa) = arbtup

        (cb, totsize, pktct, maxct,
                tpf, tps, tsa) = struct.unpack('<BHBBBBB', data)

        # print out extended message and clear the buffers.
        extmsgs = j1939.getExtMsgs(sa, da)
        extmsgs['adminmsgs'].append((arbtup, data))

        j1939.clearExtMsgs(sa, da)
        msgdata = meldExtMsgs(extmsgs)

        return 'TP.EndOfMsgACK PGN: %.2x%.2x%.2x\n\t%r' % \
                (tpf, tps, tsa, msgdata)

    def tp_cm_20(arbtup, data, j1939):
        (prio, edp, dp, pf, da, sa) = arbtup

        (cb, totsize, pktct, reserved,
                tpf, tps, tsa) = struct.unpack('<BHBBBBB', data)

        # check for old stuff
        extmsgs = j1939.getExtMsgs(sa, da)
        if len(extmsgs['msgs']):
            extmsgs['sa'] = sa
            extmsgs['da'] = da
            print "\n new extended message, without closure...: "
            print "\t" + meldExtMsgs(extmsgs)

        j1939.clearExtMsgs(sa, da)

        # store extended message information for other stuff...
        extmsgs = j1939.getExtMsgs(sa, da)
        extmsgs['sa'] = sa
        extmsgs['da'] = da
        extmsgs['length'] = pktct
        extmsgs['type'] = 'BAM'
        extmsgs['adminmsgs'].append((arbtup, data))

        return 'TP.CM_BAM-Broadcast size:%.2x pktct:%.2x PGN: %.2x%.2x%.2x' % \
                (totsize, pktct, tpf, tps, tsa)

    tp_cm_handlers = {
            0x10:     ('RTS',           tp_cm_10),
            0x11:     ('CTS',           tp_cm_11),
            0x13:     ('EndOfMsgACK',   None),
            0x20:     ('BAM-Broadcast', tp_cm_20),
            0xff:     ('Abort',         None),
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
        0xfe:   ("Command Address", None),
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

class J1939(cancat.CanInterface):
    def __init__(self, c=None):
        cancat.CanInterface.__init__(self, port=None, orig_iface=c)
        self.extMsgs = {}

    def _reprCanMsg(self, idx, ts, arbid, data, comment=None):
        if comment == None:
            comment = ''

        arbtup = parseArbid(arbid)
        prio, edp, dp, pf, ps, sa = arbtup

        # give name priority to the Handler, then the manual name (this module), then J1939PGNdb
        pfmeaning, handler = pgn_pfs.get(pf, ('',None))

        if handler != None:
            enhanced = handler(arbtup, data, self)
            if enhanced != None:
                pfmeaning = enhanced

        elif not len(pfmeaning):
            pgn = (pf<<8) | ps
            res = J1939PGNdb.get(pgn)
            if res == None:
                res = J1939PGNdb.get(pf<<8)
            if res != None:
                pfmeaning = res.get("Name")

        return "%.8d %8.3f pri/edp/dp: %d/%d/%d, PG: %.2x %.2x  Source: %.2x  Len: %.2x, Data: %-18s  %s\t\t%s" % \
                (idx, ts, prio, edp, dp, pf, ps, sa, len(data), data.encode('hex'), pfmeaning, comment)


    def _getLocals(self, idx, ts, arbid, msg):
        prio, edp, dp, pf, ps, sa = parseArbid(arbid)
        pgn = (pf<<8) | ps
        lcls = {'idx':idx, 'ts':ts, 'arbid':arbid, 'msg':msg, 'priority':prio, 'edp':edp, 'dp':dp, 'pf':pf, 'ps':ps, 'sa':sa, 'pgn':pgn}

        return lcls

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


    def J1939xmit(self, pf, ps, sa, data, prio=6, edp=0, dp=0):
        arbid = emitArbid(prio, edp, dp, pf, ps, sa)
        self.CANxmit(arbid, data)

    def J1939recv(self, pf, ps, sa, edp=0, dp=0, count=1, advfilters=[]):
        pass

    def J1939xmit_recv(self, pf, ps, sa, data, recv_arbid=None, recv_count=1, prio=6, edp=0, dp=0, advfilters=[]):
        arbid = emitArbid(prio, edp, dp, pf, ps, sa)
        msgidx = self.getCanMsgCount()

        self.CANxmit(arbid, data)
        res = self.J1939recv(recv_arbid, recv_count, advfilters)

        return res


    def J1939_ClaimAddress(self, addr, name=0x4040404040404040, prio=0x18):
        out = self.J1939xmit_recv(prioPlus, pf, ps, sa, timeout=2)

    def J1939_ArpAddresses(self):
        pass
