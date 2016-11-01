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



def msg_decode(msglist, verbose=False):
    messages = []
    output = []

    nextidx = 0
    for msg in msglist:

        ctrl = ord(msg[0])
        ftype = (ctrl >> 4)
        if ftype == 0:
            # Single packet message
            data = msg[1:]

            nextidx = 0
            messages.append(''.join(output))

        elif ftype == 1:
            length = struct.unpack(">H", msg[1:3])[0] & 0xfff
            idx = ctrl & 0xf
            if verbose: print "\t\t\t%x" % idx

            output.append(msg[2:])
            nextidx += 1

        elif ftype == 2:
            if length == None:
                raise Exception("Cannot parse ISO-TP, type 2 without type 1")
            idx = ctrl & 0xf
            if verbose: print "\t\t\t%x" % idx
            if idx != (nextidx):
                #raise Exception("Indexing Bug: idx: %x != nextidx: %x" % (idx, nextidx))
                print("Indexing Bug: idx: %x != nextidx: %x" % (idx, nextidx))

            output.append(msg[1:])
            nextidx += 1
        elif ftype == 3:
            if verbose: print "Flow Control packet found: %r" % (msg.encode('hex'))
        else:
            if verbose: print "Doesn't fit: %r" % (msg.encode('hex'))

        if nextidx >= 0x10:
            nextidx = 0

    return messages
