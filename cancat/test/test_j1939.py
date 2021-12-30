import time
import logging
import unittest

from cancat.test import test_messages
from cancat.utils.types import ECUAddress
from cancat import CanInterface

import cancat.j1939stack
from cancat import *


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
        test_msgs_long = [x for x in c.filterCanMsgs(advfilters=['len(data) > 8'])]
        for test_msg_long in test_msgs_long:
            logger.warning(test_msg_long)


