import cancat.uds

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


class TestUDS(cancat.uds.UDS):
    DIDs = {
        0x711: {
            0x0042: '\x62\x00\x42ANSWER',
        },
        0x7E0: {
            0xF190: '\x62\xF1\x901AB123CD1EF123456',
            0xE010: '\x62\xE0\x10VERSION 1.2.3',
        },
    }

    def __init__(self, c, tx_arbid, rx_arbid=None, verbose=True, extflag=0):
        super(TestUDS, self).__init__(c, tx_arbid, rx_arbid, verbose=verbose, extflag=extflag)
        if self.tx_arbid in TestUDS.DIDs:
            self.dids = TestUDS.DIDs[self.tx_arbid]
        else:
            self.dids = {}

    def ReadDID(self, did):
        if did in self.dids and self.extflag == False:
            return self.dids[did]
        elif self.dids:
            raise cancat.uds.NegativeResponseException(0x31, 0x22, '\x22\x00\x00\x31')
        else:
            return None
