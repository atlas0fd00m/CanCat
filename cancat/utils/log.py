# Utility functions for CanCat

import argparse
import sys
import os
import pickle
import cancat
import struct
import re


def cancat2candump(args=None, argv=None):
    if args is None:
        if argv is None:
            argv = sys.argv[1:]

        parser = argparse.ArgumentParser(
                prog='cancat2candump',
                description='Utility to convert a CanCat session into a candump log')
        parser.add_argument('session', help='input CanCat session')
        parser.add_argument('output', help='output candump file')
        args = parser.parse_args(argv)

    with open(args.session, 'rb') as f:
        sess = pickle.load(f)

    with open(args.output, 'w') as f:
        for msg_time, msg in sess['messages'].get(cancat.CMD_CAN_RECV, None):
            line = '({:.6f}) vcan0 {}#{}\n'.format(
                msg_time,
                msg[0:4].encode('HEX'),
                msg[4:].encode('HEX')
            )
            f.write(line)


def cancat2pcap(args=None, argv=None):
    import scapy.layers.l2
    import scapy.packet
    import scapy.utils
    if args is None:
        if argv is None:
            argv = sys.argv[1:]

        parser = argparse.ArgumentParser(
                prog='cancat2pcap',
                description='Utility to convert a CanCat session into a pcap')
        parser.add_argument('session', type=argparse.FileType('rb'),
                help='input CanCat session')
        parser.add_argument('output', type=str,
                help='output pcap file')
        args = parser.parse_args(argv)


    sess = pickle.load(args.session)

    msgs = []
    for msg_time, msg in sess['messages'].get(cancat.CMD_CAN_RECV, None):
        arb = struct.unpack_from('>L', msg)[0] | 0x80000000
        msg_data = msg[4:]
        msg_len = len(msg_data)
        raw = struct.pack('<LL', arb, msg_len) + msg_data + '\x00' * (8 - msg_len)

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

    scapy.utils.wrpcap(args.output, msgs)


def _import_candump(filename):
    msgs = []
    with open(filename, 'r') as f:
        pat = re.compile(r'\(([0-9]+\.[0-9]+)\) [A-Za-z0-9]+ ([A-Fa-f0-9]+)#([A-Fa-f0-9]+)')
        for line in f.readlines():
            match = pat.match(line.strip())
            if match is None:
                raise ValueError('Invalid candump format: %s' % line)

            time, arb_id, data = match.groups()

            # Ensure that the arbid is padded out to 4 bytes
            if len(arb_id) < 8:
                arb_id = ('0' * (8 - len(arb_id))) + arb_id

            msgs.append((float(time), arb_id.decode('hex') + data.decode('hex')))

    sess = {
        'bookmark_info': {},
        'bookmarks': [],
        'comments': [],
        'messages': {
            cancat.CMD_CAN_RECV: msgs,
        },
    }

    return sess


def _import_pcap(filename):
    import scapy.layers.l2
    import scapy.packet
    import scapy.utils

    msgs = []
    can_pkts = [p for p in scapy.utils.rdpcap(filename) \
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
            cancat.CMD_CAN_RECV: msgs,
        },
    }

    return sess


def candump2cancat(args=None, argv=None):
    if args is None:
        if argv is None:
            argv = sys.argv[1:]

        parser = argparse.ArgumentParser(
                prog='candump2cancat',
                description='Utility to convert a candump log into a CanCat session')
        parser.add_argument('log', help='input candump log')
        parser.add_argument('output', help='output cancat session')
        args = parser.parse_args(argv)

        with open(args.output, 'w') as f:
            pickle.dump(_import_candump(args.log), f)

def pcap2cancat(args=None, argv=None):
    if args is None:
        if argv is None:
            argv = sys.argv[1:]

        parser = argparse.ArgumentParser(
                prog='pcap2cancat',
                description='Utility to convert a pcap with CAN messages into a CanCat session')
        parser.add_argument('log', help='input pcap')
        parser.add_argument('output', help='output cancat session')
        args = parser.parse_args(argv)

        with open(args.output, 'w') as f:
            pickle.dump(_import_pcap(args.log), f)
