import struct

def msg_encode(data):
    olist = []
    dlen = len(data)
    
    if dlen > 4095:
        raise Exception("Data too long for one ISO-TP message (<4096)")

    if dlen < 8:
        # single
        ftype = 0
        size = dlen
        b0 = (ftype << 4) | size
        olist.append( "%c%s" % (b0, data))

    else:


        # first frame
        ftype = 1
        size = dlen
        b0 = (ftype << 12) | size
        olist.append( "%s%s" % (struct.pack(">H", b0), data[:6]) )

        # consecutive frames
        frameidx = 1
        for dataidx in range(6, dlen, 7):
            ftype = 2
            b0 = (ftype << 4) | frameidx
            print hex(b0)
            olist.append( "%c%s" % (b0, data[dataidx:dataidx+7]) )

            frameidx += 1
            frameidx %= 16

    return olist



def msg_encode(msglist):
    ''' not done.  '''
    dlen = len(data)
    
    if dlen > 4095:
        raise Exception("Data too long for one ISO-TP message (<4096)")

    if dlen < 8:
        # single
        ftype = 0
        size = dlen
        b0 = (ftype << 4) | size
        olist.append( "%c%s" % (b0, data))

    else:


        # first frame
        ftype = 1
        size = dlen
        b0 = (ftype << 12) | size
        olist.append( "%s%s" % (struct.pack(">H", b0), data[:6]) )

        # consecutive frames
        frameidx = 1
        for dataidx in range(6, dlen, 7):
            ftype = 2
            b0 = (ftype << 4) | frameidx
            print hex(b0)
            olist.append( "%c%s" % (b0, data[dataidx:dataidx+7]) )

            frameidx += 1
            frameidx %= 16

    return olist
