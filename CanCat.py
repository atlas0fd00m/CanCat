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

    interfaces = [iface[:-9] for iface in globals().keys() if iface.endswith('Interface')]
    interface_names = ', '.join(interfaces)

    bauds = [baud[4:-3] for baud in globals().keys() if baud.startswith('CAN_') and baud.endswith('BPS')]
    baud_nums = ', '.join(bauds)

    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--port', default='/dev/ttyACM0') 
    parser.add_argument('-f', '--filename', help='Load file (does not require CanCat device)') 
    parser.add_argument('-I', '--interface', help='Use a predefined Interface (%s)' % interface_names) 
    parser.add_argument('-S', '--baud', help='Set the CAN Bus Speed (%s)' % (baud_nums)) 

    ifo = parser.parse_args()

    interface = CanInterface

    if ifo.interface:
        ifacename = ifo.interface + "Interface"
        interface = globals().get(ifacename)
        if interface == None:
            raise Exception("Invalid interface: %s.  Must use one of the following: %s" % (ifo.interface, interface_names))

    baud_val = CAN_500KBPS
    if ifo.baud:
        baud_val = globals().get("CAN_%sBPS" % ifo.baud)
        if baud_val == None:
            raise Exception("Invalid baud: %s.  Must use one of the following: %s" % (ifo.baud, baud_nums))

    interactive(ifo.port, intro=intro, InterfaceClass=interface, load_filename=ifo.filename, can_baud=baud_val)
