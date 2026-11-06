"""Tests for socketcan support in CanInterface's cmdhandler dispatch and in
J1939Interface -- both needed for J1939Cat -s <iface> to actually process
messages live (PGN/TP reassembly, myIDs filtering) rather than just log raw
frames.

Unlike tests/test_transport.py these tests import cancatlib itself (pyserial
required), so they're skipped rather than failing outright if that's not
available in a given environment.

Run:  python -m unittest tests.test_socketcan_j1939 -v
"""
import struct
import time
import unittest
from unittest import mock

try:
    import serial  # noqa: F401 -- cancatlib/__init__.py needs this at import time
    _HAVE_PYSERIAL = True
except ImportError:
    _HAVE_PYSERIAL = False


class FakeCanMessage:
    """Minimal fake can.Message for testing."""
    def __init__(self, arbitration_id=0, data=b"", is_extended_id=False):
        self.arbitration_id = arbitration_id
        self.data = bytearray(data) if isinstance(data, bytes) else list(data)
        self.is_extended_id = is_extended_id
        self.dlc = len(self.data)


class FakeCanBus:
    """Fake can.Bus with send/recv for in-process testing."""

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
class TestSocketcanCmdHandlerDispatch(unittest.TestCase):
    """CanInterface._socketcan_rx_loop must dispatch through self._cmdhandlers
    (like the serial _rxtx() loop does) instead of always filing frames into
    the generic CMD_CAN_RECV mailbox -- otherwise a subclass that registers a
    live handler (e.g. J1939Interface) never sees socketcan traffic."""

    @classmethod
    def setUpClass(cls):
        cls._old_mod, cls._old_attr, cls._transport_mod = _patch_can()

    @classmethod
    def tearDownClass(cls):
        _unpatch_can(cls._old_mod, cls._old_attr, cls._transport_mod)

    def setUp(self):
        FakeCanBus._send_queue.clear()
        FakeCanBus._sent_frames.clear()

    def test_registered_handler_is_invoked_for_socketcan_frames(self):
        from cancatlib import CanInterface, CMD_CAN_RECV

        c = CanInterface(port='FakeCanCat', transport='socketcan', socketcan_iface='vcan0')
        try:
            seen = []
            c.register_handler(CMD_CAN_RECV, lambda tsmsg, canbuf: seen.append(tsmsg))

            FakeCanBus._send_queue.append(FakeCanMessage(0x123, b"\xDE\xAD\xBE\xEF"))
            deadline = time.time() + 2.0
            while not seen and time.time() < deadline:
                time.sleep(0.02)

            self.assertEqual(len(seen), 1)
            ts, msg = seen[0]
            arbid = struct.unpack('>I', msg[:4])[0]
            self.assertEqual(arbid, 0x123)
            self.assertEqual(msg[4:], b"\xDE\xAD\xBE\xEF")

            # A registered handler means CMD_CAN_RECV is NOT double-filed
            # into the generic mailbox -- matches the serial _rxtx() behavior.
            self.assertEqual(c._messages.get(CMD_CAN_RECV, []), [])
        finally:
            c._config['shutdown'] = True
            c._transport.close()


@unittest.skipUnless(_HAVE_PYSERIAL, "pyserial not installed")
class TestJ1939InterfaceSocketcan(unittest.TestCase):
    """J1939Interface must accept and forward transport/socketcan_iface so
    J1939Cat -s <iface> can construct it (previously TypeError'd -- its
    __init__ didn't accept those kwargs at all)."""

    @classmethod
    def setUpClass(cls):
        cls._old_mod, cls._old_attr, cls._transport_mod = _patch_can()

    @classmethod
    def tearDownClass(cls):
        _unpatch_can(cls._old_mod, cls._old_attr, cls._transport_mod)

    def setUp(self):
        FakeCanBus._send_queue.clear()
        FakeCanBus._sent_frames.clear()

    def test_constructs_with_socketcan_transport(self):
        from cancatlib.j1939stack import J1939Interface

        j = J1939Interface(port='FakeCanCat', transport='socketcan', socketcan_iface='vcan0')
        try:
            self.assertEqual(j.transport_mode, 'socketcan')
        finally:
            j._config['shutdown'] = True
            j._transport.close()

    def test_j1939_handler_fires_for_live_socketcan_frames(self):
        from cancatlib.j1939stack import J1939Interface, J1939MSGS
        from cancatlib.j1939 import emitArbid

        j = J1939Interface(port='FakeCanCat', transport='socketcan', socketcan_iface='vcan0')
        try:
            # priority=6, edp=0, dp=0, PF=0xFE (broadcast PGN), PS=0xF0, SA=0x01
            arbid = emitArbid(6, 0, 0, 0xFE, 0xF0, 0x01)
            FakeCanBus._send_queue.append(
                FakeCanMessage(arbid, b"\x01\x02\x03\x04\x05\x06\x07\x08", is_extended_id=True))

            deadline = time.time() + 2.0
            mbox = []
            while not mbox and time.time() < deadline:
                mbox = j._messages.get(J1939MSGS, [])
                time.sleep(0.02)

            self.assertEqual(len(mbox), 1)
        finally:
            j._config['shutdown'] = True
            j._transport.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
