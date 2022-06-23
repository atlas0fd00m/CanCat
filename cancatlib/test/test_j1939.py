import time
import logging
import unittest

from cancat.test.test_messages import *
from cancat.j1939stack import J1939Interface

from binascii import unhexlify

logger = logging.getLogger(__name__)


def getLoadedFakeJ1939Interface(**kwargs):
    # start out with CanInterface with a fake dongle
    c = J1939Interface(port='FakeCanCat', **kwargs)
    c._io.queueCanMessages(test_j1939_msgs_0)
    c._io.queueCanMessages(test_j1939_msgs_1)
    return c
        

class J1939_test(unittest.TestCase):
    def test_basic_j1939_dongle(self):
        c = getLoadedFakeJ1939Interface()

        pingdata = b'foobar'
        pingtest = c.ping(pingdata)
        self.assertEqual(pingdata, pingtest[1])

        for x in range(16):
            canmsgct = c.getCanMsgCount()
            logger.warning("messageCount: %r", canmsgct)
            if canmsgct > 700:
                break
            time.sleep(.2)

        logger.info(c.reprCanMsgs()[-300:])
        c.printCanMsgs(advfilters=['len(data) > 8'])
        c.printCanMsgs(advfilters=['pgn == 0xfeca'])


        # make sure we have the correct number of LONG J1939 messages here
        test_msgs_long = [x for x in c.filterCanMsgs(advfilters=['len(data) > 8'])]
        self.assertEqual(len(test_msgs_long), 2)

        # validate one particular message
        test_msg_feca = [x for x in c.filterCanMsgs(advfilters=['pgn==0xfeca'])][0]
        idx, ts, arbtup, data = test_msg_feca
        self.assertEqual(data[0:5], unhexlify(b'57ff5b0004'))
        self.assertEqual(data[-5:], unhexlify(b'0139040901'))
        self.assertEqual(len(data), 78)


        # now do destructive testing
        ts, arbtup, msg = c.J1939recv(pf=0xf0, ps=0x03, sa=0)[0]
        self.assertEqual(arbtup, (0x3, 0x0, 0x0, 0xf0, 0x3, 0x0))
        self.assertEqual(msg, b'\xda\xfe\x00\xff\xff\x0fc}')

