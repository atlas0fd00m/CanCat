#!/usr/bin/env python
import sys
import time
import cancat
import struct
import threading

import cancat.iso_tp as cisotp

NEG_RESP_CODES = {
        0x10:'GeneralReject',
        0x11:'ServiceNotSupported',
        0x12:'SubFunctionNotSupported',
        0x13:'IncorrectMesageLengthOrInvalidFormat',
        0x14:'ResponseTooLong',
        0x21:'BusyRepeatRequest',
        0x22:'ConditionsNotCorrect',
        0x24:'RequestSequenceError',
        0x25:'NoResponseFromSubnetComponent',
        0x26:'FailurePreventsExecutionOfRequestedAction',
        0x31:'RequestOutOfRange',
        0x33:'SecurityAccessDenied',
        0x35:'InvalidKey',
        0x36:'ExceedNumberOfAttempts',
        0x37:'RequiredTimeDelayNotExpired',
        0x70:'UploadDownloadNotAccepted',
        0x71:'TransferDataSuspended',
        0x72:'GeneralProgrammingFailure',
        0x73:'WrongBlockSequenceCounter',
        0x78:'RequestCorrectlyReceived-ResponsePending',
        0x7e:'SubFunctionNotSupportedInActiveSession',
        0x7f:'ServiceNotSupportedInActiveSession',
        0x81:'RpmTooHigh',
        0x82:'RpmTooLow',
        0x83:'EngineIsRunning',
        0x84:'EngineIsNotRunning',
        0x85:'EngineRunTimeTooLow',
        0x86:'TemperatureTooHigh',
        0x87:'TemperatureTooLow',
        0x88:'VehicleSpeedTooHigh',
        0x89:'VehicleSpeedTooLow',
        0x8a:'ThrottlePedalTooHigh',
        0x8b:'ThrottlePedalTooLow',
        0x8c:'TransmissionRangeNotInNeutral',
        0x8d:'TransmissionRangeNotInGear',
        0x8f:'BrakeSwitchsNotClosed',
        0x90:'ShifterLeverNotInPark',
        0x91:'TorqueConverterClutchLocked',
        0x92:'VoltageTooHigh',
        0x93:'VoltageTooLow',
        }

SVC_DIAGNOSTICS_SESSION_CONTROL =           0x10
SVC_ECU_RESET =                             0x11
SVC_CLEAR_DIAGNOSTICS_INFORMATION =         0x14
SVC_READ_DTC_INFORMATION =                  0x19
SVC_READ_DATA_BY_IDENTIFIER =               0x22
SVC_READ_MEMORY_BY_ADDRESS =                0x23
SVC_SECURITY_ACCESS =                       0x27
SVC_READ_DATA_BY_PERIODIC_IDENTIFIER =      0x2a
SVC_DYNAMICALLY_DEFINE_DATA_IDENTIFIER =    0x2c
SVC_WRITE_DATA_BY_IDENTIFIER =              0x2e
SVC_INPUT_OUTPUT_CONTROL_BY_IDENTIFIER =    0x2f
SVC_ROUTINE_CONTROL =                       0x31
SVC_REQUEST_DOWNLOAD =                      0x34
SVC_REQUEST_UPLOAD =                        0x35
SVC_TRANSFER_DATA =                         0x36
SVC_REQUEST_TRANSFER_EXIT =                 0x37
SVC_WRITE_MEMORY_BY_ADDRESS =               0x3d
SVC_TESTER_PRESENT =                        0x3e
SVC_CONTROL_DTC_SETTING =                   0x85

UDS_SVCS = { v:k for k,v in globals().items() if k.startswith('SVC_') }

POS_RESP_CODES = { (k|0x40) : "OK_" + v.lower() for k,v in UDS_SVCS.items() }
POS_RESP_CODES[0] = 'Success'

NEG_RESP_REPR = {}
for k,v in NEG_RESP_CODES.items():
    NEG_RESP_REPR[k] = 'ERR_' + v

RESP_CODES = {}
RESP_CODES.update(NEG_RESP_REPR)
RESP_CODES.update(POS_RESP_CODES)


class NegativeResponseException(Exception):
    def __init__(self, neg_code, svc, msg):
        self.neg_code = neg_code
        self.msg = msg
        self.svc = svc

    def __repr__(self):
        negresprepr = NEG_RESP_CODES.get(self.neg_code)
        return "NEGATIVE RESPONSE to 0x%x (%s):   ERROR 0x%x: %s" % \
            (self.svc, UDS_SVCS.get(self.svc), self.neg_code, negresprepr, self.msg.encode('hex'))

    def __str__(self):
        negresprepr = NEG_RESP_CODES.get(self.neg_code)
        return "NEGATIVE RESPONSE to 0x%x (%s):   ERROR 0x%x: %s   \tmsg: %s" % \
            (self.svc, UDS_SVCS.get(self.svc), self.neg_code, negresprepr, self.msg.encode('hex'))


class UDS:
    def __init__(self, c, tx_arbid, rx_arbid=None, verbose=True, extflag=0):
        self.c = c
        self.verbose = verbose
        self.extflag = extflag

        if rx_arbid == None:
            rx_arbid = tx_arbid + 8 # by UDS spec

        self.tx_arbid = tx_arbid
        self.rx_arbid = rx_arbid

    def xmit_recv(self, data, extflag=0, timeout=3, count=1, service=None):
        msg = self.c.ISOTPxmit_recv(self.tx_arbid, self.rx_arbid, data, extflag, timeout, count, service)

        # check if the response is something we know about and can help out
        if msg != None and len(msg):
            svc = ord(data[0])
            svc_resp = ord(msg[0])
            errcode = 0
            if len(msg) >= 3:
                errcode = ord(msg[2])

            if svc_resp == svc + 0x40:
                if self.verbose: 
                    print "Positive Response!"

            negresprepr = NEG_RESP_CODES.get(errcode)
            if negresprepr != None and svc_resp != svc + 0x40:
                if self.verbose > 1: 
                    print negresprepr + "\n"
                # TODO: Implement getting final message if ResponseCorrectlyReceivedResponsePending is received
                if errcode != 0x78: # Don't throw an exception for ResponseCorrectlyReceivedResponsePending
                    raise NegativeResponseException(errcode, svc, msg)


        return msg

       
    def _do_Function(self, func, data=None, subfunc=None, service=None):

        omsg = chr(func)
        if subfunc != None:
            omsg += chr(subfunc)

        if data != None:
            omsg += data

        msg = self.xmit_recv(omsg, extflag=self.extflag, service=service)
        return msg

    def SendTesterPresent(self):
        while self.TesterPresent is True:
            if self.TesterPresentRequestsResponse:
                self.c.CANxmit(self.tx_arbid, "023E000000000000".decode('hex'))
            else:
                self.c.CANxmit(self.tx_arbid, "023E800000000000".decode('hex'))
            time.sleep(2.0)

    def StartTesterPresent(self, request_response=True):
        self.TesterPresent = True
        self.TesterPresentRequestsResponse=request_response
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
        return self._do_Function(SVC_DIAGNOSTICS_SESSION_CONTROL, chr(session), service=0x50)

    def ReadMemoryByAddress(self, address, size):
        currIdx = self.c.getCanMsgCount()
        return self._do_Function(SVC_READ_MEMORY_BY_ADDRESS, subfunc=0x24, data=struct.pack(">IH", address, size), service = 0x63)
        #return self.xmit_recv("\x23\x24" + struct.pack(">I", address) + struct.pack(">H", size), service = 0x63)
        
    def ReadDID(self, did):
        '''
        Read the Data Identifier specified from the ECU.

        Returns: The response ISO-TP message as a string
        '''
        msg = self._do_Function(SVC_READ_DATA_BY_IDENTIFIER, struct.pack('>H', did), service=0x62)
        #msg = self.xmit_recv("22".decode('hex') + struct.pack('>H', did), service=0x62)
        return msg

    def WriteDID(self, did, data):
        '''
        Write the Data Identifier specified from the ECU.

        Returns: The response ISO-TP message as a string
        '''
        msg = self._do_Function(SVC_WRITE_DATA_BY_IDENTIFIER,struct.pack('>H', did), service=0x62)
        #msg = self.xmit_recv("22".decode('hex') + struct.pack('>H', did), service=0x62)
        return msg

    def RequestDownload(self, addr, data, data_format = 0x00, addr_format = 0x44):
        '''
        Assumes correct Diagnostics Session and SecurityAccess
        '''
        # Figure out the right address and data length formats
        pack_fmt_str = ">BB"
        try:
            pack_fmt_str += {1:"B", 2:"H", 4:"I"}.get(addr_format >> 4) + {1:"B", 2:"H", 4:"I"}.get(addr_format & 0xf)
        except TypeError:
            print "Cannot parse addressAndLengthFormatIdentifier", hex(addr_format)
            return None
        msg = self.xmit_recv("\x34" + struct.pack(pack_fmt_str, data_format, addr_format, addr, len(data)), extflag=self.extflag, service = 0x74)

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
            msg = self.xmit_recv("\x36" + chr(block_idx) + data[data_idx:data_idx+max_txfr_len-2], extflag=self.extflag, service = 0x76)
            data_idx += max_txfr_len - 2
            block_idx += 1
            if block_idx > 0xff:
                block_idx = 0

            # error checking
            if msg is not None and ord(msg[0]) == 0x7f and ord(msg[2]) != 0x78:
                print "Error sending data: {}".format(msg.encode('hex'))
                return None
            if msg is None:
                print "Didn't get a response?"
                data_idx -= max_txfr_len - 2
                block_idx -= 1
                if block_idx == 0:
                    block_idx = 0xff

            # TODO: need to figure out how to get 2nd isotp message to verify that this worked

        # Send RequestTransferExit
        self._do_Function(SVC_REQUEST_TRANSFER_EXIT, service = 0x77)

    def readMemoryByAddress(self, address, length, lenlen=1, addrlen=4):
        '''
        Work in progress!
        '''
        if lenlen == 1:
            lfmt = "B"
        else:
            lfmt = "H"

        lenlenbyte = (lenlen << 4) | addrlen

        msg = self._do_Function(SVC_READ_MEMORY_BY_ADDRESS, data=struct.pack('<BI' + lfmt, lenlenbyte, address, length), service=0x63)
        
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

        data = struct.pack('<BI' + lfmt, lenlenbyte, address, length)
        #data = "3d".decode('hex') + struct.pack('<BI' + lfmt, lenlenbyte, address, length)

        msg = self._do_Function(SVC_WRITE_MEMORY_BY_ADDRESS, data=data, service=0x63)
        #msg = self.xmit_recv(data, service=0x63)
        
        return msg


    def RequestUpload(self, addr, length, data_format = 0x00, addr_format = 0x44):
        '''
        Work in progress!
        '''
        msg = self._do_Function(SVC_REQUEST_UPLOAD, subfunc=data_format, data = chr(addr_format) + struct.pack('>I', addr)[1:] +  struct.pack('>I', length)[1:]) 

        sid, lfmtid, maxnumblocks = struct.unpack('>BBH', msg[:4])

        output = []
        for loop in maxnumblocks:
            msg = self._do_Function(SVC_TRANSFER_DATA, subfunc=loop)
            output.append(msg)

            if len(msg) and msg[0] != '\x76':
                print "FAILURE TO DOWNLOAD ALL.  Returning what we have so far (including error message)"
                return output

        msg = self._do_Function(SVC_REQUEST_TRANSFER_EXIT)
        if len(msg) and msg[0] != '\x77':
            print "FAILURE TO EXIT CLEANLY.  Returning what we received."

        return output

    def EcuReset(self, rst_type=0x1):
        return self._do_Function(SVC_ECU_RESET, subfunc=rst_type)

    def ClearDiagnosticInformation(self):
        pass
    def ReadDTCInfomation(self):
        pass
    def ReadDataByPeriodicIdentifier(self, pdid):
        pass
    def DynamicallyDefineDataIdentifier(self):
        pass
    def InputOutputControlByIdentifier(self, iodid):
        pass
    def RoutineControl(self, rid):
        pass
    def TransferData(self, did):
        pass
    def RequestTransferExit(self):
        pass
    def ControlDTCSetting(self):
        pass



    def ScanDIDs(self, start=0, end=0x10000, delay=0):
        success = []
        try:
            for x in range(start, end):
                try:
                    if self.verbose: 
                        sys.stderr.write(' %x ' % x)

                    val = self.ReadDID(x)
                    success.append((x, val))

                except KeyboardInterrupt:
                    raise

                except Exception, e:
                    if self.verbose > 1:
                        print e

                time.sleep(delay)

        except KeyboardInterrupt:
            print "Stopping Scan during DID 0x%x " % x
            return success

        return success


    def SecurityAccess(self, level, key):
        msg = self._do_Function(SVC_SECURITY_ACCESS, subfunc=level, service = 0x67)
        if msg is None:
            return msg
        if(ord(msg[0]) == 0x7f):
            print "Error getting seed:", msg.encode('hex')

        else:
            seed = msg[2:5]
            hexified_seed = " ".join(x.encode('hex') for x in seed)
            key = str(bytearray(self._key_from_seed(hexified_seed, key)))

            msg = self._do_Function(SVC_SECURITY_ACCESS, subfunc=level+1, data=key, service = 0x67)
            return msg


    def _key_from_seed(self, seed, secret):
        print "Not implemented in this class"
        return 0


def printUDSSession(c, tx_arbid, rx_arbid=None, paginate=45):
    if rx_arbid == None:
        rx_arbid = tx_arbid + 8 # by UDS spec

    msgs = [msg for msg in c.genCanMsgs(arbids=[tx_arbid, rx_arbid])]

    msgs_idx = 0
    
    linect = 1
    while msgs_idx < len(msgs):
        arbid, isotpmsg, count = cisotp.msg_decode(msgs, msgs_idx)
        #print "Message: (%s:%s) \t %s" % (count, msgs_idx, isotpmsg.encode('hex'))
        svc = ord(isotpmsg[0])
        mtype = (RESP_CODES, UDS_SVCS)[arbid==tx_arbid].get(svc, '')

        print "Message: (%s:%s) \t %-30s %s" % (count, msgs_idx, isotpmsg.encode('hex'), mtype)
        msgs_idx += count

        if paginate:
            if (linect % paginate)==0:
                raw_input("%x)  PRESS ENTER" % linect)

        linect += 1
        

