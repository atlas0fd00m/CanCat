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

    def ReadMemoryByAddress(self, address, size):
        msg = self.c.ISOTPxmit_recv(self.tx_arbid, self.rx_arbid, "\x23\x24" + struct.pack(">I", address) + struct.pack(">H", size))
        return msg
        
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
        msg = self.c.ISOTPxmit_recv(self.tx_arbid, self.rx_arbid, "22".decode('hex') + struct.pack('>H', did), service=0x62)
        return msg

    def RequestDownload(self, addr, data, data_format = 0x00, addr_format = 0x44):
        # Figure out the right address and data length formats
        pack_fmt_str = ">BB"
        try:
            pack_fmt_str += {1:"B", 2:"H", 4:"I"}.get(addr_format >> 4) + {1:"B", 2:"H", 4:"I"}.get(addr_format & 0xf)
        except TypeError:
            print "Cannot parse addressAndLengthFormatIdentifier", hex(addr_format)
            return None
        msg = self.c.ISOTPxmit_recv(self.tx_arbid, self.rx_arbid, 
                                  "\x34" + struct.pack(pack_fmt_str, data_format, addr_format, addr, len(data)))

        # Parse the response
        if ord(msg[0]) != 0x74:
            print "Error received: {}".format(msg.encode('hex'))
            return msg
        max_txfr_num_bytes = ord(msg[1]) >> 4 # number of bytes in the max tranfer length parameter
        max_txfr_len = 0 
        for i in range(2,2+max_txfr_num_bytes):
            max_txfr_len <<= 8
            max_txfr_len += ord(msg[i])

        # Transfer data
        data_idx = 0
        block_idx = 1
        while data_idx < len(data):
            msg = self.c.ISOTPxmit_recv(self.tx_arbid, self.rx_arbid, 
                                      "\x36" + chr(block_idx) + data[data_idx:data_idx+max_txfr_len-2])
            data_idx += max_txfr_len - 2
            block_idx += 1
            if block_idx > 0xff:
                block_idx = 0
>>>>>>> 6e33fb9... Finished getting RequestUpload working. Updated firmware to be more robust to sending large numbers of messages. Implemented ISOTP flow control

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
