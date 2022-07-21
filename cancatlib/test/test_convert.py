import os
import time
import logging
import pathlib
import tempfile
import unittest

import cancatlib
import cancatlib.test.data.candump_examples as testdata


from cancatlib import *
from cancatlib import CanInterface
from cancatlib.test import test_messages
from cancatlib.utils.types import ECUAddress

from binascii import unhexlify
from cancatlib.utils import convert


logger = logging.getLogger(__name__)

class Convert_test(unittest.TestCase):
    def test_CanDump2CanCat(self):
        outf0 = tempfile.mkstemp()
        with open(outf0[1], 'wb') as outf:
            outf.write(testdata.filedata)
            outf.close()

        outf1 = tempfile.mkstemp()
        outf2 = tempfile.mkstemp()

        # first test from Candump to CanCat:
        convert.candump2cancat(outf0[1], outf1[1])

        # now convert back
        convert.cancat2candump(outf1[1], outf2[1])


    def test_Pcap2CanCat(self):
        outf0 = tempfile.mkstemp()
        with open(outf0[1], 'wb') as outf:
            outf.write(testdata.filedata)
            outf.close()

        outf1 = tempfile.mkstemp()
        outf2 = tempfile.mkstemp()
        outf3 = tempfile.mkstemp()

        # first test from Candump to CanCat:
        convert.candump2cancat(outf0[1], outf1[1])

        # now convert to pcap
        #convert.cancat2pcap(outf1[1], outf2[1])

        # now convert back
        #convert.pcap2cancat(outf2[1], outf3[1])

