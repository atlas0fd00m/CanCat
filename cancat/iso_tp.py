from __future__ import print_function

import sys
import struct

def msg_encode(data, verbose=False):
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
            if verbose: print(hex(b0))
            olist.append( "%c%s" % (b0, data[dataidx:dataidx+7]) )

            frameidx += 1
            frameidx %= 16

    return olist


class IncompleteIsoTpMsg(Exception):
    def __init__(self, output, length):
        self.output = output
        self.length = length

    #def __repr__(self):
    def __str__(self):
        return "Data incomplete.  Remaining length: %r bytes.  Current data: %r"\
                % (self.length, self.output)


def msg_decode(msglist, offset=0, verbose=False, cancat=True):
    output = []

    count = 0
    nextidx = 0
    length = None
    midx = offset
    arbid = 0

    while midx < len(msglist) and (length == None or length > 0):
        if cancat:
            idx, ts, narbid, msg = msglist[midx]
        else:
            msg = msglist[midx]
            narbid = 0

        ctrl = msg[0]
        ftype = (ctrl >> 4)
        if ftype == 0:
            data_len = ctrl # Number of bytes in message
            if len(output):
                msg = b''.join(output)
                print("Failed to reach length %d:  only got %d" % (length, len(msg)))
                return arbid, msg, count

            # Single packet message, return only the relevant data
            data = msg[1:data_len+1]
            if verbose: print("0: %r" % data.encode('hex'))

            return narbid, data, count+1

        elif ftype == 1:
            length = struct.unpack(">H", msg[0:2])[0] & 0xfff
            arbid = narbid

            if verbose: print("length: %r" % length)

            msg = msg[2:]
            output.append(msg)
            if verbose: print("1: %r" % msg.encode('hex'))
            length -= len(msg)
            nextidx += 1

        elif ftype == 2:
            if length == None:
                raise Exception("Cannot parse ISO-TP, type 2 without type 1")
            idx = ctrl & 0xf
            if verbose: print("\t\t\t%x" % idx)
            if idx != (nextidx):
                #raise Exception("Indexing Bug: idx: %x != nextidx: %x" % (idx, nextidx))
                print("Indexing Bug: idx: %x != nextidx: %x" % (idx, nextidx))

            msg = msg[1:length+1]
            output.append(msg)
            if verbose: print("2: %r" % msg.encode('hex'))
            length -= len(msg)
            nextidx += 1

        elif ftype == 3:
            if verbose: print("Flow Control packet found: %r" % (msg.encode('hex')))
        else:
            if verbose: print("Doesn't fit: %r" % (msg.encode('hex')))

        if nextidx >= 0x10:
            nextidx = 0

        count += 1
        midx += 1

    if length != None and length < 0:
        if verbose: print("Extra bytes at the end: %r" % (output[-1][length:]))

    if length == None or length > 0:
        raise IncompleteIsoTpMsg(output, length)

    return arbid, b''.join(output), count


def msgs_decode(msglist, verbose=False):
    output = None
    messages = []

    nextidx = 0
    for msg in msglist:

        ctrl = msg[0]
        ftype = (ctrl >> 4)
        if ftype == 0:
            # Single packet message
            data = msg[1:]

            nextidx = 0
            messages.append(data)

        elif ftype == 1:
            output = []
            length = struct.unpack(">H", msg[1:3])[0] & 0xfff
            idx = ctrl & 0xf
            if verbose: print("\t\t\t%x" % idx)

            output.append(msg[2:])
            nextidx += 1
            messages.append(output)

        elif ftype == 2:
            if not length:
                raise Exception("Cannot parse ISO-TP, type 2 without type 1")
            idx = ctrl & 0xf
            if verbose: print("\t\t\t%x" % idx)
            if idx != (nextidx):
                #raise Exception("Indexing Bug: idx: %x != nextidx: %x" % (idx, nextidx))
                print("Indexing Bug: idx: %x != nextidx: %x" % (idx, nextidx))

            msg = msg[1:]
            output.append(msg)
            length -= len(msg)
            nextidx += 1

            if not length:
                messages[-1] = b''.join(output)

        elif ftype == 3:
            if verbose: print("Flow Control packet found: %r" % (msg.encode('hex')))
        else:
            if verbose: print("Doesn't fit: %r" % (msg.encode('hex')))

        if nextidx >= 0x10:
            nextidx = 0

    return messages
