# Command line entry point for candump2cancat
# This requires scapy to be installed

import sys
import argparse
import pickle
import struct
import cancat

import scapy.layers.l2
import scapy.packet
import scapy.utils


def _import_pcap(filename):
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


def pcap2cancat(pcap, output):
    with open(output, 'w') as f:
        pickle.dump(_import_pcap(pcap), f)


def main():
    argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
            prog='pcap2cancat',
            description='Utility to convert a pcap with CAN messages into a CanCat session')
    parser.add_argument('pcap', help='input pcap')
    parser.add_argument('output', help='output cancat session')
    args = parser.parse_args(argv)

    pcap2cancat(args.pcap, args.output)
