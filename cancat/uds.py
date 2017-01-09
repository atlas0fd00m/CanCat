#!/usr/bin/env python
import cancat
import threading
import time

class UDS:
    def __init__(self, c, tx_arbid, rx_arbid):
        self.c = c
        self.tx_arbid = tx_arbid
        self.rx_arbid = rx_arbid
        self.t = threading.Thread(target = self.SendTesterPresent)
        self.TesterPresent = False
        self.t.setDaemon(True)
        self.t.start()

    def ReassembleIsoTP(self, start_index = 0):
        msg_found = False
        while msg_found is False:
            for idx, ts, arbid, msg in self.c.genCanMsgs(start=start_index, arbids=[self.rx_arbid]):
                msg_found = True
                return hex(arbid), msg.encode('hex')
            time.sleep(0.1)

    def SendTesterPresent(self):
        while True:
            if self.TesterPresent:
                self.c.CANxmit(self.tx_arbid, "023E000000000000".decode('hex'))
            time.sleep(2.0)

    def StartTesterPresent(self):
        self.TesterPresent = True

    def StopTesterPresent(self):
        self.TesterPresent = False

    def DiagnosticSessionControl(self, session):
        currIdx = self.c.getCanMsgCount()
        self.c.ISOTPxmit_recv(self.tx_arbid, self.rx_arbid, "10".decode('hex') + chr(session))
        print self.ReassembleIsoTP(start_index = currIdx)
        
    def SecurityService(self, level):
        currIdx = self.c.getCanMsgCount()
        self.c.ISOTPxmit_recv(self.tx_arbid, self.rx_arbid, "27".decode('hex') + chr(level))
        print self.ReassembleIsoTP(start_index = currIdx)


