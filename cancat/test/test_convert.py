import os
import logging
import pathlib
import tempfile
import unittest

import cancat

from cancat import *
from cancat import CanInterface
from cancat.test import test_messages
from cancat.utils.types import ECUAddress

from binascii import unhexlify
from cancat.utils import convert


logger = logging.getLogger(__name__)

class Convert_test(unittest.TestCase):
    def test_CanDump2CanCat(self):
        basedir = os.path.dirname(cancat.__file__)
        excandump = os.sep.join([basedir, 'test', 'data', 'candump_example.txt'])

        outf0 = tempfile.mkstemp()
        outf1 = tempfile.mkstemp()

        # first test from Candump to CanCat:
        convert.candump2cancat(excandump, outf0[1])

        # now convert back
        convert.cancat2candump(outf0[1], outf1[1])


