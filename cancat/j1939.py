
import cancat
import struct


def pf_c9(arbtup, data):
    b4 = data[3]
    req = "%.2x %.2x %.2x" % ([ord(d) for d in data[:3]])
    usexferpfn = ('', 'Use_Transfer_PGN', 'undef', 'NA')[b4 & 3]
    
    return "Request2: %s %s" % (req,  usexferpgn)

def pf_eb(arbtup, data):
    if len(data) < 1:
        return 'TP ERROR: NO DATA!'

    idx = ord(data[0])
    return 'TP.DT idx: %.x' % idx

def tp_cm_10(arbtup, data):
    (cb, 
            totsize,
            pktct,
            maxct,
            tpf, tps, tsa) = struct.unpack('<BHBBBBB', data)

    return 'TP.CM_RTS size:%.2x pktct:%.2x maxpkt:%.2x PGN: %.2x %.2x %.2x' % \
            (totsize, pktct, maxct, tpf, tps, tsa)

def tp_cm_11(arbtup, data):
    (cb, 
            maxpkts,
            nextpkt,
            reserved,
            tpf, tps, tsa) = struct.unpack('<BBBHBBB', data)

    return 'TP.CM_CTS        maxpkt:%.2x nxtpkt:%.2x PGN: %.2x %.2x %.2x' % \
            (maxpkts, nextpkt, tpf, tps, tsa)

def tp_cm_20(arbtup, data):
    (cb, 
            totsize,
            pktct,
            reserved,
            tpf, tps, tsa) = struct.unpack('<BHBBBBB', data)

    return 'TP.CM_BAM-Broadcast size:%.2x pktct:%.2x PGN: %.2x %.2x %.2x' % \
            (totsize, pktct, tpf, tps, tsa)

tp_cm_handlers = {
        0x10:     ('RTS',           tp_cm_10),
        0x11:     ('CTS',           tp_cm_11),
        0x13:     ('EndOfMsgACK',   None),
        0x20:     ('BAM-Broadcast', tp_cm_20),
        0xff:     ('Abort',         None),
        }

def pf_ec(arbtup, data):
    cb = ord(data[0])

    htup = tp_cm_handlers.get(cb)
    if htup != None:
        subname, cb_handler = htup

        if cb_handler == None:
            return 'TP.CM_%s' % subname

        newmsg = cb_handler(arbtup, data)
        if newmsg == None:
            return 'TP.CM_%s' % subname

        return newmsg

    return 'TP.CM_%.2x' % cb

def pf_ee((prio, edp, dp, pf, ps, sa), data):
    if ps == 255 and sa == 254:
        return 'CANNOT CLAIM ADDRESS'

def pf_ef((prio, edp, dp, pf, ps, sa), data):
    if dp:
        return 'Proprietary A2'

    return 'Proprietary A1'
    
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
        0xff:   ("Proprietary B",   None),
        }

def parseArbid(arbid):
    (prioPlus,
        PF,
        PS,
        SA) = struct.unpack('BBBB', struct.pack(">I", arbid))

    prio = prioPlus >> 2
    edp = (prioPlus >> 1) & 1
    dp = prioPlus & 1


    return prio, edp, dp, PF, PS, SA

class J1939(cancat.CanInterface):
    def __init__(self, c=None):
        cancat.CanInterface.__init__(self, port=None, orig_iface=c)
        #me = c.saveSession()
        #self.restoreSession(me)

    def _reprCanMsg(self, idx, ts, arbid, data, comment=None):
        if comment == None:
            comment = ''

        arbtup = parseArbid(arbid)
        prio, edp, dp, PF, PS, SA = arbtup

        pfmeaning, handler = pgn_pfs.get(PF, ('',None))
        if handler != None:
            enhanced = handler(arbtup, data)
            if enhanced != None:
                pfmeaning = enhanced

        return "%.8d %8.3f pri/edp/dp: %d/%d/%d, PG: %.2x %.2x  Source: %.2x  Len: %.2x, Data: %-18s  %s\t\t%s" % \
                (idx, ts, prio, edp, dp, PF, PS, SA, len(data), data.encode('hex'), pfmeaning, comment)


    def _getLocals(self, idx, ts, arbid, msg):
        prio, edp, dp, PF, PS, SA = parseArbid(arbid)
        return {'idx':idx, 'ts':ts, 'arbid':arbid, 'msg':msg, 'priority':prio, 'edp':edp, 'dp':dp, 'pf':PF, 'ps':PS, 'sa':SA}

