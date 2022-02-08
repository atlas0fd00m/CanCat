#!/usr/bin/env python
import sys
import time
import cancat
import struct
import threading
from utils import *
import utils

CRM_START_VAL = 0xff

'''
    MESSAGE TYPES:

    CRO (Command Receive Object): message sent from the leader device to the
        follower device(s).
    DTO (Data Transmission Object): message sent from the follower device to the
        leader device (Command Return Message or Event Message or Data Acquisition Message).
    CRM (Command Return Message): one type of message sent from the follower device
        to the leader device containing command / error code and command counter.

    FYI:
        For all data transfered by the CCP, no byte order for the protocol itself
        is defined. Because the data organization depends on the ECU's CPU,
        the byte ordering is defined in the follower device description file.
        The only exceptions are the station addresses in the TEST, CONNECT
        and DISCONNECT commands.

    Spec: https://automotivetechis.files.wordpress.com/2012/06/ccp211.pdf
'''

class CCPFollower(object):
    def __init__(self, c, tx_arbid=None, rx_arbid=None, verbose=True, extflag=0):
        self.c = c
        self.verbose = verbose
        self.extflag = extflag

        self.tx_arbid = tx_arbid
        self.rx_arbid = rx_arbid

    def _do_Function(self, msg, command_type, currIdx, timeout=1):
        print("Not Implemented on follower")

    '''
    +---------------------------------------------------------------------+
    |                                                                     |
    |               Command Receive Object helper functions               |
    |                                                                     |
    +---------------------------------------------------------------------+
    |   Use these to parse messages sent from the leader to a follower    |
    +---------------------------------------------------------------------+
    '''

    def _parse_CRO(self, msg):
        CCP_CRO_Type = msg[0];

        if CCP_CRO_Type == CCP_CONNECT:
            parsed_msg = self._parse_connect_CRO(msg)
        elif CCP_CRO_Type == CCP_DISCONNECT:
            parsed_msg = self._parse_disconnect_CRO(msg)
        elif CCP_CRO_Type == CCP_SET_MTA:
            parsed_msg = self._parse_setMTA_CRO(msg)
        elif CCP_CRO_Type == CCP_DNLOAD:
            parsed_msg = self._parse_dnload_CRO(msg)
        elif CCP_CRO_Type == CCP_UPLOAD:
            parsed_msg = self._parse_upload_CRO(msg)
        elif CCP_CRO_Type == CCP_SHORT_UP:
            parsed_msg = self._parse_short_upload_CRO(msg)
        elif CCP_CRO_Type == CCP_CLEAR_MEMORY:
            parsed_msg = self._parse_clear_memory_CRO(msg)
        elif CCP_CRO_Type == CCP_MOVE:
            parsed_msg = self._parse_move_CRO(msg)
        elif CCP_CRO_Type == CCP_TEST:
            parsed_msg = self._parse_test_CRO(msg)
        elif CCP_CRO_Type == CCP_PROGRAM:
            parsed_msg = self._parse_program_CRO(msg)
        elif CCP_CRO_Type == CCP_EXCHANGE_ID:
            parsed_msg = self._parse_exchangeID_CRO(msg)
        elif CCP_CRO_Type == CCP_GET_CCP_VERSION:
            parsed_msg = self._parse_ccp_version_CRO(msg)
        elif CCP_CRO_Type == CCP_GET_SEED:
            parsed_msg = self._parse_get_seed_CRO(msg)
        elif CCP_CRO_Type == CCP_BUILD_CHKSUM:
            parsed_msg = self._parse_build_chksum_CRO(msg)
        elif CCP_CRO_Type == CCP_UNLOCK:
            parsed_msg = self._parse_unlock_CRO(msg)
        elif CCP_CRO_Type == CCP_SET_S_STATUS:
            parsed_msg = self._parse_set_s_status_CRO(msg)
        elif CCP_CRO_Type == CCP_GET_S_STATUS:
            parsed_msg = self._parse_get_s_status_CRO(msg)
        else:
            raise Exception("Cannot parse message type ", CCP_CRO_Type)

        return parsed_msg

    def _parse_connect_CRO(self, msg):
        '''
        CRO

        +-------+--------+-----------------------------------------------+
        |   0   |  byte  |  CRO command type                             |
        +-------+--------+-----------------------------------------------+
        |   1   |  bytes |  Counter (CTR)                                |
        +-------+--------+-----------------------------------------------+
        |  2..3 |  word  |  station address (Intel format)               |
        +-------+--------+-----------------------------------------------+
        |  4..7 |  bytes |  don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        cmd = utils._parse_byte(msg[0])
        ctr = utils._parse_byte(msg[1])

        stat_addr = utils._parse_2_byte_value(msg[2:4])

        parsed = {'CMD': cmd, 'CTR': ctr, 'stat_addr': stat_addr}

        return parsed

    def _parse_exchangeID_CRO(self, msg):
        '''
        EXCHANGE_ID CRO

        The CCP leader and follower stations exchange IDs for automatic session
        configuration. This might include automatic assignment of a data
        acquisition setup file depending on the follower's returned ID (Plug-n-Play).

        +-------+--------+-----------------------------------------------+
        |   0   |  byte  |  CRO command type                             |
        +-------+--------+-----------------------------------------------+
        |   1   |  bytes |  Counter (CTR)                                |
        +-------+--------+-----------------------------------------------+
        | 2..7  |  bytes |  CCP leader device ID information             |
        |       |        |  (optional and implementation specific)       |
        +-------+--------+-----------------------------------------------+
        '''

        cmd = utils._parse_byte(msg[0])
        ctr = utils._parse_byte(msg[1])

        # Device ID is implementation specific and optional, just return back value for now
        id = utils._parse_6_byte_value(msg[2:])

        parsed = {'CMD': cmd, 'CTR': ctr, 'DEVICE_ID': id}

        return parsed

    def _parse_set_MTA_CRO(self, msg):
        '''
        SET_MTA CRO

        This CRO sets the memory address to later read to or write from.

        This CRO sets MTA0 or MTA1, depending on bit 2.
        - MTA0 is used by the commands DNLOAD, UPLOAD, DNLOAD_6,
        SELECT_CAL_PAGE, CLEAR_MEMORY, PROGRAM and PROGRAM_6.
        - MTA1 is used by the MOVE command.

        +-------+--------+-----------------------------------------------+
        |   0   |  byte  |  CRO command type                             |
        +-------+--------+-----------------------------------------------+
        |   1   |  bytes |  Counter (CTR)                                |
        +-------+--------+-----------------------------------------------+
        |   2   |  byte  |  Memory transfer address MTA number (0,1)     |
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  Address extension                            |
        +-------+--------+-----------------------------------------------+
        | 4..7  |  ulong |  Address                                      |
        +-------+--------+-----------------------------------------------+
        '''

        cmd = utils._parse_byte(msg[0])
        ctr = utils._parse_byte(msg[1])

        mta_number = utils._parse_byte(msg[2])

        address_extension = utils._parse_byte(msg[3])

        address = utils._parse_4_byte_value(msg[4:])

        parsed = {'CMD': cmd, 'CTR': ctr, 'mta_number': mta_number, \
                  'address_extension': address_extension, 'address': address}

        return parsed

    def _parse_download_CRO(self, msg):
        '''
        CRO

        Will download value to the follower device at address of MTA0.

        ***************************************************************************
        ** You must set MTA0 with the SET_MTA command before using this function **
        ***************************************************************************

        +-------+--------+-----------------------------------------------+
        |   0   |  byte  |  CRO command type                             |
        +-------+--------+-----------------------------------------------+
        |   1   |  bytes |  Counter (CTR)                                |
        +-------+--------+-----------------------------------------------+
        |   2   |  byte  |  size of data block to follow in bytes        |
        +-------+--------+-----------------------------------------------+
        | 3..7  |  bytes |  data to be transferred (up to 5 bytes)       |
        +-------+--------+-----------------------------------------------+
        '''

        cmd = utils._parse_byte(msg[0])
        ctr = utils._parse_byte(msg[1])

        data_block_size = utils._parse_byte(msg[2])
        data = utils._parse_4_byte_value(msg[3:7])

        parsed = {'CMD': cmd, 'CTR': ctr, 'data_block_size': data_block_size, 'data': data}

        return parsed

    def _parse_upload_CRO(self, msg):
        '''
        CRO

        ***************************************************************************
        ** You must set MTA0 with the SET_MTA command before using this function **
        ***************************************************************************

        A data block of the specified length (size), starting at current MTA0,
        will be copied into the corresponding DTO data field.

        The MTA0 pointer will be post-incremented by the value of 'size'.

        +-------+--------+-----------------------------------------------+
        |   0   |  byte  |  CRO command type                             |
        +-------+--------+-----------------------------------------------+
        |   1   |  bytes |  Counter (CTR)                                |
        +-------+--------+-----------------------------------------------+
        |   2   |  byte  |  Size of data block to be uploaded in bytes   |
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        cmd = utils._parse_byte(msg[0])
        ctr = utils._parse_byte(msg[1])

        data_block_size = utils._parse_byte(msg[2])

        parsed = {'CMD': cmd, 'CTR': ctr, 'data_block_size': data_block_size}

        return parsed

    def _parse_disconnect_CRO(self, msg):
        '''
        CRO

        Data to be parsed after CMD and CTR values:
        +-------+--------+-----------------------------------------------+
        |   2   |  byte  |  0x00 temporary, 0x01 end of session          |
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  don't care                                   |
        +-------+--------+-----------------------------------------------+
        |  4,5  |  word  |  Station address (Intel format)               |
        +-------+--------+-----------------------------------------------+
        |  6..7 |  bytes |  don't care                                   |
        +-------+--------+-----------------------------------------------+

        Disconnect Types:
        - TEMPORARY_DISCONNECT = 0x00
        - END_OF_SESSION_DISCONNECT = 0x01
        '''

        cmd = utils._parse_byte(msg[0])
        ctr = utils._parse_byte(msg[1])

        stat_addr = utils._parse_2_byte_value(msg[4:6])

        disconnect_type = utils._parse_byte(msg[2])

        parsed = {'CMD': cmd, 'CTR': ctr, 'disconnect_type': disconnect_type, 'stat_addr': stat_addr}

        return parsed

    def _parse_program_CRO(self, msg):
        '''
        PROGRAM CRO

        ***************************************************************************
        ** You must set MTA0 with the SET_MTA command before using this function **
        ***************************************************************************

        Data block will be programmed into non-volatile memory (FLASH, EEPROM),
        starting at current MTA0. The MTA0 pointer will be post-incremented
        by the value of 'size'.

        +-------+--------+-----------------------------------------------+
        |   0   |  byte  |  CRO command type                             |
        +-------+--------+-----------------------------------------------+
        |   1   |  bytes |  Counter (CTR)                                |
        +-------+--------+-----------------------------------------------+
        |   2   |  byte  |  size of data block to follow in bytes        |
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  Data to be programmed (max. 5 bytes)         |
        +-------+--------+-----------------------------------------------+
        '''

        cmd = utils._parse_byte(msg[0])
        ctr = utils._parse_byte(msg[1])

        data_block_size = utils._parse_byte(msg[2])

        data = utils._parse_4_byte_value(msg[3:7])

        parsed = {'CMD': cmd, 'CTR': ctr, 'data_block_size': data_block_size, 'data': data}

        return parsed

    def _parse_move_CRO(self, msg):
        '''
        MOVE CRO

        A data block of the specified length (size) will be copied from the
        address defined by MTA 0 (source pointer) to the address defined by
        MTA 1 (destination pointer).

        +-------+--------+-----------------------------------------------+
        |   0   |  byte  |  CRO command type                             |
        +-------+--------+-----------------------------------------------+
        |   1   |  bytes |  Counter (CTR)                                |
        +-------+--------+-----------------------------------------------+
        |  2..5 |  long  | Size (num of bytes) of data block to be moved |
        +-------+--------+-----------------------------------------------+
        |  6,7  |  bytes | Don't care                                    |
        +-------+--------+-----------------------------------------------+
        '''

        cmd = utils._parse_byte(msg[0])
        ctr = utils._parse_byte(msg[1])

        memory_size = utils._parse_4_byte_value(msg[2:6])

        parsed = {'CMD': cmd, 'CTR': ctr, 'memory_size': memory_size}

        return parsed

    def _parse_clear_memory_CRO(self, msg):
        '''
        CLEAR_MEMORY CRO

        +-------+--------+-----------------------------------------------+
        |   0   |  byte  |  CRO command type                             |
        +-------+--------+-----------------------------------------------+
        |   1   |  bytes |  Counter (CTR)                                |
        +-------+--------+-----------------------------------------------+
        |  2..5 |  long  |  Memory size                                  |
        +-------+--------+-----------------------------------------------+
        |  6,7  |  bytes |  don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        cmd = utils._parse_byte(msg[0])
        ctr = utils._parse_byte(msg[1])

        memory_size = utils._parse_4_byte_value(msg[2:6])

        parsed = {'CMD': cmd, 'CTR': ctr, 'memory_size': memory_size}

        return parsed

    def _parse_test_CRO(self, msg):
        '''
        TEST CRO

        This command is used to test if the slave with the specified station
        address is available for CCP communication. This command does not
        establish a logical connection nor does it trigger any activities in
        the specified follower.

        +-------+--------+-----------------------------------------------+
        |   0   |  byte  |  CRO command type                             |
        +-------+--------+-----------------------------------------------+
        |   1   |  bytes |  Counter (CTR)                                |
        +-------+--------+-----------------------------------------------+
        |  2,3  |  word  |  station address (little-endian)              |
        +-------+--------+-----------------------------------------------+
        | 4..7  |  bytes |  don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        cmd = utils._parse_byte(msg[0])
        ctr = utils._parse_byte(msg[1])

        stat_addr = utils._parse_2_byte_value(msg[2:4])

        parsed = {'CMD': cmd, 'CTR': ctr, 'stat_addr': stat_addr}

        return parsed

    def _parse_get_ccp_version_CRO(self, msg):
        '''
        GET_CCP_VERSION CRO

        This command performs a mutual identification of the protocol version
        used in the leader and in the follower device to agree on a common
        protocol version. This command is expected to be executed prior to
        the EXCHANGE_ID command.

        +-------+--------+-----------------------------------------------+
        |   0   |  byte  |  CRO command type                             |
        +-------+--------+-----------------------------------------------+
        |   1   |  bytes |  Counter (CTR)                                |
        +-------+--------+-----------------------------------------------+
        |   2   |  byte  |  Desired Main Protocol version                |
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  Desired minor vers (release w/i major vers)  |
        +-------+--------+-----------------------------------------------+
        | 4..7  |  bytes |  Don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        cmd = utils._parse_byte(msg[0])
        ctr = utils._parse_byte(msg[1])

        main_protocol = utils._parse_byte(msg[2])
        minor_protocol = utils._parse_byte(msg[3])

        parsed = {'CMD': cmd, 'CTR': ctr, 'main_protocol': main_protocol, 'minor_protocol': minor_protocol}

        return parsed

    def _parse_get_seed_CRO(self, msg):
        '''
        GET_SEED CRO

        Send a GET_SEED CRO for a resource, and then send an UNLOCK CRO.
        If you need multiple resources, then do GET_SEED -> UNLOCK message pairs
        for each resource.

        Resource Mask:
        +-----+-----+-----+-----+-----+-----+-----+-----+
        |  7  |  6  |  5  |  4  |  3  |  2  |  1  |  0  |
        +-----+-----+-----+-----+-----+-----+-----+-----+
        |  X  | PGM |  X  |  X  |  X  |  X  | DAQ | CAL |
        +-----+-----+-----+-----+-----+-----+-----+-----+

        PGM:  Memory Programming
        DAQ:  Data Acquisition
        CAL:  Calibration

        Data to be sent after CMD and CTR values:
        +-------+--------+-----------------------------------------------+
        |   0   |  byte  |  CRO command type                             |
        +-------+--------+-----------------------------------------------+
        |   1   |  bytes |  Counter (CTR)                                |
        +-------+--------+-----------------------------------------------+
        |   2   |  byte  |  Requested follower resource or function **   |
        +-------+--------+-----------------------------------------------+
        | 3..7  |  bytes |  Don't care                                   |
        +-------+--------+-----------------------------------------------+

        ** See "Resource Mask" info above
        '''

        cmd = utils._parse_byte(msg[0])
        ctr = utils._parse_byte(msg[1])

        requested_resource = utils._parse_byte(msg[2])

        parsed = {'CMD': cmd, 'CTR': ctr, 'requested_resource': requested_resource}

        return parsed

    def _parse_unlock_CRO(self, msg):
        '''
        UNLOCK CRO

        +-------+--------+-----------------------------------------------+
        |   0   |  byte  |  CRO command type                             |
        +-------+--------+-----------------------------------------------+
        |   1   |  bytes |  Counter (CTR)                                |
        +-------+--------+-----------------------------------------------+
        |  2..  |  bytes |  Key computed with GET_SEED seed              |
        +-------+--------+-----------------------------------------------+
        '''

        cmd = utils._parse_byte(msg[0])
        ctr = utils._parse_byte(msg[1])

        # Key length is not specified, just return everything
        key = utils._parse_6_byte_value(msg[2:]) #'0x' + msg[2:].hex()

        parsed = {'CMD': cmd, 'CTR': ctr, 'key': key}

        return parsed

    def _parse_build_chksum_CRO(self, msg):
        '''
        BUILD_CHKSUM CRO

        +-------+--------+-----------------------------------------------+
        |   0   |  byte  |  CRO command type                             |
        +-------+--------+-----------------------------------------------+
        |   1   |  bytes |  Counter (CTR)                                |
        +-------+--------+-----------------------------------------------+
        |  2..5 |  ulong |  Block size in bytes                          |
        +-------+--------+-----------------------------------------------+
        |  6,7  |  bytes |  Don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        cmd = utils._parse_byte(msg[0])
        ctr = utils._parse_byte(msg[1])

        memory_size = utils._parse_4_byte_value(msg[2:6])

        parsed = {'CMD': cmd, 'CTR': ctr, 'memory_size': memory_size}

        return parsed

    def _parse_short_upload_CRO(self, msg):
        '''
        BUILD_CHKSUM CRO

        Address endian may be swapped (it's implementation specific)

        +-------+--------+-----------------------------------------------+
        |   0   |  byte  | CRO command type                              |
        +-------+--------+-----------------------------------------------+
        |   1   |  bytes | Counter (CTR)                                 |
        +-------+--------+-----------------------------------------------+
        |   2   |  byte  | Size of data block to be uploaded (1-5 bytes) |
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  | Address extension                             |
        +-------+--------+-----------------------------------------------+
        |  4..7 |  ulong | Address                                       |
        +-------+--------+-----------------------------------------------+
        '''
        cmd = utils._parse_byte(msg[0])
        ctr = utils._parse_byte(msg[1])

        data_block_size = utils._parse_byte(msg[2])
        address_extension = utils._parse_byte(msg[3])

        address = utils._parse_4_byte_value(msg[4:])

        parsed = {'CMD': cmd, 'CTR': ctr, 'data_block_size': data_block_size,
                  'address_extension': address_extension, 'address': address}

        return parsed

    def _parse_get_s_status_CRO(self, msg):
        '''
        GET_S_STATUS CRO

        +-------+--------+-----------------------------------------------+
        |   0   |  byte  |  CRO command type                             |
        +-------+--------+-----------------------------------------------+
        |   1   |  bytes |  Counter (CTR)                                |
        +-------+--------+-----------------------------------------------+
        |  2..7 |  bytes |  don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        cmd = utils._parse_byte(msg[0])
        ctr = utils._parse_byte(msg[1])

        parsed = {'CMD': cmd, 'CTR': ctr}

        return parsed

    def _parse_set_s_status_CRO(self, msg):
        '''
        SET_S_STATUS CRO

        Tells follower what the current status is

        +-------+--------+-----------------------------------------------+
        |   0   |  byte  |  CRO command type                             |
        +-------+--------+-----------------------------------------------+
        |   1   |  bytes |  Counter (CTR)                                |
        +-------+--------+-----------------------------------------------+
        |   2   |  byte  |  Session status bits (see table below)        |
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  don't care                                   |
        +-------+--------+-----------------------------------------------+

        Resource Mask:
        +-----+-----+-----+-----+-----+-----+-----+-----+
        |  7  |  6  |  5  |  4  |  3  |  2  |  1  |  0  |
        +-----+-----+-----+-----+-----+-----+-----+-----+
        | RUN | STR |  X  |  X  |  X  | RES | DAQ | CAL |
        +-----+-----+-----+-----+-----+-----+-----+-----+

        RUN:  Session in progress
        STR (STORE):   Request to save calibration data during shut-down in ECU
        RES (RESUME):  Request to save DAQ setup during shutdown in ECU.
                       ECU automatically restarts DAQ after startup.
        DAQ:  DAQ list(s) initialized
        CAL:  Calibration data initialized
        '''

        cmd = utils._parse_byte(msg[0])
        ctr = utils._parse_byte(msg[1])

        session_status_bits = utils._parse_byte(msg[2])

        parsed = {'CMD': cmd, 'CTR': ctr, 'session_status_bits': session_status_bits}

        return parsed

    def _parse_select_cal_page_CRO(self, msg):
        '''
        SELECT_CAL_PAGE CRO

        Tells follower to take whatever calibration page MTA0 is pointing to,
        and make it the active calibration page.

        +-------+--------+-----------------------------------------------+
        |   0   |  byte  |  CRO command type                             |
        +-------+--------+-----------------------------------------------+
        |   1   |  byte  |  Counter (CTR)                                |
        +-------+--------+-----------------------------------------------+
        |  2..7 |  bytes |  Don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        cmd = utils._parse_byte(msg[0])
        ctr = utils._parse_byte(msg[1])

        parsed = {'CMD': cmd, 'CTR': ctr}

        return parsed

    def _parse_get_active_cal_page_CRO(self, msg):
        '''
        GET_ACTIVE_CAL_PAGE CRO

        Tells follower to return start address of currently active calibration page

        +-------+--------+-----------------------------------------------+
        |   0   |  byte  |  CRO command type                             |
        +-------+--------+-----------------------------------------------+
        |   1   |  byte  |  Counter (CTR)                                |
        +-------+--------+-----------------------------------------------+
        |  2..7 |  bytes |  Don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        cmd = utils._parse_byte(msg[0])
        ctr = utils._parse_byte(msg[1])

        parsed = {'CMD': cmd, 'CTR': ctr}

        return parsed

    def _parse_diag_service_CRO(self, msg):
        '''
        DIAG_SERVICE CRO

        Tells follower to carry out specified diagnostic service, then set Memory
        Transfer Address (MTA0) to location of action service return info.

        +-------+--------+-----------------------------------------------+
        |   0   |  byte  |  CRO command type                             |
        +-------+--------+-----------------------------------------------+
        |   1   |  byte  |  Counter (CTR)                                |
        +-------+--------+-----------------------------------------------+
        |  2,3  |  word  |  Diagnostic service number                    |
        +-------+--------+-----------------------------------------------+
        |  4..7 |  bytes |  Parameters, if applicable                    |
        +-------+--------+-----------------------------------------------+
        '''

        cmd = utils._parse_byte(msg[0])
        ctr = utils._parse_byte(msg[1])

        # spec shows two bytes for number but example only shows one byte
        diag_service_num = utils._parse_2_byte_value(msg[2:4])
        params = utils._parse_4_byte_value(msg[4:])

        parsed = {'CMD': cmd, 'CTR': ctr, 'diag_service_num': diag_service_num, \
                  'params': params}

        return parsed

    def _parse_action_service_CRO(self, msg):
        '''
        ACTION_SERVICE CRO

        Tells follower to carry out specified action service, then set Memory
        Transfer Address (MTA0) to location of action service return info.

        +-------+--------+-----------------------------------------------+
        |   0   |  byte  |  CRO command type                             |
        +-------+--------+-----------------------------------------------+
        |   1   |  byte  |  Counter (CTR)                                |
        +-------+--------+-----------------------------------------------+
        |  2,3  |  word  |  Action service number                        |
        +-------+--------+-----------------------------------------------+
        |  4..7 |  bytes |  Parameters, if applicable                    |
        +-------+--------+-----------------------------------------------+
        '''

        cmd = utils._parse_byte(msg[0])
        ctr = utils._parse_byte(msg[1])

        # spec shows two bytes for number but example only shows one byte
        action_service_num = utils._parse_2_byte_value(msg[2:4])
        params = utils._parse_4_byte_value(msg[4:])

        parsed = {'CMD': cmd, 'CTR': ctr, 'action_service_num': action_service_num, \
                  'params': params}

        return parsed

    def _parse_get_daq_size_CRO(self, msg):
        '''
        GET_DAQ_SIZE CRO

        Tells follower to return size of specified DAQ list as the # of
        available Object Descriptor Tables, and clears the current list.

        If specified list # is not available, size = 0 should be returned.

        +-------+--------+-----------------------------------------------+
        |   0   |  byte  |  CRO command type                             |
        +-------+--------+-----------------------------------------------+
        |   1   |  bytes |  Counter (CTR)                                |
        +-------+--------+-----------------------------------------------+
        |   2   |  byte  |  DAQ list number (0,1,...)                    |
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  Don't care                                   |
        +-------+--------+-----------------------------------------------+
        |  4..7 |  bytes |  Unsigned long CAN identifier of DTO          |
        |       |        |  dedicated to list number                     |
        +-------+--------+-----------------------------------------------+
        '''
        cmd = utils._parse_byte(msg[0])
        ctr = utils._parse_byte(msg[1])

        daq_list_num = utils._parse_byte(msg[2])
        can_dto_id = utils._parse_4_byte_value(msg[4:])

        parsed = {'CMD': cmd, 'CTR': ctr, 'daq_list_num': daq_list_num,
                  'can_dto_id': can_dto_id }

        return parsed

    def _parse_set_daq_ptr_CRO(self, msg):
        '''
        SET_DAQ_PTR CRO

        Tells follower to initialize the DAQ list pointer for a subsequent write to a DAQ list

        +-------+--------+-----------------------------------------------+
        |   0   |  byte  |  CRO command type                             |
        +-------+--------+-----------------------------------------------+
        |   1   |  byte  |  Counter (CTR)                                |
        +-------+--------+-----------------------------------------------+
        |   2   |  byte  |  DAQ list number (0,1,...)                    |
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  Object Descriptor Table ODT number (0,1,...) |
        +-------+--------+-----------------------------------------------+
        |   4   |  byte  |  Element number within ODT (0,1,...)          |
        +-------+--------+-----------------------------------------------+
        |  5..7 |  bytes |  Don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''
        cmd = utils._parse_byte(msg[0])
        ctr = utils._parse_byte(msg[1])

        daq_list_num = utils._parse_byte(msg[2])
        odt_num = utils._parse_byte(msg[3])
        odt_elem_num = utils._parse_byte(msg[4])

        parsed = {'CMD': cmd, 'CTR': ctr, 'daq_list_num': daq_list_num, \
                  'odt_num': odt_num, 'odt_elem_num': odt_elem_num}

        return parsed

    def _parse_write_daq_CRO(self, msg):
        '''
        WRITE_DAQ CRO

        Tells follower to write one entry to DAQ list defined by the DAQ list
        pointer (see SET_DAQ_PTR).

        Size of DAQ element in bytes: 1, 2, 4 are valid values but is dependent on ECU impl.

        +-------+--------+-----------------------------------------------+
        |   0   |  byte  |  CRO command type                             |
        +-------+--------+-----------------------------------------------+
        |   1   |  byte  |  Counter (CTR)                                |
        +-------+--------+-----------------------------------------------+
        |   2   |  byte  |  Size of DAQ element in bytes { 1, 2, 4 }     |
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  Address extension of DAQ element             |
        +-------+--------+-----------------------------------------------+
        |  4..7 |  bytes |  Unsigned long address of DAQ element         |
        +-------+--------+-----------------------------------------------+
        '''
        cmd = utils._parse_byte(msg[0])
        ctr = utils._parse_byte(msg[1])

        daq_elem_size = utils._parse_byte(msg[2])
        address_ext = utils._parse_byte(msg[3])
        address = utils._parse_4_byte_value(msg[4:])

        parsed = {'CMD': cmd, 'CTR': ctr, 'daq_elem_size': daq_elem_size, \
                  'address_ext': address_ext, 'address': address}

        return parsed

    def _parse_start_stop_CRO(self, msg):
        '''
        START_STOP CRO

        Tells follower to start or stop specified DAQ list

        Params:
        - Modes: 0x00 stops specified DAQ list, 0x01 starts specified DAQ list,
          0x02 prepares DAQ list for synchronised start.
        - Last ODT number specifies which ODTs (From 0 to Last ODT number) of
          the DAQ list should be transmitted.
        - Event Channel No #: specifies the generic signal source that effectively
          determines the data transmission timing.
        - Prescaler: >= 1, can reduce transmission rate

        +-------+--------+-----------------------------------------------+
        |   0   |  byte  |  CRO command type                             |
        +-------+--------+-----------------------------------------------+
        |   1   |  byte  |  Counter (CTR)                                |
        +-------+--------+-----------------------------------------------+
        |   2   |  byte  |  Mode (specified above)                       |
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  DAQ list number                              |
        +-------+--------+-----------------------------------------------+
        |   4   |  byte  |  Last ODT number                              |
        +-------+--------+-----------------------------------------------+
        |   5   |  byte  |  Event Channel number                         |
        +-------+--------+-----------------------------------------------+
        |  6..7 |  bytes |  Transmission rate prescaler                  |
        +-------+--------+-----------------------------------------------+
        '''
        cmd = utils._parse_byte(msg[0])
        ctr = utils._parse_byte(msg[1])

        mode = utils._parse_byte(msg[2])
        daq_list_num = utils._parse_byte(msg[3])
        last_odt_num = utils._parse_byte(msg[4])
        event_chan_num = utils._parse_byte(msg[5])
        prescaler = utils._parse_2_byte_value_motorola(msg[6:8])

        parsed = {'CMD': cmd, 'CTR': ctr, 'mode': mode, 'daq_list_num': daq_list_num, \
                  'last_odt_num': last_odt_num, 'event_chan_num': event_chan_num, \
                  'prescaler': prescaler }

        return parsed

    def _parse_start_stop_all_CRO(self, msg):
        '''
        START_STOP_ALL CRO

        Tells follower to start/stop periodic transmission of all DAQ lists that
        were previously configured with START_STOP command.

        +-------+--------+-----------------------------------------------+
        |   0   |  byte  |  CRO command type                             |
        +-------+--------+-----------------------------------------------+
        |   1   |  byte  |  Counter (CTR)                                |
        +-------+--------+-----------------------------------------------+
        |   2   |  byte  |  0x00 to stop transmission, 0x01 to start     |
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''
        cmd = utils._parse_byte(msg[0])
        ctr = utils._parse_byte(msg[1])
        mode = utils._parse_byte(msg[2])

        parsed = {'CMD': cmd, 'CTR': ctr, 'mode': mode }

        return parsed

    '''
    +---------------------------------------------------------------------+
    |                                                                     |
    |                 DTO CRM generation helper functions                 |
    |                                                                     |
    +---------------------------------------------------------------------+
    |  Use these to generate messages from a follower back to a leader    |
    +---------------------------------------------------------------------+
    '''

    def _generate_connect_CRM(self, return_code, counter):
        '''
        Possible return codes:
        - 0x00:  acknowledge (no error)
        - 0x33:  Session currently not possible
        - 0x32:  Invalid station address

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  Don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        msg = utils._gen_byte(CRM_START_VAL) + utils._gen_byte(return_code) + \
              utils._gen_byte(counter) + utils._gen_byte(DONT_CARE_VAL)*5

        return msg

    def _generate_disconnect_CRM(self, return_code, counter):
        '''
        Possible return codes:
        - 0x00:  acknowledge (no error)
        - 0x33:  Temporary disconnect not possible
        - 0x32:  Invalid station address, invalid temporary disconnect param

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  Don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        msg = utils._gen_byte(CRM_START_VAL) + utils._gen_byte(return_code) + \
              utils._gen_byte(counter) + utils._gen_byte(DONT_CARE_VAL)*5

        return msg

    def _generate_setMTA_CRM(self, return_code, counter):
        '''
        Possible return codes:
        - 0x00:  acknowledge (no error)
        - 0x33:  Attempted read of classified data
        - 0x32:  Illegal MTA#, base address, address ext.

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  Don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        msg = utils._gen_byte(CRM_START_VAL) + utils._gen_byte(return_code) + \
              utils._gen_byte(counter) + utils._gen_byte(DONT_CARE_VAL)*5

        return msg

    def _generate_dnload_CRM(self, return_code, counter, mta_extension, mta_address):
        '''
        Possible return codes:
        - 0x00:  acknowledge (no error)
        - 0x33:  Write attempt to ROM
        - 0x32:  Data block size >5

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  MTA0 extension (after post-increment)        |
        +-------+--------+-----------------------------------------------+
        |  4..7 |  ulong |  MTA0 address (after post-increment)          |
        +-------+--------+-----------------------------------------------+
        '''

        address = utils._gen_4_byte_val(mta_address)

        msg = utils._gen_byte(CRM_START_VAL) + utils._gen_byte(return_code) + \
              utils._gen_byte(counter) + utils._gen_byte(mta_extension) + address

        return msg

    def _generate_program_CRM(self, return_code, counter, mta_extension, mta_address):
        '''
        Possible return codes:
        - 0x00:  acknowledge (no error)
        - Others not listed

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  MTA0 extension (after post-increment)        |
        +-------+--------+-----------------------------------------------+
        |  4..7 |  ulong |  MTA0 address (after post-increment)          |
        +-------+--------+-----------------------------------------------+
        '''

        address = utils._gen_4_byte_val(mta_address)

        msg = utils._gen_byte(CRM_START_VAL) + utils._gen_byte(return_code) + \
              utils._gen_byte(counter) + utils._gen_byte(mta_extension) + address

        return msg

    def _generate_upload_CRM(self, return_code, counter, data):
        '''
        Possible return codes:
        - 0x00:  acknowledge (no error)
        - 0x33:  Upload of classified data
        - 0x32:  Data block size >5

        Right now, this returns 4 bytes back, not 5. Will need to change the
        util functions to support variable byte sizes.

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  requested data bytes                         |
        +-------+--------+-----------------------------------------------+
        '''

        msg = utils._gen_byte(CRM_START_VAL) + utils._gen_byte(return_code) + \
              utils._gen_byte(counter) + utils._gen_4_byte_val(data) + utils._gen_byte(DONT_CARE_VAL)

        return msg

    def _generate_clear_memory_CRM(self, return_code, counter):
        '''
        Possible return codes:
        - 0x00:  acknowledge (no error)
        - Others not listed

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  Don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        msg = utils._gen_byte(CRM_START_VAL) + utils._gen_byte(return_code) + \
              utils._gen_byte(counter) + utils._gen_byte(DONT_CARE_VAL)*5

        return msg

    def _generate_move_CRM(self, return_code, counter):
        '''
        Possible return codes:
        - 0x00:  acknowledge (no error)
        - Others not listed

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  Don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        msg = utils._gen_byte(CRM_START_VAL) + utils._gen_byte(return_code) + \
              utils._gen_byte(counter) + utils._gen_byte(DONT_CARE_VAL)*5

        return msg

    def _generate_test_CRM(self, return_code, counter):
        '''
        Possible return codes:
        - 0x00:  acknowledge (no error)
        - Others not listed

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  Don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        msg = utils._gen_byte(CRM_START_VAL) + utils._gen_byte(return_code) + \
              utils._gen_byte(counter) + utils._gen_byte(DONT_CARE_VAL)*5

        return msg

    def _generate_exchangeID_CRM(self, return_code, counter, follower_device_id_length, data_type_qualifier, availability_mask, protection_mask):
        '''
        Possible return codes:
        - 0x00:  acknowledge (no error)
        - 0x33:  Illegal leader ID

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  length of follower device ID in bytes        |
        +-------+--------+-----------------------------------------------+
        |   4   |  byte  |  data type qualifier of follower device ID    |
        |       |        |  (optional and implementation specific)       |                          |
        +-------+--------+-----------------------------------------------+
        |   5   |  byte  |  Resource Availability Mask                   |
        +-------+--------+-----------------------------------------------+
        |   6   |  byte  |  Resource Protection Mask                     |
        +-------+--------+-----------------------------------------------+
        |   7   |  byte  |  Don't care                                   |
        +-------+--------+-----------------------------------------------+

        Use the following resource mask to parse availability and protection statuses.

        Resource Mask:
        +-----+-----+-----+-----+-----+-----+-----+-----+
        |  7  |  6  |  5  |  4  |  3  |  2  |  1  |  0  |
        +-----+-----+-----+-----+-----+-----+-----+-----+
        |  X  | PGM |  X  |  X  |  X  |  X  | DAQ | CAL |
        +-----+-----+-----+-----+-----+-----+-----+-----+

        PGM:  Memory Programming
        DAQ:  Data Acquisition
        CAL:  Calibration
        '''

        msg = utils._gen_byte(CRM_START_VAL) + utils._gen_byte(return_code) + \
              utils._gen_byte(counter) + utils._gen_byte(follower_device_id_length) + \
              utils._gen_byte(data_type_qualifier) + utils._gen_byte(availability_mask) + \
              utils._gen_byte(protection_mask) + utils._gen_byte(DONT_CARE_VAL)

        return msg

    def _generate_ccp_version_CRM(self, return_code, counter, main_protocol, minor_protocol):
        '''
        Possible return codes:
        - 0x00:  acknowledge (no error)
        - Others not listed

        This mirrors the CTO, where the leader sends out a message with what it
        hopes the major and minor versions are.  Apparent redundancy because
        the follower has to answer back with both a status message and the
        major and minor versions.

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  Main Protocol version as implemented         |
        +-------+--------+-----------------------------------------------+
        |   4   |  byte  |  Release within version as implemented        |
        +-------+--------+-----------------------------------------------+
        | 5..7  |  bytes |  Don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        msg = utils._gen_byte(CRM_START_VAL) + utils._gen_byte(return_code) + \
              utils._gen_byte(counter) + utils._gen_byte(main_protocol) + \
              utils._gen_byte(minor_protocol) + utils._gen_byte(DONT_CARE_VAL)*3

        return msg

    def _generate_get_seed_CRM(self, return_code, counter, protection_status, seed_data):
        '''
        Possible return codes:
        - 0x00:  acknowledge (no error)
        - Others not listed

        If protection status = false, UNLOCK is not needed.

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  Protection status (TRUE or FALSE)            |
        +-------+--------+-----------------------------------------------+
        |  4..7 |  bytes |  'seed' data                                  |
        +-------+--------+-----------------------------------------------+
        '''

        msg = utils._gen_byte(CRM_START_VAL) + utils._gen_byte(return_code) + \
              utils._gen_byte(counter) + utils._gen_byte(protection_status) + \
              utils._gen_4_byte_val(seed_data)

        return msg

    def _generate_build_chksum_CRM(self, return_code, counter, checksum_data_size, checksum_data):
        '''
        Possible return codes:
        - 0x00:  acknowledge (no error)
        - Others not listed

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  size of checksum data                        |
        +-------+--------+-----------------------------------------------+
        |  4..7 |  bytes |  checksum data (implementation specific)      |
        +-------+--------+-----------------------------------------------+
        '''

        msg = utils._gen_byte(CRM_START_VAL) + utils._gen_byte(return_code) + \
              utils._gen_byte(counter) + utils._gen_byte(checksum_data_size) + \
              utils._gen_4_byte_val(checksum_data)

        return msg

    def _generate_unlock_CRM(self, return_code, counter, resource_mask):
        '''
        Possible return codes:
        - 0x00:  acknowledge (no error)
        - 0x35:  Unqualified key

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  Current Privilege Status (Resource Mask)     |
        +-------+--------+-----------------------------------------------+
        |  4..7 |  bytes |  don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        msg = utils._gen_byte(CRM_START_VAL) + utils._gen_byte(return_code) + \
              utils._gen_byte(counter) + utils._gen_byte(resource_mask) + \
              utils._gen_byte(DONT_CARE_VAL)*4

        return msg

    def _generate_set_s_status_CRM(self, return_code, counter):
        '''
        Possible return codes:
        - 0x00:  acknowledge (no error)
        - 0x33:  status bits violate leader privilege level
        - 0x32:  Currently illegal combination of status bits

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  Don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''
        msg = utils._gen_byte(CRM_START_VAL) + utils._gen_byte(return_code) + \
              utils._gen_byte(counter) + utils._gen_byte(DONT_CARE_VAL)*5

        return msg

    def _generate_get_s_status_CRM(self, return_code, counter, session_status, addl_status_qual, addl_status_info=None):
        '''
        Possible return codes:
        - 0x00:  acknowledge (no error)
        - 0x33:  Session status not accessible

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  Session status                               |
        +-------+--------+-----------------------------------------------+
        |   4   |  byte  |  additional status information qualifier      |
        +-------+--------+-----------------------------------------------+
        |  5..7 |  bytes |  additional status information (optional)     |
        +-------+--------+-----------------------------------------------+
        '''
        addl_info_bytes = utils._gen_byte(DONT_CARE_VAL)*3

        msg = utils._gen_byte(CRM_START_VAL) + utils._gen_byte(return_code) + \
              utils._gen_byte(counter) + utils._gen_byte(session_status) + \
              utils._gen_byte(addl_status_qual) + addl_info_bytes

        return msg

    def _generate_select_cal_page_CRM(self, return_code, counter):
        '''
        This command's function depends on the ECU implementation. The previously
        initialized MTA0 points to the start of the calibration data page that
        is selected as the currently active page by this command.

        Possible return codes:
        - 0x00:  acknowledge (no error)

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        msg = utils._gen_byte(CRM_START_VAL) + utils._gen_byte(return_code) + \
              utils._gen_byte(counter) + utils._gen_byte(DONT_CARE_VAL)*5

        return msg

    def _generate_get_active_cal_page_CRM(self, return_code, counter, address_ext, address):
        '''
        This command returns the start address of the calibration page that is
        currently active in the follower device.

        Possible return codes: not specified

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  address extension                            |
        +-------+--------+-----------------------------------------------+
        |  4..7 |  bytes |  unsigned long address                        |
        +-------+--------+-----------------------------------------------+
        '''

        msg = utils._gen_byte(CRM_START_VAL) + utils._gen_byte(return_code) + \
              utils._gen_byte(counter) + utils._gen_byte(address_ext) + \
              utils._gen_4_byte_val(address)

        return msg

    def _generate_diag_service_CRM(self, return_code, counter, return_len, data_type_qual):
        '''
        The follower device carries out the requested service and automatically
        sets the Memory Transfer Address MTA0 to the location from which the
        CCP leader device (host) may subsequently upload the requested
        diagnostic service return information.

        Then the follower device will respond back with the following contents:

        Notes:
        - Data type qualifier is implementation-specific.

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  length of return information (in bytes)      |
        +-------+--------+-----------------------------------------------+
        |   4   |  byte  |  data type qualifier of return information    |
        +-------+--------+-----------------------------------------------+
        |  5..7 |  bytes |  don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        msg = utils._gen_byte(CRM_START_VAL) + utils._gen_byte(return_code) + \
              utils._gen_byte(counter) + utils._gen_byte(return_len) + \
              utils._gen_byte(data_type_qual) + utils._gen_byte(DONT_CARE_VAL)*3

        return msg

    def _generate_action_service_CRM(self, return_code, counter, return_len, data_type_qual):
        '''
        The follower device carries out the requested service and automatically
        sets the Memory Transfer Address MTA0 to the location from which the CCP
        leader device may subsequently upload the requested action service
        return information (if applicable).

        Notes:
        - Data type qualifier is implementation-specific.

        Then the follower device will respond back with the following contents:

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  length of return information (in bytes)      |
        +-------+--------+-----------------------------------------------+
        |   4   |  byte  |  data type qualifier of return information    |
        +-------+--------+-----------------------------------------------+
        |  5..7 |  bytes |  don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        msg = utils._gen_byte(CRM_START_VAL) + utils._gen_byte(return_code) + \
              utils._gen_byte(counter) + utils._gen_byte(return_len) + \
              utils._gen_byte(data_type_qual) + utils._gen_byte(DONT_CARE_VAL)*3

        return msg

    def _generate_get_daq_size_CRM(self, return_code, counter, daq_list_size, first_pid):
        '''
        Returns the size of the specified DAQ list as the number of available
        Object Descriptor Tables (ODTs) and clears the current list.

        If the specified list number is not available, size = 0 should be returned.

        The PID of a specific ODT of a DAQ list is determined by:
          PID = First PID of DAQ list + ODT number

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  DAQ list size (= # of ODTs in this list)     |
        +-------+--------+-----------------------------------------------+
        |   4   |  byte  |  First PID of DAQ list                        |
        +-------+--------+-----------------------------------------------+
        |  5..7 |  bytes |  don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        msg = utils._gen_byte(CRM_START_VAL) + utils._gen_byte(return_code) + \
              utils._gen_byte(counter) + utils._gen_byte(daq_list_size) + \
              utils._gen_byte(first_pid) + utils._gen_byte(DONT_CARE_VAL)*3

        return msg

    def _generate_set_daq_ptr_CRM(self, return_code, counter):
        '''
        Initializes the DAQ list pointer for a subsequent write to a DAQ list.
        See 'Organization of Data Acquisition Messages' from https://automotivetechis.files.wordpress.com/2012/06/ccp211.pdf

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        msg = utils._gen_byte(CRM_START_VAL) + utils._gen_byte(return_code) + \
              utils._gen_byte(counter) + utils._gen_byte(DONT_CARE_VAL)*5

        return msg

    def _generate_write_daq_CRM(self, return_code, counter):
        '''
        Follower should write one entry (description of a single DAQ element)
        to a DAQ list defined by the DAQ list pointer (SET_DAQ_PTR, separate command).

        The leader device needs to manage any ECU limitations.
        THe follower device must manage DAQ element bytes consistently.

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        msg = utils._gen_byte(CRM_START_VAL) + utils._gen_byte(return_code) + \
              utils._gen_byte(counter) + utils._gen_byte(DONT_CARE_VAL)*5

        return msg

    def _generate_start_stop_CRM(self, return_code, counter):
        '''
        START_STOP command will start or stop data acquistion, or prepare a
        synchronized start of the specified DAQ list.

        The CRO from the leader device specifies modes, what to transmit, and so on.
        The follower device just reports back a status code.

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        msg = utils._gen_byte(CRM_START_VAL) + utils._gen_byte(return_code) + \
              utils._gen_byte(counter) + utils._gen_byte(DONT_CARE_VAL)*5

        return msg

    def _generate_start_stop_all_CRM(self, return_code, counter):
        '''
        Same as START_STOP but will start (or stop) ALL previously stopped/started
        DAQ lists. The follower device just reports back a status code.

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        msg = utils._gen_byte(CRM_START_VAL) + utils._gen_byte(return_code) + \
              utils._gen_byte(counter) + utils._gen_byte(DONT_CARE_VAL)*5

        return msg
