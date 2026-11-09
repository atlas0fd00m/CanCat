import os
import time
import pickle
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
        convert.cancat2pcap(outf1[1], outf2[1])

        # now convert back
        convert.pcap2cancat(outf2[1], outf3[1])

    # Reference pcap produced by the original scapy-based cancat2pcap()
    # (CookedLinux/SLL, big-endian SLL fields, little-endian can_frame).
    SCAPY_PCAP_HEX = (
        # pcap global header: LE magic, v2.4, snaplen 65535, linktype 113
        'd4c3b2a1020004000000000000000000ffff000071000000'
        # rec 0: pcap rec hdr | SLL hdr | can_frame
        '00f1536590d003002000000020000000'
        '0001011800000000000000000000000c'
        'df070080080000000201000000000000'
        # rec 1
        '01f1536520a107002000000020000000'
        '0001011800000000000000000000000c'
        '10f1da98020000001122000000000000'
    )
    SCAPY_PCAP_MSGS = [
        (1700000000.25, unhexlify('000007df0201000000000000')),
        (1700000001.5, unhexlify('18daf1101122')),
    ]

    def _session_file(self, msgs):
        fd, path = tempfile.mkstemp()
        with os.fdopen(fd, 'wb') as f:
            pickle.dump({'bookmark_info': {}, 'bookmarks': [], 'comments': [],
                         'messages': {cancatlib.CMD_CAN_RECV: msgs}}, f)
        return path

    def test_cancat2pcap_matches_scapy_output(self):
        sess = self._session_file(self.SCAPY_PCAP_MSGS)
        fd, out = tempfile.mkstemp()
        os.close(fd)
        convert.cancat2pcap(sess, out)
        with open(out, 'rb') as f:
            self.assertEqual(f.read().hex(), self.SCAPY_PCAP_HEX)

    def test_pcap2cancat_reads_scapy_output(self):
        fd, pcap = tempfile.mkstemp()
        with os.fdopen(fd, 'wb') as f:
            f.write(unhexlify(self.SCAPY_PCAP_HEX))
        fd, out = tempfile.mkstemp()
        os.close(fd)
        convert.pcap2cancat(pcap, out)
        with open(out, 'rb') as f:
            msgs = pickle.load(f)['messages'][cancatlib.CMD_CAN_RECV]
        self.assertEqual(msgs, self.SCAPY_PCAP_MSGS)
