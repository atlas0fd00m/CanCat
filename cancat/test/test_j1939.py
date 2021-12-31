import time
import logging
import unittest

from cancat.test.test_messages import *
from cancat.j1939stack import J1939Interface

from binascii import unhexlify

logger = logging.getLogger(__name__)


def getLoadedFakeJ1939Interface():
    # start out with CanInterface with a fake dongle
    c = J1939Interface(port='FakeCanCat')
    c._io.queueCanMessages(test_j1939_msgs_0)
    c._io.queueCanMessages(test_j1939_msgs_1)
    return c
        

class J1939_test(unittest.TestCase):
    def test_basic_j1939_dongle(self):
        c = getLoadedFakeJ1939Interface()

        pingdata = b'foobar'
        pingtest = c.ping(pingdata)
        self.assertEqual(pingdata, pingtest[1])

        for x in range(3):
            logger.warning("messageCount: %r", c.getCanMsgCount())
            time.sleep(.2)

        c.printCanMsgs()
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


