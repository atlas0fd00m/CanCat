import time
import logging
import unittest

import cancat.j1939stack

from cancat import *
from cancat import CanInterface
from cancat.test import test_messages
from cancat.utils.types import ECUAddress

from binascii import unhexlify

logger = logging.getLogger(__name__)


class J1939Dongle_test(unittest.TestCase):
    def test_basic_j1939_dongle(self):
        # start out with CanInterface with a fake dongle
        #c = J1939Interface(port='FakeCanCat')
        c = j1939stack.J1939Interface(port='FakeCanCat')
        pingdata = b'foobar'
        pingtest = c.ping(pingdata)
        self.assertEqual(pingdata, pingtest[1])

        c._io.queueCanMessages(test_messages.test_j1939_msgs_0)
        c._io.queueCanMessages(test_messages.test_j1939_msgs_1)
        
        for x in range(3):
            logger.warning("messageCount: %r", c.getCanMsgCount())
            time.sleep(.2)

        c.printCanMsgs()
        c.printCanMsgs(advfilters=['len(data) > 8'])
        c.printCanMsgs(advfilters=['pgn == 0xfeca'])

        test_msgs_long = [x for x in c.filterCanMsgs(advfilters=['len(data) > 8'])]
        self.assertEqual(len(test_msgs_long), 2)

        test_msg_feca = [x for x in c.filterCanMsgs(advfilters=['pgn==0xfeca'])][0]
        idx, ts, arbtup, data = test_msg_feca
        self.assertEqual(data[0:5], unhexlify(b'57ff5b0004'))
        self.assertEqual(data[-5:], unhexlify(b'0139040901'))
        self.assertEqual(len(data), 78)


