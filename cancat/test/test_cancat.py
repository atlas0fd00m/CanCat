import logging
import unittest

from cancat import *
from cancat import CanInterface
from cancat.test import test_messages
from cancat.utils.types import ECUAddress

from binascii import unhexlify

logger = logging.getLogger(__name__)


def getLoadedFakeCanCatInterface():
    # start out with CanInterface with a fake dongle
    c = CanInterface(port='FakeCanCat')
    c._io.queueCanMessages(test_messages.test_j1939_msgs_0)
    c._io.queueCanMessages(test_messages.test_j1939_msgs_1)
    return c
        
class CanCat_test(unittest.TestCase):
    def test_basic_cancat_dongle(self):
        c = getLoadedFakeCanCatInterface()

        # test CANrecv()
        msg = next(c.CANrecv())

        # test the rest of the CanCat interface
