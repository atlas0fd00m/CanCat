# Command line entry point for candump2cancat

import sys
import argparse
import pickle
import re
import cancat


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


def candump2cancat(candump_log, output):
    with open(output, 'w') as f:
        pickle.dump(_import_candump(candump_log), f)


def main():
    argv = sys.argv[1:]
                                                                                  
    parser = argparse.ArgumentParser(
            prog='candump2cancat',
            description='Utility to convert a candump log into a CanCat session')
    parser.add_argument('log', help='input candump log')
    parser.add_argument('output', help='output cancat session')
    args = parser.parse_args(argv)

    candump2cancat(args.log, args.output)
