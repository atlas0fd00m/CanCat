# Command line entry point for candump2cancat
# This requires scapy to be installed

import sys
import argparse
import cancat.utils.parse


def main():
    argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
            prog='pcap2cancat',
            description='Utility to convert a pcap with CAN messages into a CanCat session')
    parser.add_argument('pcap', help='input pcap')
    parser.add_argument('output', help='output cancat session')
    args = parser.parse_args(argv)

    cancat.utils.parse.pcap2cancat(args.pcap, args.output)
