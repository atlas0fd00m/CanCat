import struct

# TODO each one has its own timeout length

CCP_CONNECT = 0x01
CCP_GET_CCP_VERSION = 0x1B
CCP_EXCHANGE_ID = 0x17
CCP_GET_SEED = 0x12
CCP_UNLOCK = 0x13
CCP_SET_MTA = 0x02
CCP_DNLOAD = 0x03
CCP_DNLOAD_6 = 0x23
CCP_UPLOAD = 0x04
CCP_SHORT_UP = 0x0F
CCP_SELECT_CAL_PAGE = 0x11
CCP_GET_DAQ_SIZE = 0x14
CCP_SET_DAQ_PTR = 0x15
CCP_WRITE_DAQ = 0x16
CCP_START_STOP = 0x06
CCP_DISCONNECT = 0x07
CCP_SET_S_STATUS = 0x0C
CCP_GET_S_STATUS = 0x0D
CCP_BUILD_CHKSUM = 0x0E
CCP_CLEAR_MEMORY = 0x10
CCP_PROGRAM = 0x18
CCP_PROGRAM_6 = 0x22
CCP_MOVE = 0x19
CCP_TEST = 0x05
CCP_GET_ACTIVE_CAL_PAGE = 0x09
CCP_START_STOP_ALL = 0x08
CCP_CCP_DIAG_SERVICE = 0x20
CCP_ACTION_SERVICE = 0x21

DONT_CARE_VAL = 0x90

TEMPORARY_DISCONNECT = 0x00
END_OF_SESSION_DISCONNECT = 0x01

COMMAND_CODES = {
    0x01: 'CONNECT',
    0x1B: 'GET_CCP_VERSION',
    0x17: 'EXCHANGE_ID',
    0x12: 'GET_SEED', # optional
    0x13: 'UNLOCK', # optional
    0x02: 'SET_MTA',
    0x03: 'DNLOAD',
    0x23: 'DNLOAD_6', # optional
    0x04: 'UPLOAD',
    0x0F: 'SHORT_UP', # optional
    0x11: 'SELECT_CAL_PAGE', # optional
    0x14: 'GET_DAQ_SIZE',
    0x15: 'SET_DAQ_PTR',
    0x16: 'WRITE_DAQ',
    0x06: 'START_STOP',
    0x07: 'DISCONNECT',
    0x0C: 'SET_S_STATUS', # optional
    0x0D: 'GET_S_STATUS', # optional
    0x0E: 'BUILD_CHKSUM', # optional
    0x10: 'CLEAR_MEMORY', # optional
    0x18: 'PROGRAM', # optional
    0x22: 'PROGRAM_6', # optional
    0x19: 'MOVE', # optional
    0x05: 'TEST', # optional
    0x09: 'GET_ACTIVE_CAL_PAGE', # optional
    0x08: 'START_STOP_ALL', # optional
    0x20: 'DIAG_SERVICE', # optional
    0x21: 'ACTION_SERVICE' # optional
}

# TODO some commands are optional if the ECU doesn't support DAQ:
# GET_DAQ_SIZE, SET_DAQ_PTR, WRITE_DAQ , START_STOP

# TODO If SELECT_CAL_PAGE is implemented, GET_ACTIVE_CAL_PAGE is required.

# COMMAND RETURN CODES
# Code / Description / Error category / State transition to
COMMAND_RET_CODES = {
    0x00: ('acknowledge / no error', '', ''),
    0x01: ('DAQ processor overload', 'C0', ''),
    0x10: ('command processor busy', 'C1', 'NONE (wait until ACK or timeout)'),
    0x11: ('DAQ processor busy', 'C1', 'NONE (wait until ACK or timeout)'),
    0x12: ('internal timeout', 'C1', 'NONE (wait until ACK or timeout)'),
    0x18: ('key request', 'C1', 'NONE (embedded seed&key)'),
    0x19: ('session status request', 'C1', 'NONE (embedded SET_S_STATUS)'),
    0x20: ('cold start request', 'C2', 'COLD START'),
    0x21: ('cal. data init. request', 'C2', 'cal. data initialization'),
    0x22: ('DAQ list init. request', 'C2', 'DAQ list initialization'),
    0x23: ('code update request', 'C2', '(COLD START)'),
    0x30: ('unknown command', 'C3', '(FAULT)'),
    0x31: ('command syntax', 'C3', 'FAULT'),
    0x32: ('parameter(s) out of range', 'C3', 'FAULT'),
    0x33: ('access denied', 'C3', 'FAULT'),
    0x34: ('overload', 'C3', 'FAULT'),
    0x35: ('access locked', 'C3', 'FAULT'),
    0x36: ('resource/function not available', 'C3', 'FAULT')
}


'''
These pack and unpack helpers are all in one place, as the specification hints that
the endianness shown in examples is implementaiton specific and not necessarily
internally consistent across command types.
'''

def _gen_byte(value):
    return struct.pack('B', value)

def _gen_2_byte_val(value):
    # As noted elsewhere, CCP spec examples are not consistent between
    # little endian and big endian
    return struct.pack('<H', value)

def _gen_4_byte_val(value):
    return struct.pack('>I', value)

def _parse_byte(value):
    return struct.unpack('B', value)[0]

def _parse_4_byte_value(value):
    return hex(struct.unpack('>I', value)[0])

def _parse_2_byte_value(value):
    # All the CCP examples show 2 byte values -> little endian,
    # and 4 byte values (addresses, etc) as being big endian.
    # Of course this is all implementation specific.
    return hex(struct.unpack('<H', value)[0])
