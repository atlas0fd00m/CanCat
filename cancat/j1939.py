
import cancat
import struct


def pf_eb(data):
    if len(data) < 1:
        return ''

    idx = ord(data[0])
    return 'idx: %.x' % idx

def pf_ec(data):
    out = []
    (cb, 
            size,
            pktct,
            maxct,
            sendablect,
            nextpkt,
            seq) = struct.unpack('<BBBBBHB', data)

    return 'CB: %.x size: %.2x pkt:%.2x/max:%.2x/sendable:%.2x/next:%.2x seq: %.2x' % \
            (cb, size, pktct, maxct, sendablect, nextpkt, seq)


pgn_pfs = [
        # normal
        {
        0xea:   ("Address Rqst ", None),
        0xeb:   ("TP ", pf_eb),
        0xec:   ("TP.CM",         pf_ec),
        0xee:   ("Address Claim", None),
        0xef:   ("Proprietary", None),
        },
        # page 2
        {}
        ]

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

        prio, edp, dp, PF, PS, SA = parseArbid(arbid)

        pgn_pf = pgn_pfs[dp]
        pfmeaning, handler = pgn_pf.get(PF, ('',None))
        if handler != None:
            pfmeaning += " " + handler(data)

        return "%.8d %8.3f pri/edp/dp: %d/%d/%d, PG: %.2x %.2x  Source: %.2x  Len: %.2x, Data: %-18s  %s\t\t%s" % \
                (idx, ts, prio, edp, dp, PF, PS, SA, len(data), data.encode('hex'), pfmeaning, comment)


    def _getLocals(self, idx, ts, arbid, msg):
        prio, edp, dp, PF, PS, SA = parseArbid(arbid)
        return {'idx':idx, 'ts':ts, 'arbid':arbid, 'msg':msg, 'priority':prio, 'edp':edp, 'dp':dp, 'pf':PF, 'ps':PS, 'sa':SA}

