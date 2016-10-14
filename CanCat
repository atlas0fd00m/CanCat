#!/usr/bin/env python

import sys
import readline
import rlcompleter
readline.parse_and_bind("tab: complete")

from cancat import *



intro = """'CanCat, the greatest thing since J2534!'

Research Mode: enjoy the raw power of CanCat

currently your environment has an object called "c" for CanCat.  this is how 
you interact with the CanCat tool:
    >>> c.ping()
    >>> c.placeBookmark('')
    >>> c.snapshotCanMsgs()
    >>> c.printSessionStats()
    >>> c.printCanMsgs()
    >>> c.printCanSessions()
    >>> c.CANxmit('message', )
    >>> c.CANreplay()
    >>> c.saveSessionToFile('file_to_save_session_to')
    >>> help(c)

"""

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--port', default='/dev/ttyACM0') 
    parser.add_argument('-f', '--filename', help='Load file (does not require CanCat device)') 

    ifo = parser.parse_args()

    interactive(ifo.port, intro=intro, load_filename=ifo.filename)
