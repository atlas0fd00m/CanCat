# Command line entry point for cancat2pcap
# This requires scapy to be installed

import sys
import argparse
from cancat.utils import convert


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

    convert.cancat2pcap(args.session, args.output)
