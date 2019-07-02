# Utility functions for CanCat

import argparse
import sys
import os
import pickle
import cancat


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
    import struct
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
        arb = struct.unpack('>L', msg[:4])[0] | 0x80000000
        msg_data = msg[4:]
        msg_len = len(msg_data)
        raw = struct.pack('<LL', arb, msg_len) + msg_data + '\x00' * (8 - msg_len)

        pkt = scapy.layers.l2.CookedLinux(pkttype=1, lladdrtype=0x118, lladdrlen=0, src='', proto=0xc) / scapy.packet.Raw(load=raw)
        pkt.time = msg_time

        msgs.append(pkt)

    scapy.utils.wrpcap(args.output, msgs)
