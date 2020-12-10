import time
import struct

from cancat.uds import NegativeResponseException
from cancat.uds.ecu import ScanClass

class CanInterface(object):
    """
    A fake CanInterface class for test purposes.

    All actual functions are just stubbed out, this is not a superclass of the
    real cancat.CanInterface class.
    """
    def __init__(self, *args, **kwargs):
        # required to make canmap think the bus is working
        self.msg_count = 1

    def setCanBaud(self, *args, **kwargs):
        pass

    def placeCanBookmark(self, *args, **kwargs):
        pass

    def saveSessionToFile(self, *args, **kwargs):
        pass

    def getCanMsgCount(self):
        count = self.msg_count
        self.msg_count += 1
        return count

    def genCanMsgs(self, start=0, stop=None, arbids=None, tail=False, maxsecs=None):
        return []


class TestUDS(ScanClass):
    DIDs = {
        0x711: {
            0x0042: '\x62\x00\x42ANSWER',
        },
        0x7E0: {
            0xE010: '\x62\xE0\x10VERSION 1.2.3',
            0xF190: '\x62\xF1\x901AB123CD1EF123456',
        },
    }

    SEEDs = {
        0x711: {
            2: {
                1: 'SEED',
            }
        },
        0x7E0: {
            2: {
                1: 'FOOD',
            },
            5: {
                3: 'SEEDSEED',
            }
        },
    }

    def __init__(self, c, tx_arbid, rx_arbid=None, verbose=True, extflag=0, timeout=3.0):
        super(TestUDS, self).__init__(c, tx_arbid, rx_arbid, verbose=verbose, extflag=extflag, timeout=timeout)
        self._session = 1
        if self.tx_arbid in TestUDS.DIDs and extflag == False:
            self._dids = TestUDS.DIDs[self.tx_arbid]
        else:
            self._dids = {}

        if self.tx_arbid in TestUDS.SEEDs and extflag == False:
            self._sessions = TestUDS.SEEDs[self.tx_arbid]
        else:
            self._sessions = {}

    def ReadDID(self, did):
        if did in self._dids:
            return self._dids[did]
        elif self._dids:
            # 0x31:'RequestOutOfRange',
            raise NegativeResponseException(
                        0x31, 0x22, struct.pack('>BHB', 0x27, did, 0x31))
        else:
            # Using this timeout makes the test appear more realistic, but that 
            # is silly for testing
            #time.sleep(self.timeout)
            return None

    def WriteDID(self, did, data):
        pass

    def StartTesterPresent(self, request_response=True):
        pass

    def StopTesterPresent(self):
        pass

    def DiagnosticSessionControl(self, session):
        self._session = session
        if session in self._sessions:
            return struct.pack('>BB', 0x50, session)
        elif self._sessions:
            # 0x12:'SubFunctionNotSupported',
            raise NegativeResponseException(
                    0x12, 0x10, struct.pack('>BBB', 0x10, session, 0x12))
        else:
            # Using this timeout makes the test appear more realistic, but that 
            # is silly for testing
            #time.sleep(self.timeout)
            return None

    def RequestDownload(self, addr, data, data_format = 0x00, addr_format = 0x44):
        pass

    def RequestUpload(self, addr, length, data_format = 0x00, addr_format = 0x44):
        pass

    def readMemoryByAddress(self, address, length, lenlen=1, addrlen=4):
        pass

    def writeMemoryByAddress(self, address, data, lenlen=1, addrlen=4):
        pass

    def EcuReset(self, rst_type=0x1):
        pass

    def SecurityAccess(self, level, key):
        if self._session in self._sessions and \
                level in self._sessions[self._session]:
            seed = self._sessions[self._session][level]
            self._key_from_seed(seed, key)
            if key == seed:
                return struct.pack('>BB', 0x67, level + 1)
            elif len(key) == len(seed):
                # 0x35:'InvalidKey',
                raise NegativeResponseException(
                        0x35, 0x27, struct.pack('>BBB', 0x27, level+1, 0x35))
            else:
                # 0x13:'IncorrectMesageLengthOrInvalidFormat',
                raise NegativeResponseException(
                        0x13, 0x27, struct.pack('>BBB', 0x27, level+1, 0x13))
        elif self._sessions:
            # 0x12:'SubFunctionNotSupported',
            raise NegativeResponseException(
                    0x12, 0x27, struct.pack('>BBB', 0x27, level, 0x12))
        else:
            # Using this timeout makes the test appear more realistic, but that 
            # is silly for testing
            #time.sleep(self.timeout)
            return None