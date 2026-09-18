"""Regression tests for UDS "response pending" (NRC 0x78) handling over
socketcan.

UDS.xmit_recv()'s retry-on-0x78 path calls CanInterface._isotp_get_msg(),
which was originally a firmware/serial-mailbox-only implementation (it scans
a position index into the raw CAN message log). Under socketcan that index
is always None (there's no mailbox position -- see ISOTPxmit_recv()), so the
retry path (`start_index=idx+1`) TypeError'd on `None + 1` the moment a real
ECU used 0x78 to say "still working, give me more time."

Like tests/test_socketcan_j1939.py these import cancatlib itself (pyserial
required), so they're skipped rather than failing outright if that's not
available.

Run:  python -m unittest tests.test_socketcan_uds -v
"""
import time
import threading
import unittest
from unittest import mock

try:
    import serial  # noqa: F401 -- cancatlib/__init__.py needs this at import time
    _HAVE_PYSERIAL = True
except ImportError:
    _HAVE_PYSERIAL = False


class FakeCanMessage:
    def __init__(self, arbitration_id=0, data=b"", is_extended_id=False):
        self.arbitration_id = arbitration_id
        self.data = bytearray(data) if isinstance(data, bytes) else list(data)
        self.is_extended_id = is_extended_id
        self.dlc = len(self.data)


class FakeCanBus:
    _send_queue = []
    _sent_frames = []

    def __init__(self, channel="can0", bustype="socketcan", bitrate=500000, receive_own_messages=False):
        self.receive_own_messages = receive_own_messages
        self._alive = True

    def send(self, msg):
        FakeCanBus._sent_frames.append(msg)
        if self.receive_own_messages:
            FakeCanBus._send_queue.append(msg)

    def recv(self, timeout=1.0):
        deadline = time.time() + timeout
        while self._alive:
            try:
                return FakeCanBus._send_queue.pop(0)
            except IndexError:
                if time.time() >= deadline:
                    return None
                time.sleep(0.005)

    def shutdown(self):
        self._alive = False


def _patch_can():
    import sys
    _can_mock = mock.MagicMock()
    _can_mock.Bus = FakeCanBus
    _can_mock.Message = FakeCanMessage
    old_mod = sys.modules.get("can")
    sys.modules["can"] = _can_mock

    import cancatlib.transport as transport_mod
    old_attr = getattr(transport_mod, "can", None)
    transport_mod.can = _can_mock
    return old_mod, old_attr, transport_mod


def _unpatch_can(old_mod, old_attr, transport_mod):
    import sys
    if old_mod is None:
        sys.modules.pop("can", None)
    else:
        sys.modules["can"] = old_mod
    transport_mod.can = old_attr


@unittest.skipUnless(_HAVE_PYSERIAL, "pyserial not installed")
class TestSocketcanUdsResponsePending(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._old_mod, cls._old_attr, cls._transport_mod = _patch_can()

    @classmethod
    def tearDownClass(cls):
        _unpatch_can(cls._old_mod, cls._old_attr, cls._transport_mod)

    def setUp(self):
        FakeCanBus._send_queue.clear()
        FakeCanBus._sent_frames.clear()

    def test_isotp_get_msg_waits_for_next_message_on_rx_arbid(self):
        from cancatlib import CanInterface

        c = CanInterface(port='FakeCanCat', transport='socketcan', socketcan_iface='vcan0')
        try:
            def send_later():
                time.sleep(0.1)
                FakeCanBus._send_queue.append(FakeCanMessage(0x7c8, bytes.fromhex('036edead00000000')))
            threading.Thread(target=send_later, daemon=True).start()

            msg, idx = c._isotp_get_msg(0x7c8, tx_arbid=0x7c0, timeout=2.0)
            self.assertEqual(msg, bytes.fromhex('6edead'))
            self.assertIsNone(idx)  # no mailbox position under socketcan
        finally:
            c._config['shutdown'] = True
            c._transport.close()

    def test_isotprecv_calls_isotp_get_msg(self):
        """Regression test: ISOTPrecv() called self._getIsoTpMsg(), a method
        that has never existed (it's _isotp_get_msg, underscore-prefixed) --
        an AttributeError on every call, since day one of this file back in
        2022. Broken independent of transport, but exercised here over
        socketcan since that's this test module's fixture."""
        from cancatlib import CanInterface

        c = CanInterface(port='FakeCanCat', transport='socketcan', socketcan_iface='vcan0')
        try:
            def send_later():
                time.sleep(0.1)
                FakeCanBus._send_queue.append(FakeCanMessage(0x7c8, bytes.fromhex('036edead00000000')))
            threading.Thread(target=send_later, daemon=True).start()

            msg, idx = c.ISOTPrecv(0x7c0, 0x7c8, timeout=2.0)
            self.assertEqual(msg, bytes.fromhex('6edead'))
            self.assertIsNone(idx)  # no mailbox position under socketcan
        finally:
            c._config['shutdown'] = True
            c._transport.close()

    def test_write_did_survives_response_pending(self):
        """Regression test: a real ECU replying with NRC 0x78
        (ResponseCorrectlyReceivedResponsePending) before its real answer
        must not crash with TypeError: unsupported operand type(s) for
        +: 'NoneType' and 'int'."""
        from cancatlib import CanInterface
        import cancatlib.uds as uds

        c = CanInterface(port='FakeCanCat', transport='socketcan', socketcan_iface='vcan0')
        try:
            u = uds.UDS(c, 0x7c0, timeout=2.0, verbose=False)

            def wait_for_nth_frame(arbid, n, deadline):
                """Wait until at least n frames with this arbid have been sent."""
                while time.time() < deadline:
                    if sum(1 for m in FakeCanBus._sent_frames if m.arbitration_id == arbid) >= n:
                        return True
                    time.sleep(0.01)
                return False

            def ecu_sim():
                deadline = time.time() + 2.0
                # Request is 13 bytes (SID + DID + 10 data bytes) -- multi-frame:
                # FF, then wait for our FC, then 1 CF. A real ECU can't evaluate
                # the request (and so can't reply 0x78/positive/negative) until
                # it has received all of it.
                if not wait_for_nth_frame(0x7c0, 1, deadline):  # the FF
                    return
                FakeCanBus._send_queue.append(FakeCanMessage(0x7c8, bytes.fromhex('3000000000000000')))
                if not wait_for_nth_frame(0x7c0, 2, deadline):  # the CF
                    return

                # NRC 0x78 for WriteDataByIdentifier (0x2e)
                FakeCanBus._send_queue.append(FakeCanMessage(0x7c8, bytes.fromhex('037f2e7800000000')))
                time.sleep(0.1)
                # Real positive response: 0x6e 0xde 0xad
                FakeCanBus._send_queue.append(FakeCanMessage(0x7c8, bytes.fromhex('036edead00000000')))

            threading.Thread(target=ecu_sim, daemon=True).start()

            result = u.WriteDID(0xdead, b'\x11\x22\x33\x44\x55\x66\x77\x88\x99\xaa')
            self.assertEqual(result, bytes.fromhex('6edead'))
        finally:
            c._config['shutdown'] = True
            c._transport.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
