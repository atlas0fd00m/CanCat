"""Regression tests for socketcan support in the canmap script
(cancatlib/scripts/canmap.py).

canmap builds its own CanInterface (or a caller-supplied subclass via
-u/--uds-class) directly from parsed args rather than going through
cancatlib.interactive(), so it needed its own --socketcan wiring separate
from CanCat/J1939Cat. This covers:
  * --socketcan is accepted by the argument parser (and doesn't collide
    with -s/--scan, which already owns the short flag).
  * canmap.main() actually constructs the interface with
    transport='socketcan' / socketcan_iface=<IFACE> when --socketcan is
    given, instead of the default port-based serial construction.
  * A full canmap run (ECU scan) over socketcan completes without
    crashing when no ECUs are present on the bus.

Like tests/test_socketcan_uds.py these import cancatlib itself (pyserial
required), so they're skipped rather than failing outright if that's not
available.

Run:  python -m unittest tests.test_socketcan_canmap -v
"""
import sys
import time
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
        self.channel = channel
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
    if old_mod is None:
        sys.modules.pop("can", None)
    else:
        sys.modules["can"] = old_mod
    transport_mod.can = old_attr


@unittest.skipUnless(_HAVE_PYSERIAL, "pyserial not installed")
class TestCanmapSocketcan(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._old_mod, cls._old_attr, cls._transport_mod = _patch_can()

    @classmethod
    def tearDownClass(cls):
        _unpatch_can(cls._old_mod, cls._old_attr, cls._transport_mod)

    def setUp(self):
        FakeCanBus._send_queue.clear()
        FakeCanBus._sent_frames.clear()

    def test_parse_args_accepts_socketcan(self):
        from cancatlib.scripts import canmap

        argv = ['canmap', '-s', 'E', '--socketcan', 'vcan0']
        with mock.patch.object(sys, 'argv', argv):
            args = canmap.udsmap_parse_args()
        self.assertEqual(args.socketcan, 'vcan0')
        self.assertEqual(args.scan, ['E'])

    def test_main_constructs_interface_with_socketcan_transport(self):
        from cancatlib import CanInterface
        from cancatlib.scripts import canmap

        argv = ['canmap', '-s', 'E', '--socketcan', 'vcan0', '-E', '01-02', '-T', '0.05']
        with mock.patch.object(sys, 'argv', argv):
            try:
                canmap.main()
            except SystemExit as e:
                self.assertEqual(e.code, 0)
            else:
                self.fail('canmap.main() should call sys.exit()')

        # canmap.main() stashes the constructed interface on the module global
        self.assertIsInstance(canmap.c, CanInterface)
        self.assertEqual(canmap.c.transport_mode, 'socketcan')
        # An empty simulated bus should yield no discovered ECUs, not a crash
        self.assertEqual(canmap._config['ECUs'], {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
