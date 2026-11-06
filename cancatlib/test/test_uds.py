import unittest

from cancatlib.utils.types import ECUAddress
from cancatlib.uds.ecu import ECU
from cancatlib.uds.utils import ecu_did_scan, ecu_session_scan, did_str, gen_uds_resp_range
from cancatlib.uds.test import CanInterface, FakeUDS


class UDStest(unittest.TestCase):
    def test_ecu_did_scan(self):
        c = CanInterface('')
        testclass_ecus = [
            ECUAddress(0x711, 0x719, 0),
            ECUAddress(0x7e0, 0x7e8, 0)
        ]

        ecus = ecu_did_scan(c, range(0, 0x100), udscls=FakeUDS)
        self.assertEqual(testclass_ecus, ecus)

    def test_ecu_session_scan(self):
        c = CanInterface('')
        testclass_ecus = [
            ECUAddress(0x711, 0x719, 0),
            ECUAddress(0x7e0, 0x7e8, 0)
        ]

        ecus = ecu_session_scan(c, range(0, 0x100), udscls=FakeUDS)
        self.assertEqual(testclass_ecus, ecus)

    def test_did_scan(self):
        c = CanInterface('')
        testclass_ecus = [
            {
                'ecu': ECU(c, ECUAddress(0x711, 0x719, 0), scancls=FakeUDS),
                'dids': {
                    0x0042: b'\x62\x00\x42ANSWER',
                },
            },
            {
                'ecu': ECU(c, ECUAddress(0x7e0, 0x7e8, 0), scancls=FakeUDS),
                'dids': {
                    0xE010: b'\x62\xE0\x10VERSION 1.2.3',
                    0xF190: b'\x62\xF1\x901AB123CD1EF123456',
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

    def test_did_str_known_did(self):
        # A DID present in ISO_14229_DIDS should be resolved by name, not by
        # the generic manufacturer/supplier-specific range fallback.
        self.assertEqual('0xf190 (VINDataIdentifier)', did_str(0xF190))

    def test_did_str_generic_vehicle_manufacturer_range(self):
        # DIDs 0xf1a0-0xf1ef are reserved for vehicle-manufacturer-specific
        # use and aren't individually named in ISO_14229_DIDS.
        self.assertEqual(
            '0xf1a5 (identificationOptionVehicleManufacturerSpecific)', did_str(0xF1A5))

    def test_did_str_generic_system_supplier_range(self):
        # DIDs 0xf1f0-0xf1ff are reserved for system-supplier-specific use.
        self.assertEqual(
            '0xf1f5 (identificationOptionSystemSupplierSpecific)', did_str(0xF1F5))

    def test_did_str_unknown_did(self):
        # A DID outside both ISO_14229_DIDS and the generic ranges just
        # renders as hex, with no name.
        self.assertEqual('0x1234', did_str(0x1234))

    def test_gen_uds_resp_range_11bit(self):
        # 11-bit (standard) addressing always uses the fixed 0x700-0x7ff
        # OBD2/UDS response range.
        resp_range = gen_uds_resp_range(0x711)
        self.assertEqual(range(0x700, 0x800), resp_range)

    def test_gen_uds_resp_range_29bit(self):
        # 29-bit (extended) addressing computes a range based on the
        # request arbid instead of using a fixed range.
        resp_range = gen_uds_resp_range(0x18DA01F1)
        self.assertIsInstance(resp_range, range)
        self.assertEqual(0x100, len(resp_range))
