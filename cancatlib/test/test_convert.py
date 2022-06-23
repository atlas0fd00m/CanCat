import os
import logging
import pathlib
import tempfile
import unittest

import cancatlib

from cancatlib import *
from cancatlib import CanInterface
from cancatlib.test import test_messages
from cancatlib.utils.types import ECUAddress

from binascii import unhexlify
from cancatlib.utils import convert


logger = logging.getLogger(__name__)
basedir = os.path.dirname(cancatlib.__file__)

class Convert_test(unittest.TestCase):
    def test_CanDump2CanCat(self):
        excandump = os.sep.join([basedir, 'test', 'data', 'candump_example.txt'])

        outf0 = tempfile.mkstemp()
        outf1 = tempfile.mkstemp()

        # first test from Candump to CanCat:
        convert.candump2cancat(excandump, outf0[1])

        # now convert back
        convert.cancat2candump(outf0[1], outf1[1])


    def test_Pcap2CanCat(self):
        excandump = os.sep.join([basedir, 'test', 'data', 'candump_example.txt'])

        outf0 = tempfile.mkstemp()
        outf1 = tempfile.mkstemp()
        outf2 = tempfile.mkstemp()

        # first test from Candump to CanCat:
        convert.candump2cancat(excandump, outf0[1])

        # now convert to pcap
        convert.cancat2pcap(outf0[1], outf1[1])

        # now convert back
        convert.pcap2cancat(outf1[1], outf2[1])

