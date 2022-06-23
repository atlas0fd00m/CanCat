# Utility functions for CanCat

import re
import pickle
import cancatlib
import struct

from binascii import unhexlify

def cancat2candump(session, output):
    with open(session, 'rb') as f:
        sess = pickle.load(f, encoding='latin1')

    with open(output, 'w') as f:
        for msg_time, msg in sess['messages'].get(cancatlib.CMD_CAN_RECV, None):
            if isinstance(msg, str):
                msg = bytes(msg, 'latin1')

            line = '({:.6f}) vcan0 {}#{}\n'.format(
                msg_time,
                msg[0:4].hex(),
                msg[4:].hex(),
            )
            f.write(line)


def cancat2pcap(session, output):
    import scapy.layers.l2
    import scapy.packet
    import scapy.utils

    with open(session, 'rb') as f:
        sess = pickle.load(f, encoding='latin1')

    msgs = []
    for msg_time, msg in sess['messages'].get(cancatlib.CMD_CAN_RECV, None):
        if isinstance(msg, str):
            msg = bytes(msg, 'latin1')

        arb = struct.unpack_from('>L', msg)[0] | 0x80000000
        msg_data = msg[4:]
        msg_len = len(msg_data)
        raw = struct.pack('<LL', arb, msg_len) + msg_data + b'\x00' * (8 - msg_len)

        pkt = scapy.layers.l2.CookedLinux(
                pkttype=1,
                lladdrtype=0x118,
                lladdrlen=0,
                src='',
                proto=0xc
              ) / scapy.packet.Raw(
                load=raw
              )
        pkt.time = msg_time

        msgs.append(pkt)

    scapy.utils.wrpcap(output, msgs)


def _import_candump(filename):
    msgs = []
    with open(filename, 'rb') as f:
        pat = re.compile(br'\(([0-9]+\.[0-9]+)\) [A-Za-z0-9]+ ([A-Fa-f0-9]+)#([A-Fa-f0-9]*)( *;.*)*')
        for line in f.readlines():
            match = pat.match(line.strip())
            if match is None:
                raise ValueError('Invalid candump format: %s' % line)

            time, arb_id, data, comment = match.groups()

            # Ensure that the arbid is padded out to 4 bytes
            if len(arb_id) < 8:
                arb_id = ('0' * (8 - len(arb_id))) + arb_id

            msgs.append((float(time), unhexlify(arb_id) + unhexlify(data)))

    sess = {
        'bookmark_info': {},
        'bookmarks': [],
        'comments': [],
        'messages': {
            cancatlib.CMD_CAN_RECV: msgs,
        },
    }

    return sess


def _import_pcap(filename):
    import scapy.layers.l2
    import scapy.packet
    import scapy.utils

    msgs = []
    can_pkts = [p for p in scapy.utils.rdpcap(filename)
                if scapy.layers.l2.CookedLinux in p and p.proto == 12]
    for pkt in can_pkts:
        [arb_id, data_len] = struct.unpack_from('<LL', pkt.load)

        # Clear any flags in the arbitration ID field that might be set
        arb_id &= 0x1FFFFFFF
        msgs.append((pkt.time, struct.pack('>L', arb_id) + pkt.load[8:8+data_len]))

    sess = {
        'bookmark_info': {},
        'bookmarks': [],
        'comments': [],
        'messages': {
            cancatlib.CMD_CAN_RECV: msgs,
        },
    }

    return sess


def candump2cancat(candumplog, output):
    with open(output, 'wb') as f:
        pickle.dump(_import_candump(candumplog), f)


def pcap2cancat(pcapfile, output):
    with open(output, 'wb') as f:
        pickle.dump(_import_pcap(pcapfile), f)
