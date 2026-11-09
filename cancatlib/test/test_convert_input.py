import os
import sys
import pickle
import tempfile
import unittest
from unittest import mock
from binascii import unhexlify

import cancatlib
from cancatlib.utils import convert


class ConvertInput_test(unittest.TestCase):
    def test_candump2cancat_standard_ids(self):
        # candump -l writes 11-bit IDs as 3 hex digits ("7DF#...")
        fd, log = tempfile.mkstemp()
        with os.fdopen(fd, 'wb') as f:
            f.write(b'(1700000000.250000) vcan0 7DF#0201000000000000\n'
                    b'(1700000000.260000) vcan0 7E8#064100BE3FA813\n'
                    b'(1700000000.270000) vcan0 18DAF110#1122\n')
        fd, out = tempfile.mkstemp()
        os.close(fd)
        convert.candump2cancat(log, out)
        with open(out, 'rb') as f:
            msgs = pickle.load(f)['messages'][cancatlib.CMD_CAN_RECV]
        self.assertEqual(msgs, [
            (1700000000.25, unhexlify('000007df0201000000000000')),
            (1700000000.26, unhexlify('000007e8064100be3fa813')),
            (1700000000.27, unhexlify('18daf1101122')),
        ])

    def test_cancat2pcap_cli_passes_path(self):
        import cancatlib.scripts.cancat2pcap as cli
        with mock.patch.object(cli.convert, 'cancat2pcap') as conv, \
                mock.patch.object(sys, 'argv', ['cancat2pcap', 'in.sess', 'out.pcap']):
            cli.main()
        conv.assert_called_once_with('in.sess', 'out.pcap')
