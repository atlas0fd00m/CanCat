# Command line entry point for candump2cancat

import sys
import argparse
from cancat.utils import convert


def main():
    argv = sys.argv[1:]
                                                                                  
    parser = argparse.ArgumentParser(
            prog='candump2cancat',
            description='Utility to convert a candump log into a CanCat session')
    parser.add_argument('log', help='input candump log')
    parser.add_argument('output', help='output cancat session')
    args = parser.parse_args(argv)

    convert.candump2cancat(args.log, args.output)
