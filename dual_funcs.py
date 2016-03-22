#!/usr/bin/env python

def dualReplay(bus1, bus2, bus1_start, bus1_end, bus2_start, bus2_end):
    bus1_num = bus1_end - bus1_start;
    bus2_num = bus2_end - bus2_start;

    bus1_sent = 0
    bus2_sent = 0

    bus1_msgs = bus1.genCanMsgs(bus1_start, bus1_end)
    bus2_msgs = bus2.genCanMsgs(bus2_start, bus2_end)

    while(bus1_sent < bus1_num and bus2_sent < bus2_num):
        # Decide if we want to send bus1 or bus2
        bus1_pct = bus1_sent / float(bus1_num)
        bus2_pct = bus2_sent / float(bus2_num)

        if(bus1_pct <= bus2_pct):
            idx,ts,arbid,data = bus1_msgs.next()
            bus1.CANxmit(arbid, data)
            bus1_sent += 1
        else:
            idx,ts,arbid,data = bus2_msgs.next()
            bus2.CANxmit(arbid, data)
            bus2_sent += 1


def dualBookmarks(bus1, bus2, msg):
    bus1.placeCanBookmark(msg)
    bus2.placeCanBookmark(msg)

