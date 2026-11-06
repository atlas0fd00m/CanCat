"""ISO-TP (ISO 15765-2) stack implemented in the Python layer.

Provides multi-frame message assembly/disassembly with flow control for
SocketCAN mode, where the underlying kernel does not handle ISO-TP natively.

Used by CanCat when communicating via SocketCAN to send and receive ECU
messages larger than 8 bytes (UDS diagnostic requests/responses).
"""
import struct
import sys
import threading
import time


# ---------------------------------------------------------------------------
# ISO-TP constants (ISO 15765-2 PCI type nibble, top 4 bits of byte 0)
# ---------------------------------------------------------------------------

ISO_TP_SA    = 0x00   # Single Frame indicator bit position (bits 7-6)
ISO_TP_FF    = 0x10   # First Frame indicator
ISO_TP_CF    = 0x20   # Consecutive Frame indicator
ISO_TP_FC    = 0x30   # Flow Control indicator
ISO_TP_TS_MASK = 0x0F # Reserved byte / timestamp mask

# Single frame maximum payload (5 bytes type + data)
ISO_TP_SF_MAX_DL = 6

# Flow control status values
ISO_TP_FC_CONTINUE       = 0x00
ISO_TP_FC_WAIT           = 0x01
ISO_TP_FC_OVERFLOW_ERROR = 0x02

# Default flow control parameters
ISO_TP_DS_SEP_DEFAULT    = 0x00   # min. 0 ms between CFs
ISO_TP_BS_DEFAULT        = 0x80   # block size 0 (unlimited)


class IsoTpStack(object):
    """Python-layer ISO-TP stack for SocketCAN transport.

    Handles multi-frame send/receive with flow control negotiation.  Wraps a
    :class:`Transport` instance that provides ``send_raw_can`` and
    ``recv_raw_can`` for single 8-byte CAN frames.
    """

    def __init__(self, transport, rx_id=None, tx_id=None):
        self._transport = transport
        self._rx_id = rx_id or 0x7DF   # arbid we expect the ECU to respond on
        self._tx_id = tx_id or 0x7E8   # arbid we transmit our own frames on
        self._fc_bs = ISO_TP_BS_DEFAULT
        self._fc_st_min = ISO_TP_DS_SEP_DEFAULT
        self._lock = threading.Lock()

    def send(self, arbid, data, extflag=False):
        """Send a (potentially > 8 byte) ISO-TP message.

        Returns ``True`` on success or ``False`` if the ECU responds with an error.
        """
        total_len = len(data)
        if total_len <= ISO_TP_SF_MAX_DL:
            # -- Single Frame --------------------------------------------------
            header = struct.pack("B", ISO_TP_SA | total_len)
            frame_data = header + data[:total_len]
            self._transport.send_raw_can(arbid, frame_data, extflag=extflag)
            return True

        # -- Multi-Frame: First Frame ------------------------------------------
        # ISO 15765-2 packs the length into a 2-byte PCI: the top nibble of
        # byte 0 is the FF type, the bottom nibble + all of byte 1 hold a
        # 12-bit length (0-4095), leaving 6 data bytes in the 8-byte frame.
        # Lengths beyond 4095 use the "escape" form: byte 0/1 = 0x10 0x00
        # followed by a 4-byte length, leaving only 2 data bytes.
        if total_len <= 0xFFF:
            ff_header = struct.pack("BB", ISO_TP_FF | ((total_len >> 8) & 0x0F), total_len & 0xFF)
            first_chunk = data[:6]
            offset = 6
        else:
            ff_header = struct.pack(">BBI", ISO_TP_FF, 0x00, total_len)
            first_chunk = data[:2]
            offset = 2
        ff_payload = ff_header + first_chunk
        self._transport.send_raw_can(arbid, ff_payload, extflag=extflag)

        # -- Wait for the initial Flow Control before sending any CFs ----------
        # Per ISO 15765-2 a Flow Control frame is only expected once per
        # block: BS (block size) CFs get sent back-to-back (paced by STmin),
        # and another FC is only awaited after a full block -- not before
        # every single CF. BS==0 means "no limit", i.e. send everything and
        # never wait for another FC.
        if not self._await_flow_control(timeout=2.0):
            return False

        # -- Send Consecutive Frames, respecting the negotiated block size -----
        block_count = 0
        sn = 1  # sequence number starts at 1 for CF[1]

        while offset < total_len:
            cf_header = struct.pack("B", ISO_TP_CF | (sn & 0x0F))
            cf_payload = cf_header + data[offset:offset + 7]
            self._transport.send_raw_can(arbid, cf_payload, extflag=extflag)

            offset += 7
            sn = (sn + 1) & 0x0F
            block_count += 1

            # Inter-frame delay (STmin conversion)
            st_min_us = self._st_min_to_us(self._fc_st_min or 0)
            if st_min_us > 0:
                time.sleep(st_min_us / 1e6)

            # Block size check -- only wait for another FC once we've sent
            # a full block (and there's more data left to send).
            if self._fc_bs != 0 and block_count >= self._fc_bs and offset < total_len:
                block_count = 0
                if not self._await_flow_control(timeout=2.0):
                    return False

        return True

    def _await_flow_control(self, timeout=2.0):
        """Wait for a Flow Control frame, updating self._fc_bs/_fc_st_min.

        Ignores anything on our rx id that isn't actually PCI-type Flow
        Control (0x3) -- e.g. a negative response left over from a prior
        request, or other traffic -- rather than misparsing it as one; that
        traffic doesn't consume the wait budget for the FC we're actually
        after. Loops on repeated FC_WAIT frames (the ECU asking for more
        time before it's ready for the next block/CF), each restarting the
        wait budget since the ECU explicitly asked for more time. Returns
        True once a CONTINUE is received; False on timeout or overflow, in
        which case the caller should abort the transfer.
        """
        while True:
            deadline = time.time() + timeout
            while True:
                remaining = deadline - time.time()
                if remaining <= 0:
                    print("ISO-TP: timed out waiting for Flow Control", file=sys.stderr)
                    return False
                resp = self._recv_from_ecu(timeout=remaining)
                if resp is None:
                    print("ISO-TP: timed out waiting for Flow Control", file=sys.stderr)
                    return False
                _, frame_data, _ = resp
                if ((frame_data[0] & 0xF0) >> 4) == 0x3:
                    break
                # not a Flow Control frame -- ignore and keep waiting

            fc_status = self._parse_flow_control(frame_data)
            if fc_status == ISO_TP_FC_OVERFLOW_ERROR:
                print("ISO-TP flow control overflow error", file=sys.stderr)
                return False
            if fc_status == ISO_TP_FC_CONTINUE:
                return True
            # else FC_WAIT -- loop and wait for the next FC (fresh budget)

    def receive(self, timeout=5.0, extflag=False):
        """Wait for and assemble an incoming ISO-TP message.

        Returns ``None`` on timeout. Otherwise returns raw response data bytes.
        """
        first_frame = self._recv_from_ecu(timeout=timeout)
        if first_frame is None:
            return None

        arbid, frame_data, frame_extflag = first_frame
        pci_byte = frame_data[0]
        pci_type = (pci_byte & 0xF0) >> 4

        if pci_type == 0x0:
            # -- Single Frame --------------------------------------------------
            length = pci_byte & 0x0F
            return frame_data[1:length + 1]

        elif pci_type == 0x1:
            # -- First Frame (multi-frame) ------------------------------------
            # 2-byte PCI: 12-bit length in (byte0 low nibble, byte1); a
            # length of 0 there means the escape form -- a 4-byte length
            # follows in bytes 2-5, leaving only 2 data bytes (see send()).
            ff_dl = ((pci_byte & 0x0F) << 8) | frame_data[1]
            if ff_dl == 0:
                total_length = struct.unpack(">I", frame_data[2:6])[0]
                accumulated = bytearray(frame_data[6:])
            else:
                total_length = ff_dl
                accumulated = bytearray(frame_data[2:])  # first 6 bytes of data

            sn = 1  # expected sequence number for next CF (CF[1] is first)

            # Tell the ECU we're ready to receive the Consecutive Frames --
            # without this the ECU just times out and never sends them.
            self._send_flow_control(extflag=extflag)

            while len(accumulated) < total_length:
                cf_frame = self._recv_from_ecu(timeout=2.0)
                if cf_frame is None:
                    break
                _, cf_data, _ = cf_frame
                cf_pci_type = (cf_data[0] & 0xF0) >> 4
                if cf_pci_type != 0x2:
                    # Not a Consecutive Frame (stray/duplicate traffic on our
                    # rx id) -- ignore and keep waiting for the real one.
                    continue
                cf_sn = cf_data[0] & 0x0F

                if cf_sn != (sn & 0x0F):
                    print("ISO-TP consecutive frame sequence error", file=sys.stderr)
                    return None

                accumulated += cf_data[1:]   # append payload bytes (7 max per CF)
                sn = (sn + 1) & 0x0F

            else:
                return bytes(accumulated[:total_length])

            # Loop was broken out of (timeout) rather than completing
            return None

        elif pci_type == 0x3:
            # A Flow Control frame is not a valid response payload here --
            # we're the one receiving a response, not sending one.  Ignore it.
            print("ISO-TP: unexpected Flow Control frame while awaiting response", file=sys.stderr)
            return None

    def _recv_from_ecu(self, timeout):
        """Wait up to ``timeout`` seconds for a frame addressed to our rx id.

        Any other traffic on the bus (our own echoed tx frames, other ECUs,
        etc.) is discarded so it can't be mistaken for part of this
        transaction.
        """
        deadline = time.time() + timeout
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                return None
            frame = self._transport.recv_raw_can(timeout=remaining)
            if frame is None:
                return None
            arbid, frame_data, extflag = frame
            if arbid == self._rx_id:
                return frame
            # not addressed to us -- keep waiting for the rest of the budget

    def _parse_flow_control(self, frame_data):
        """Parse and extract flow control parameters.

        Returns the status code (CONTINUE/WAIT/OVERFLOW_ERROR).
        """
        try:
            status_code = frame_data[0] & 0x0F
            bs = frame_data[1]
            st_min_raw = frame_data[2]
        except IndexError:
            return ISO_TP_FC_OVERFLOW_ERROR

        self._fc_bs = bs
        if st_min_raw <= 0x7F:
            self._fc_st_min = st_min_raw    # ms value
        elif st_min_raw >= 0xF1 and st_min_raw <= 0xF9:
            self._fc_st_min = st_min_raw - 0xF1 + 100   # map to centiseconds

        return status_code

    def _st_min_to_us(self, raw):
        """Convert STmin byte value to microseconds."""
        if raw == 0:
            return 0
        elif raw <= 0x7F:
            return int(raw * 1e3)      # ms -> us
        elif raw >= 0xF1 and raw <= 0xF9:
            centiseconds = (raw - 0xF1 + 100)
            return int(centiseconds * 10e3)   # cs to us

    def _send_flow_control(self, extflag=False):
        """Send a Flow Control (clear-to-send) frame back to the ECU."""
        fc_frame = struct.pack("BBB",
                               ISO_TP_FC | ISO_TP_FC_CONTINUE,
                               self._fc_bs,                 # block size
                               self._fc_st_min              # STmin
                              )
        self._transport.send_raw_can(self._tx_id, fc_frame, extflag=extflag)
