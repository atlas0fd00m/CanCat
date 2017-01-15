#!/usr/bin/env python
import time
import cancat
import struct
import threading

class UDS:
    def __init__(self, c, tx_arbid, rx_arbid):
        self.c = c
        self.tx_arbid = tx_arbid
        self.rx_arbid = rx_arbid

    def ReassembleIsoTP(self, start_index = 0, service = None):
        msg_found = False
        while msg_found is False:
            for idx, ts, arbid, msg in self.c.genCanMsgs(start=start_index, arbids=[self.rx_arbid]):
                # Check that the message is for the expected service, if specified
                if service is not None:
                    # Check if this is the right service, or there was an error
                    if ord(msg[1]) == service or ord(msg[1]) == 0x7f:
                        msg_found = True
                        return arbid, msg
                else:
                    msg_found = True
                    return arbid, msg
            time.sleep(0.1)

    def SendTesterPresent(self):
        while self.TesterPresent is True:
            self.c.CANxmit(self.tx_arbid, "023E000000000000".decode('hex'))
            time.sleep(2.0)

    def StartTesterPresent(self):
        self.TesterPresent = True
        self.t = threading.Thread(target = self.SendTesterPresent)
        self.t.setDaemon(True)
        self.t.start()

    def StopTesterPresent(self):
        self.TesterPresent = False
        self.t.join(5.0)
        if self.t.isAlive():
            print "Error killing Tester Present thread"
        else:
            del self.t

    def DiagnosticSessionControl(self, session):
        currIdx = self.c.getCanMsgCount()
        self.c.ISOTPxmit_recv(self.tx_arbid, self.rx_arbid, "\x10" + chr(session))
        arbid, msg = self.ReassembleIsoTP(start_index = currIdx, service = 0x50)
        print arbid, msg.encode('hex')
        
    def SecurityService(self, level):
        currIdx = self.c.getCanMsgCount()
        self.c.ISOTPxmit_recv(self.tx_arbid, self.rx_arbid, "\x27" + chr(level))
        arbid, msg = self.ReassembleIsoTP(start_index = currIdx, service = 0x67)
        print arbid, msg.encode('hex')
        if(msg[1] == 0x7f):
            print "Error getting seed:", msg
        else:
            seed = msg[3:6]

            key = seed # Replace this with a call to the actual response computation function
            currIdx = self.c.getCanMsgCount()
            self.c.ISOTPxmit_recv(self.tx_arbid, self.rx_arbid, "\x27" + chr(level+1) + key)
            arbid, msg = self.ReassembleIsoTP(start_index = currIdx, service = 0x67)
            print arbid, msg.encode('hex')

    def readDID(self, ecuarbid, did, resparbid=None):
        if resparbid == None:
            resparbid = ecuarbid + 8 # by ISO-TP Spec

        currIdx = self.c.getCanMsgCount()
        self.c.ISOTPxmit_recv(ecuarbid, resparbid, "22".decode('hex') + struct.pack('>H', did))
        
        return self.ReassembleIsoTP(start_index = currIdx)

