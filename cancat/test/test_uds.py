import unittest

from cancat.utils.types import ECUAddress
from cancat.uds.ecu import ECU
from cancat.uds.utils import ecu_did_scan, ecu_session_scan
from cancat.uds.test import CanInterface, TestUDS

class UDStest(unittest.TestCase):
    def test_ecu_did_scan(self):
        c = CanInterface('')
        testclass_ecus = [
            ECUAddress(0x711, 0x719, 0),
            ECUAddress(0x7e0, 0x7e8, 0)
        ]

        ecus = ecu_did_scan(c, range(0, 0x100), udscls=TestUDS)
        self.assertEqual(testclass_ecus, ecus)

    def test_ecu_session_scan(self):
        c = CanInterface('')
        testclass_ecus = [
            ECUAddress(0x711, 0x719, 0),
            ECUAddress(0x7e0, 0x7e8, 0)
        ]

        ecus = ecu_session_scan(c, range(0, 0x100), udscls=TestUDS)
        self.assertEqual(testclass_ecus, ecus)

    def test_did_scan(self):
        c = CanInterface('')
        testclass_ecus = [
            {
                'ecu': ECU(c, ECUAddress(0x711, 0x719, 0), scancls=TestUDS),
                'dids': {
                    0x0042: '\x62\x00\x42ANSWER',
                },
            },
            {
                'ecu': ECU(c, ECUAddress(0x7e0, 0x7e8, 0), scancls=TestUDS),
                'dids': {
                    0xE010: '\x62\xE0\x10VERSION 1.2.3',
                    0xF190: '\x62\xF1\x901AB123CD1EF123456',
                },
            },
        ]
        for test in testclass_ecus:
            ecu = test['ecu']
            test_dids = list(test['dids'].keys())

            before_scan_sessions = list(ecu._sessions.keys())
            self.assertEqual([1], before_scan_sessions)

            before_scan_dids = list(ecu._sessions[1]['dids'].keys())
            self.assertEqual([], before_scan_dids)

            ecu.did_read_scan(range(0, 0x10000))

            after_scan_sessions = list(ecu._sessions.keys())
            self.assertEqual([1], after_scan_sessions)

            dids = list(ecu._sessions[1]['dids'].keys())
            self.assertEqual(test_dids, dids)

            for did in test['dids'].keys():
                self.assertEqual(test['dids'][did], ecu._sessions[1]['dids'][did]['resp'])
