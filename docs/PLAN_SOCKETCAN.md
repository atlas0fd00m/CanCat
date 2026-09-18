# PLAN: Add SocketCAN Transport Support to CanCat

## Background

CanCat currently communicates with a dedicated USB-connected firmware device (the CanCat transceiver) over serial. The firmware handles all CAN bus physical layer operations and ISO-TP flow control internally, exposing a simple custom binary protocol (`@<size><cmd><payload>`) over the serial port to the Python client.

This plan describes adding **socketcan** as an alternative transport mode, allowing CanCat to operate directly against Linux socketCAN interfaces (e.g., `vcan`, `can0`, or hardware adapters like PEAK/Sonoelectrics supported by kernel drivers). This enables using CanCat tools without any dedicated firmware device, at the cost of moving ISO-TP flow control from firmware into Python.

**Key principle:** Full backward compatibility. No existing behavior changes for users operating in serial mode. All `CanInterface` subclasses (`FordInterface`, `GMInterface`, `J1939`, etc.) continue unchanged.

---

## Phase 1: Transport Abstraction Layer (`cancatlib/transport.py`)

Introduce a transport layer that isolates the physical communication mechanism from CanCat's higher-level CAN logic. This lets us swap serial ↔ socketcan with minimal changes elsewhere.

### Step 1.1 — Define abstract base class `Transport`

Create `cancatlib/transport.py` and define:

```python
from abc import ABC, abstractmethod

class Transport(ABC):
    """Abstract transport layer for CAN communication."""

    @abstractmethod
    def open(self) -> None: ...        # Open the underlying connection (serial port / socketcan bus).
    @abstractmethod
    def close(self) -> None: ...       # Close and release resources.

    @abstractmethod
    def send_raw_can(self, arbid: int, data: bytes, extflag: bool = False) -> int:
        """Send a single CAN frame (no flow-control). Returns byte count or status."""

    @abstractmethod
    def recv_raw_can(self, timeout: float) -> tuple[int, bytes, bool]:
        """Block up to `timeout` seconds for the next CAN frame.
        Returns (arbid, data_bytes, extflag) or None on timeout."""

    # Convenience alias preferred by CanInterface:
    @abstractmethod
    def xmit_raw_can(self, arbid: int, data: bytes, extflag: bool = False) -> int:
        """Send-and-return variant (may include acknowledgment for serial path)."""

```

**Design rationale:**
- `send_raw_can` / `recv_raw_can` are the symmetric low-level operations.
- `xmit_raw_can` is preserved as a drop-in alias because the existing CanInterface code already calls it via `_io.write()` + response pattern in some paths.
- The layer operates on **raw CAN frames** (single 11-byte max). ISO-TP segmentation and flow control sit *above* this layer.

### Step 1.2 — Implement `SerialTransport`

Extract the current serial-path logic from `CanInterface._reconnect()`, `_rxtx()`, and `_send()` into a dedicated transport class:

```python
import serial
import threading

class SerialTransport(Transport):
    """Transport over CanCat's custom serial binary protocol."""

    FRAMING_PREFIX = None   # '@' byte for command framing
    CMD_CAN_XMIT     = 0x30  # (or whatever hex values the firmware uses)
    CMD_PING         = 0x...
    CMD_CHANGE_BAUD  = 0x...
    # ... constants currently in __init__.py ...

    def __init__(self, port: str, baud: int = 4_000_000):
        self.port = port
        self.baud = baud
        self._io: serial.Serial | None = None
        self._lock = threading.Lock()
        # ...

    def open(self) -> None:
        """Open the serial port, send ping handshake, configure CAN baud."""
        ...

    def close(self) -> None:
        if self._io and self._io.is_open:
            self._io.close()

    # --- internal helpers (extracted from CanInterface) ---

    def _send(self, cmd: int, payload: bytes = b'') -> bytes:
        """Frame a command as @<size><cmd><payload> over serial."""
        ...

    def recv_response(self, timeout: float = 0.5) -> bytes:
        """Read response from firmware, handle framing and checksums."""
        ...

    # --- Transport ABC methods ---

    def send_raw_can(self, arbid: int, data: bytes, extflag: bool = False) -> int:
        """Encode CAN frame in serial protocol payload, send to device."""
        self._send(CMD_CAN_XMIT, struct.pack(...) + bytes([arbid ...]) + data)
        return 0

    def xmit_raw_can(self, arbid: int, data: bytes, extflag: bool = False) -> int:
        """Send frame and read device acknowledgment."""
        self.send_raw_can(arbid, data, extflag)
        response = self.recv_response()
        return ...  # status byte or byte count

    def recv_raw_can(self, timeout: float) -> tuple[int, bytes, bool]:
        """Read from serial receive buffer (populated by _rxtx receiver thread)."""
        with self._lock:
            # Use select.poll on the serial fd for timed reads.
            ...

```

**Key extraction decisions:**
- `_reconnect()` → logic folds into `SerialTransport.open()`.
- `_send()` → becomes `SerialTransport._send()` (private helper, not part of ABC).
- The serial receiver thread (`_rxtx()` receiver half) either lives in `SerialTransport` or stays at the `CanInterface` level depending on whether subclasses expect it. **Recommendation:** move the receive loop into `SerialTransport.open()` as a daemon thread that pushes frames into an internal queue; `recv_raw_can()` pulls from that queue with timeout support via `select()`.

**Backward-compatibility check:** After extraction, instantiating `CanInterface` in serial mode must produce byte-for-byte identical wire behavior. The only change is *where* the code lives.

### Step 1.3 — Implement `SocketcanTransport`

A simple transport backed by **python-can**'s socketcan backend:

```python
import can   # python-can library

class SocketcanTransport(Transport):
    """Direct Linux socketCAN transport via python-can."""

    def __init__(self, channel: str = 'can0'):
        self.channel = channel
        self._bus: can.BusABC | None = None

    def open(self) -> None:
        self._bus = can.Bus(bustype='socketcan', channel=self.channel)

    def close(self) -> None:
        if self._bus:
            self._bus.shutdown()
            self._bus = None

    def send_raw_can(self, arbid: int, data: bytes, extflag: bool = False) -> int:
        frame = can.Message(arbitration_id=arbid,
                            data=list(data),
                            is_extended_id=extflag)
        self._bus.send(frame)
        return len(data)

    def xmit_raw_can(self, arbid: int, data: bytes, extflag: bool = False) -> int:
        # Same as send_raw_can for socketcan — no separate ack handshake.
        return self.send_raw_can(arbid, data, extflag)

    def recv_raw_can(self, timeout: float) -> tuple[int, bytes, bool] | None:
        frame = self._bus.recv(timeout=timeout)  # python-can blocks internally
        if frame is None:
            return None
        return (frame.arbitration_id, bytes(frame.data[:frame.dlc]), frame.is_extended_id)

```

**No receiver thread** needed here — `can.Bus.recv()` already supports blocking with timeout natively (libsocketcan's blocking read). This simplifies the code enormously compared to the serial path.

### Step 1.4 — Smoke-test both transports independently

Before touching CanInterface, verify each transport in isolation:

- **SerialTransport**: Ensure it connects to a plugged-in CanCat device and successfully pings/reads frames. (Integration test — requires hardware.)
- **SocketcanTransport**: Create `vcan0`, write/read CAN frames via `ip link` + python-can on a second thread/process, confirm `_recv_raw_can()` returns them correctly.

---

## Phase 2: ISO-TP Flow Control in Python (`cancatlib/isotp_stack.py`)

Currently the CanCat firmware handles ISO-TP (ISO 15765-2) flow control for multi-frame messages. In socketcan mode, there is no firmware — we need to do this entirely in Python using the `isotp.Protocol` class from the **python-isotp** library (already installed in .venv).

### Step 2.1 — Create `cancatlib/isotp_stack.py`

Design a thin wrapper that presents clean synchronous functions for CAN-ISOTP send/recv over any transport:

```python
"""ISO-TP stack helpers wrapping isotp.Protocol for socketcan mode."""

import isotp
from .transport import Transport
```

**Why a wrapper instead of calling `isotp.Protocol` directly:** The `isotp.Protocol` class expects `send()` callbacks that accept raw CAN frames, but our transports operate through the shared `Transport.send_raw_can()` / `recv_raw_can()` interface. Our functions set up the correct Protocol instances and tie them together with TX/RX IDs.

### Step 2.2 — Implement core function: `send_isotp(transport, tx_id, rx_id, data)`

```python
import struct
import time
from enum import IntEnum

class IsoTPError(Exception): ...

def send_isotp(transport: Transport, tx_id: int, rx_id: int,
               data: bytes, timeout: float = 5.0) -> iso_tp.CanIsoMsgException | None:
    """Send an ISO-TP message (handles single-frame and multi-frame segmentation)."""
```

**Implementation approach:**

1. If `len(data) <= 7`, send as a **single frame** (SF): `transport.send_raw_can(rx_id, bytes([0x00 | len(data)] + data))`. Done.
2. Otherwise:
   - Create an `isotp.Protocol` sender using the transport for TX and a dummy receiver:

     ```python
     protocol = isotp.Protocol(
         tx_path=functools.partial(transport.send_raw_can, extflag=False),
         rx_path=_read_response_callback,  # reads from transport.recv_raw_can()
     )
     ```

   - The Protocol handles frame numbering, sends FF (first frame) with total length, receives FC (flow control) back, then streams CF (consecutive frames) respecting **BS** (block size) and **STmin** (separation time minimum).
   - After transmitting all data, verify the sender status is complete.

3. On timeout or error, raise `IsoTPError`.

### Step 2.3 — Implement: `recv_isotp(transport, tx_id, rx_id)`

```python
def recv_isotp(transport: Transport, tx_id: int, rx_id: int,
               timeout: float = 5.0) -> bytes:
    """Receive an ISO-TP message (reads SF/FF+CF frames, handles flow control)."""
```

**Implementation approach:**

1. Build `isotp.Protocol` with the transport — this time we *listen* on `tx_id` for incoming messages and send FC responses from `rx_id`.
2. The Protocol class automatically:
   - Reads SF/FF frames arriving from TX ID (our RX path).
   - On FF, sends an **FC (Flow Control)** frame to the TX side with configurable STmin/BS.
   - Assembles consecutive CF frames into a complete message.
3. Call `protocol.send(b'')` or similar to start the receive handshake if needed (some python-isotp APIs require triggering). Or use `isotp.recv()` pattern where we just pass `tx_path` and `rx_path`.
4. Return assembled bytes when complete, or raise on timeout.

**Important nuance:** For socketcan mode we must send FC (Flow Control) frames **back-to-back** as responses to FF (First Frame). The `isotp.Protocol` class handles this internally via its `tx_path` callback — our wrapper just needs to wire it up so TX writes go to our transport.

### Step 2.4 — Implement: `sendrecv_isotp(transport, tx_id, rx_id, request_data)`

```python
def sendrecv_isotp(transport: Transport, tx_id: int, rx_id: int,
                   request_data: bytes, timeout: float = 5.0) -> bytes:
    """Send an ISO-TP request and return the response (request-response pattern)."""
```

1. Call `send_isotp()` with `rx_id` as destination for the request.
2. Immediately call `recv_isotp()` listening on `tx_id` for the response.
3. Return the received response bytes.

### Step 2.5 — Implement: `sniff_isotp(transport, tx_id, rx_id)` (optional / advanced)

For modes where we want to passively capture ISO-TP traffic:

```python
def sniff_isotp(transport: Transport, rx_id: int, timeout: float = 1.0) -> bytes | None:
    """Passively reassemble ISO-TP messages without sending flow control.
    Use case: listening where the device already handles FC."""
```

May use `cancatlib.iso_tp`'s existing static decode logic for single-frame, or a simplified Protocol in passive mode.

### Step 2.6 — Edge cases to handle explicitly

- **STmin = 0**: Some ECUs specify zero millisecond separation time between CF frames. Must support burst sends (no `time.sleep()`).
- **BS = 0**: Block size of zero means "send all remaining frames without flow control." Protocol must detect this and pump the entire message after receiving FF+FC(BC=0)+STmin=0.
- **Partial messages / timeouts**: If FC is not received within timeout, discard partial buffer and raise an error. Don't leave stale state in the transport or protocol object.
- **Multi-session isolation**: Each call to `send_isotp()`/`recv_isotp()` must use a *fresh* Protocol instance so async operations don't interfere (socketcan mode is single-threaded blocking, but callers may run in threads).

---

## Phase 3: CanInterface Integration

Wire the transport layer and ISO-TP stack into the existing `CanInterface` class at `cancatlib/__init__.py`.

### Step 3.1 — Modify `CanInterface.__init__()` signature

```python
def __init__(self, port=None, baud=baud, verbose=False, cmdhandlers=None,
             comment='', load_filename=None, orig_iface=None, max_msgs=None,
             transport='serial', socketcan_iface=None):
    '''CAN Analysis Workspace.

    Args:
        ...  (existing args unchanged)
        transport: 'serial' or 'socketcan'. Default 'serial' for backward compat.
        socketcan_iface: Interface name for socketcan mode (e.g., 'vcan0', 'can0').
    '''
```

Backward compatibility guarantee: All existing positional and keyword arguments remain in the same order and keep their defaults. Only new **keyword-only** additions appended at the end.

### Step 3.2 — Instantiate transport based on mode

Inside `__init__`, after logging setup but before any CAN bus operations:

```python
from .transport import SerialTransport, SocketcanTransport

if self.transport_mode == 'serial':
    if port is None:
        raise ValueError('port required for serial transport')
    self._transport = SerialTransport(port=port, baud=self.can_baud)
elif self.transport_mode == 'socketcan':
    iface = socketcan_iface if socketcan_iface else 'vcan0'
    self._transport = SocketcanTransport(channel=iface)
else:
    raise ValueError(f"Unsupported transport mode: {self.transport_mode!r}")

# Open the connection (handshake for serial, bus init for socketcan).
self._transport.open()
```

### Step 3.3 — Route `CANxmit()` through transport layer

**Existing code path (serial):**  
`CANxmit(msg)` already handles sending raw CAN frames via the `_io` serial writer and reading back results.

**New polymporphic design:**

```python
def CANxmit(self, message):
    """Send a single CAN frame. `message = [arbid, data_bytes]."""
    (arbid, data) = message[0], bytes(message[1])  # normalize input
    if self.transport_mode == 'serial':
        return self._transport.xmit_raw_can(arbid, data)
    else:
        return self._transport.send_raw_can(arbid, data)
```

Keep the existing `CANxmit` signature and message format. Internal dispatch to `self._transport`.

### Step 3.4 — Rewrite `ISOTPxmit()` / `ISOTPrecv()` / `ISOTPxmit_recv()` as polymorphic methods

These three methods currently invoke firmware-level ISO-TP commands (the device handles segmentation, flow control, and reassembly). We need them to work with both transports:

```python
from . import isotp_stack

def ISOTPxmit(self, data, IDtx=None, IDrx=None):
    """Send multi-frame ISO-TP message."""
    if self.transport_mode == 'serial':
        # Existing code — sends via firmware command.
        ...   # unchanged
    else:
        return isotp_stack.send_isotp(
            self._transport, tx_id=IDtx, rx_id=IDrx, data=data
        )

def ISOTPrecv(self, addr=None):
    """Receive ISO-TP message with flow control."""
    if self.transport_mode == 'serial':
        # Existing code — queries firmware.
        ...   # unchanged
    else:
        return isotp_stack.recv_isotp(
            self._transport, tx_id=addr[0], rx_id=addr[1]  # or however IDs are passed
        )

def ISOTPxmit_recv(self, data, IDtx=None, IDrx=None):
    """Request-response via ISO-TP."""
    if self.transport_mode == 'serial':
        ...   # unchanged — firmware handles both sides.
    else:
        return isotp_stack.sendrecv_isotp(
            self._transport, tx_id=IDtx, rx_id=IDrx, request_data=data
        )
```

**Key design: the existing serial path stays completely untouched.** Only socketcan mode routes through `isotp_stack.py`. This means regression risk to the serial path is near-zero.

### Step 3.5 — Handle receiver thread removal for socketcan

The existing `_rxtx()` method spawns a background daemon thread that reads from serial and parses CAN frames into internal buffers (`self.rxbuf`, etc.). In socketcan mode:

- **No receiver thread needed.** Blocking `recv_raw_can(timeout)` in the transport already handles framing.
- For methods like `sniff()`, `CANreceive()`, etc., replace direct `_io.read()` calls with `self._transport.recv_raw_can()`.
- Add a guard: Do **not** start `_rxtx()` when `self.transport_mode == 'socketcan'`.

```python
# In __init__:
if self.transport_mode == 'serial':
    # Start the existing receiver thread.
    ...   # unchanged
elif self.transport_mode == 'socketcan':
    pass  # No background reader needed — blocking transport reads suffice.
```

### Step 3.6 — Update `ping()`, reconnect logic, and cleanup

- **`CanInterface.ping()`**: Currently sends a ping command to firmware. For socketcan, override or short-circuit this (no device to ping). Option: check bus availability via transport.
- **Reconnect / `_reconnect()`**: Only meaningful for serial. Skip entirely in socketcan mode.
- **Destructor / cleanup**: Close `self._transport` on exit if open (use `atexit` or context manager pattern).

### Step 3.7 — Verify subclasses are unaffected

All `CanInterface` subclasses (`FordInterface`, `GMInterface`, `J1939`, etc.) call the parent `__init__()` and override specific methods. Since we only appended keyword arguments:

```python
class FordInterface(CanInterface):
    def __init__(self, ...):
        super().__init__('COM4', verbose=True)   # still works identically
```

Confirm by inspecting each subclass's `super().__init__()` call — none should break. If a subclass passes new kwargs via `**kwargs`, add `**kwargs` to our expanded signature for future safety.

---

## Phase 4: CLI Integration

### Step 4.1 — Add `--socketcan IFACE` argument to CanCat entry point

In `CanCat` (the main script at the repo root):

```python
parser.add_argument('-s', '--socketcan', metavar='IFACE',
                    help='Use socketcan interface instead of serial device '
                         '(e.g., can0, vcan0)')
```

### Step 4.2 — Wire argument through to CanInterface construction

The entry point currently calls `interactive()` with the parsed args:

```python
# Existing line (approximate):
results = interactive(ifo.port, intro=intro, InterfaceClass=interface,
                      load_filename=ifo.filename, can_baud=baud_val)
```

Update to pass transport mode info through the appropriate parameter path (either via `interactive()` or directly to CanInterface):

```python
transport_args = {}
if ifo.socketcan:
    # --socketcan overrides --port; device is a network interface not a serial port.
    transport_args['transport'] = 'socketcan'
    transport_args['socketcan_iface'] = ifo.socketcan
else:
    assert ifo.port, "--port required (not using --socketcan)"

results = interactive(..., **kwargs_to_pass_transport)  # adapt interactive() accordingly
```

If `interactive()` in `__init__.py` directly instantiates CanInterface, pass the new kwargs through to it.

### Step 4.3 — Update dependency declarations

In `setup.py`:

```python
install_requires = [
    "ipython",
    "pyserial",                 # only needed for serial mode
    "pyusb",
    "termcolor",
    "future",
    "six",
    "isotp>=1.0",              # NEW: ISO-TP flow control stack (socketcan mode)
],

extras_require = {
    'socketcan': [
        'python-can>=4.0',     # NEW: socketcan backend + more
    ],
},
```

**Rationale for dependency placement:**
- `isotp` → top-level because the UDS scanner (`cancatlib/uds`) and core CanInterface already use ISO-TP concepts internally; it's lightweight (~25 KB).
- `python-can` → optional extra because: (a) serial-only users don't need it, (b) it pulls in Cython bindings that aren't built on all platforms by default.

### Step 4.4 — Import-time guards for socketcan dependencies

To avoid "python-can not installed" errors when running CanCat without the `socketcan` extra:

```python
# In cancatlib/transport.py or __init__.py
def _get_socketcan_transport(iface):
    try:
        from .transport import SocketcanTransport
        return SocketcanTransport(channel=iface)
    except ImportError as e:
        raise RuntimeError(
            "socketcan transport requires 'python-can'. Install with: "
            "pip install cancat[socketcan]"
        ) from e

def _get_isotp_stack():
    try:
        from . import isotp_stack
        return isotp_stack
    except ImportError as e:
        raise RuntimeError(
            "ISO-TP stack requires the 'isotp' library. Install with: "
            "pip install isotp"
        ) from e
```

---

## Phase 5: Testing

### Step 5.1 — Infrastructure: virtual CAN interface for testing

Before running tests, set up a `vcan` interface on Linux:

```bash
sudo modprobe vcan          # Load kernel module if not loaded
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0
# Verify it exists:
ip -details link show vcan0
```

The `vcan` interface supports loopback (frames sent on one end can be read by another process/reader on the same endpoint). This is ideal for unit testing without physical CAN hardware.

### Step 5.2 — Unit test: SocketcanTransport basic send/recv

```python
# tests/test_socketcan_transport.py
import threading, time, socket
from cancatlib.transport import SocketcanTransport

def test_send_recv_vcan():
    """Send a CAN frame on one end of vcan0 and read it on the other."""
    t1 = SocketcanTransport('vcan0')
    t2 = SocketcanTransport('vcan0')   # Both read from same interface.
    t1.open()
    t2.open()

    data = b'\xde\xad\xbe\xef'
        
    def sender():
        time.sleep(0.1)  # Let receiver start first.
        t1.send_raw_can(arbid=0x7DF, data=data, extflag=False)

    threading.Thread(target=sender, daemon=True).start()
    result = t2.recv_raw_can(timeout=2.0)
    
    assert result is not None
    arbid_rx, data_rx, ext_rx = result
    assert arbid_rx == 0x7DF
    assert list(data_rx)[:4] == [0xde, 0xad, 0xbe, 0xef]
    assert ext_rx == False

    t1.close()
    t2.close()
```

### Step 5.3 — Unit test: ISO-TP flow control through isotp_stack.py

```python
def test_isotp_multiframe():
    """Send a 16-byte message (requires FF+CF frames) and verify FC handling."""
    from cancatlib.isotp_stack import sendrecv_isotp
    
    t_tx = SocketcanTransport('vcan0')
    t_rx = SocketcanTransport('vcan0')
    t_tx.open()
    t_rx.open()

    # Large payload > 7 bytes, forces multi-frame ISO-TP.
    payload = bytes(range(256))

    def responder():
        """Receive the request and send back a response."""
        ...   # See Step 5.4 for full implementation sketch.

    ...
```

Verify:
- Sender segments into FF (First Frame) + CFs (Consecutive Frames).
- Receiver sends FC (Flow Control) with valid BS and STmin before accepting CFs.
- Complete payload reassembled correctly on the receiving end.
- `sendrecv_isotp()` round-trips without data loss or corruption.

### Step 5.4 — Integration test: CanInterface with socketcan transport

```python
def test_caninterface_socketcan():
    """End-to-end: Create a CanInterface using socketcan, CANxmit and receive."""
    from cancatlib import CanInterface
    
    c = CanInterface(transport='socketcan', socketcan_iface='vcan0')
    
    # Raw frame transmit + loopback receive (on vcan, send is readable by same bus).
    arb_id = 0x123
    msg_data = b'\x01\x02\x03'
    c.CANxmit([arb_id, msg_data])

    result = c._transport.recv_raw_can(timeout=1.0)
    assert result[0] == arb_id
    assert list(result[1])[:3] == [0x01, 0x02, 0x03]
```

### Step 5.5 — Regression test: existing serial tests still pass

Run the full existing CanCat test suite with no modifications to confirm zero behavioral change to the serial path:

```bash
./venv/bin/python -m pytest tests/ -k "not socketcan" --ignore=tests/test_socketcan_transport.py --ignore=tests/test_isotp_stack.py -v
```

All pre-existing tests should pass. If any regress, the transport extraction in Phase 1 broke backwards compat — fix before proceeding.

---

## File Structure After Implementation

```
cancatlib/
├── __init__.py          # Modified: CanInterface accepts transport params, routes CAN methods polymorphically.
├── iso_tp.py            # Unchanged — static ISO-TP encode/decode helpers.
├── isotp_stack.py       # NEW — Full ISO-TP flow control using python-isotp (socketcan mode).
├── transport.py         # NEW — Transport ABC + SerialTransport + SocketcanTransport.
└── ...                  # Existing submodules (uds, etc.) unchanged for serial path.

docs/
└── PLAN_SOCKETCAN.md    # This plan document.

tests/
├── test_socketcan_transport.py   # NEW — SocketcanTransport unit tests via vcan0.
└── test_isotp_stack.py           # NEW — ISO-TP flow control integration tests via vcan0.

CanCat                        # Modified: Added --socketcan CLI argument.
setup.py                      # Modified: Added isotp, python-can[socketcan] dependencies.
```

---

## Risk Assessment and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Serial transport regression from extraction to `SerialTransport` | High | Keep serial branch code identical to original; no logic changes unless bug fixes explicitly tested against hardware. Fallback: keep original methods as legacy path behind the same ABC calls. |
| `isotp.Protocol` API incompatibility with our callback pattern | Medium | Wrap all Protocol usage inside helper functions; don't expose protocol internals. Keep only one version of python-isotp pinned in deps. |
| Subclass breaking from `__init__()` signature change | Low | Only append keyword-only arguments after existing positional args — verified by inspecting all subclass `super().__init__()`. |
| Blocking serial operations (e.g., `.recv(timeout=0)` means "non-blocking"). Our wrapper must preserve these semantics. |
