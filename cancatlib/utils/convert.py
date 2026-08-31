# Utility functions for CanCat

import re
import pickle
import cancatlib
import struct

from binascii import unhexlify

# --- PCAP (Linux SLL linktype) support without scapy ---------------------
# The original scapy-based conversion used Linktype 113 (LINKTYPE_LINUX_SLL /
# Cooked Linux).  We reproduce the exact same wire format manually so pcap
# files remain interoperable with tools like tcpdump and wireshark.
#
# pcap global header (little-endian), 24 bytes:
#   magic(4), version_major(2), version_minor(2),
#   thiszone(4), sigfigs(4), snaplen(4), network(4)
PCAP_GLOBAL_HDR = struct.pack(
    '<IHHiIII',
    0xA1B2C3D4,  # little-endian magic
    2, 4,        # version 2.4
    0, 0,        # thiszone, sigfigs
    262144,      # snaplen
    113,         # LINKTYPE_LINUX_SLL
)

# 16-byte Linux SLL header: pkttype(2), lladdrtype(2), lladdrlen(2),
# src(8), proto(2)
SLL_HDR = struct.pack('<HHH8sH', 1, 0x118, 0, b'', 0x0c)  # pkttype=1(host), proto=0x0c (ETH_P_CAN)


def _pcap_record(arb, msg_data, msg_time):
    """Build a single little-endian pcap record (packet header + frame)."""
    msg_len = len(msg_data)
    frame = SLL_HDR + struct.pack('<LL', arb | 0x80000000, msg_len) + msg_data + b'\x00' * (8 - msg_len)
    # pcap record header: ts_sec(4), ts_usec(4), incl_len(4), orig_len(4)
    ts_sec = int(msg_time)
    ts_usec = int((msg_time - ts_sec) * 1_000_000)
    rec_hdr = struct.pack('<IIII', ts_sec, ts_usec, len(frame), len(frame))
    return rec_hdr + frame

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
    with open(session, 'rb') as f:
        sess = pickle.load(f, encoding='latin1')

    records = []
    for msg_time, msg in sess['messages'].get(cancatlib.CMD_CAN_RECV, None):
        if isinstance(msg, str):
            msg = bytes(msg, 'latin1')

        arb = struct.unpack_from('>L', msg)[0]
        msg_data = msg[4:]
        records.append(_pcap_record(arb, msg_data, msg_time))

    with open(output, 'wb') as f:
        f.write(PCAP_GLOBAL_HDR)
        for rec in records:
            f.write(rec)


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
    msgs = []
    with open(filename, 'rb') as f:
        # Read and validate the global header
        gh = f.read(24)
        if len(gh) != 24:
            raise ValueError('Invalid pcap file: too short for global header')
        magic = struct.unpack_from('<I', gh, 0)[0]
        if magic == 0xA1B2C3D4:
            # little-endian
            endian = '<'
        elif struct.unpack_from('>I', gh, 0)[0] == 0xA1B2C3D4:
            # big-endian
            endian = '>'
        else:
            raise ValueError('Invalid pcap file: bad magic 0x%08x' % magic)
        # network/encapsulation type
        network = struct.unpack_from(endian + 'I', gh, 20)[0]
        if network != 113:
            raise ValueError('Unsupported pcap network type %d (expected 113/LINKTYPE_LINUX_SLL)' % network)

        while True:
            rec_hdr = f.read(16)
            if len(rec_hdr) != 16:
                break  # clean EOF
            (ts_sec, ts_usec, incl_len, orig_len) = struct.unpack(endian + 'IIII', rec_hdr)
            frame = f.read(incl_len)
            if len(frame) != incl_len:
                raise ValueError('Truncated pcap packet record')

            # SLL header: pkttype(2), lladdrtype(2), lladdrlen(2), src(8), proto(2)
            if len(frame) < 16 + 8:
                continue
            proto = struct.unpack_from(endian + 'H', frame, 14)[0]
            if proto != 0x0c:  # ETH_P_CAN
                continue
            payload = frame[16:]

            # CAN frame: ARB id(4) | length(4) | data(len)
            arb_id, data_len = struct.unpack_from(endian + 'LL', payload)
            # Clear any flags in the arbitration ID field that might be set
            arb_id &= 0x1FFFFFFF
            msgs.append((ts_sec + ts_usec / 1_000_000, struct.pack('>L', arb_id) + payload[8:8+data_len]))

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
