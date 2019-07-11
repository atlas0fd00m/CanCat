# Command line entry point for cancat2pcap
# This requires scapy to be installed

import sys
import argparse
import pickle
import struct
import cancat

import scapy.layers.l2
import scapy.packet
import scapy.utils


def cancat2pcap(session, output):
    sess = pickle.load(session)

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

    scapy.utils.wrpcap(output, msgs)


def main():
    argv = sys.argv[1:]
                                                                           
    parser = argparse.ArgumentParser(
            prog='cancat2pcap',
            description='Utility to convert a CanCat session into a pcap')
    parser.add_argument('session', type=argparse.FileType('rb'),
            help='input CanCat session')
    parser.add_argument('output', type=str,
            help='output pcap file')
    args = parser.parse_args(argv)

    cancat2pcap(args.session, args.output)
