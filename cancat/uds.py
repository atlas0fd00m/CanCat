#!/usr/bin/env python
import time
import cancat
import struct
import threading

class UDS:
    def __init__(self, c, tx_arbid, rx_arbid=None):
        self.c = c

        if rx_arbid == None:
            rx_arbid = tx_arbid + 8 # by UDS spec

        self.tx_arbid = tx_arbid
        self.rx_arbid = rx_arbid

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
        msg = self.c.ISOTPxmit_recv(self.tx_arbid, self.rx_arbid, "\x10" + chr(session), service=0x50)
        print msg.encode('hex')
        
    def SecurityService(self, level):
        txmsg = "\x27" + chr(level)
        print "sending", self.tx_arbid, txmsg.encode('hex')
        msg = self.c.ISOTPxmit_recv(self.tx_arbid, self.rx_arbid, txmsg, service=0x67)
        #arbid, msg = self.ReassembleIsoTP(start_index = currIdx, service = 0x67)
        print "got", msg.encode('hex')
        print "msg[0]:", msg[0].encode('hex')

        if(msg[0].encode('hex') == '7f'):
            print "Error getting seed:", msg.encode('hex')

        else:
            seed = msg[2:5]
            hexified_seed = " ".join(x.encode('hex') for x in seed)
            key = seed # Replace this with a call to the actual response computation function
            currIdx = self.c.getCanMsgCount()
            msg = self.c.ISOTPxmit_recv(self.tx_arbid, self.rx_arbid, txmsg, service=0x67)
            #arbid, msg = self.ReassembleIsoTP(start_index = currIdx, service = 0x67)
            print "got", msg.encode('hex')
            return msg

    def readDID(self, did, ecuarbid=None, resparbid=None):
        '''
        Read the Data Identifier specified from the ECU.  i
        For hackery purposes, the xmit and recv ARBIDs can be specified.

        Returns: The response ISO-TP message as a string
        '''
        if ecuarbid == None:
            ecuarbid = self.tx_arbid

        if resparbid == None:
            resparbid = self.rx_arbid

        msg = self.c.ISOTPxmit_recv(ecuarbid, resparbid, "22".decode('hex') + struct.pack('>H', did), service=0x62)
        
        return msg

    def writeDID(self, did, data, ecuarbid=None, resparbid=None):
        '''
        Write the Data Identifier specified from the ECU.  i
        For hackery purposes, the xmit and recv ARBIDs can be specified.

        Returns: The response ISO-TP message as a string
        '''
        if ecuarbid == None:
            ecuarbid = self.tx_arbid

        if resparbid == None:
            resparbid = self.rx_arbid

        msg = self.c.ISOTPxmit_recv(ecuarbid, resparbid, "22".decode('hex') + struct.pack('>H', did), service=0x62)
        
        return msg

    def readMemoryByAddress(self, address, length, lenlen=1, addrlen=4):
        '''
        Work in progress!
        '''
        if lenlen == 1:
            lfmt = "B"
        else:
            lfmt = "H"

        lenlenbyte = (lenlen << 4) | addrlen

        data = "23".decode('hex') + struct.pack('<BI' + lfmt, lenlenbyte, address, length)

        msg = self.c.ISOTPxmit_recv(self.tx_arbid, self.rx_arbid, data, service=0x63)
        
        return msg

    def writeMemoryByAddress(self, address, data, lenlen=1, addrlen=4):
        '''
        Work in progress!
        '''
        if lenlen == 1:
            lfmt = "B"
        else:
            lfmt = "H"

        lenlenbyte = (lenlen << 4) | addrlen

        data = "3d".decode('hex') + struct.pack('<BI' + lfmt, lenlenbyte, address, length)

        msg = self.c.ISOTPxmit_recv(self.tx_arbid, self.rx_arbid, data, service=0x63)
        
        return msg
