# Command line entry point for cancat2candump

import sys
import argparse
import pickle
import cancat


def cancat2candump(session, output):
    with open(session, 'rb') as f:
        sess = pickle.load(f)

    with open(output, 'w') as f:
        for msg_time, msg in sess['messages'].get(cancat.CMD_CAN_RECV, None):
            line = '({:.6f}) vcan0 {}#{}\n'.format(
                msg_time,
                msg[0:4].encode('HEX'),
                msg[4:].encode('HEX')
            )
            f.write(line)


def main():
    argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
            prog='cancat2candump',
            description='Utility to convert a CanCat session into a candump log')
    parser.add_argument('session', help='input CanCat session')
    parser.add_argument('output', help='output candump file')
    args = parser.parse_args(argv)

    cancat2candump(args.session, args.output)
