import logging
import unittest

from cancat import *
from cancat import CanInterface
from cancat.test import test_messages
from cancat.utils.types import ECUAddress

from binascii import unhexlify

logger = logging.getLogger(__name__)


class CanCat_test(unittest.TestCase):
    def test_basic_cancat_dongle(self):
        pass

