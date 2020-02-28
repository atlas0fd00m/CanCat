#!/usr/bin/env python
import sys
import time
import cancat
import struct
import threading

COUNTER_VAL = 0x20

from utils import *

from utils import _gen_byte, _gen_2_byte_val, _gen_4_byte_val, _parse_byte, _parse_2_byte_value, _parse_4_byte_value

'''
    MESSAGE TYPES:

    CRO (Command Receive Object): message sent from the leader device to the
        follower device(s).
    CRM (Command Return Message): one type of message sent from the follower device
        to the leader device containing command / error code and command counter.
    DTO (Data Transmission Object): message sent from the follower device to the
        leader device (Command Return Message or Event Message or Data Acquisition Message).

    FYI:
        For all data transfered by the CCP no byte order for the protocol itself
        is defined. Because the data organisation depends on the ECU's CPU,
        the byte ordering is defined in the follower device description file.
        The only exceptions are the station addresses in the TEST, CONNECT
        and DISCONNECT commands.
'''

class CCPLeader(object):
    def __init__(self, c, tx_arbid=None, rx_arbid=None, verbose=True, extflag=0):
        self.c = c
        self.verbose = verbose
        self.extflag = extflag

        self.tx_arbid = tx_arbid
        self.rx_arbid = rx_arbid

    def _do_Function(self, msg, command_type, currIdx, timeout=1):
        self.c._send(cancat.CMD_CAN_SEND, msg)

        found = False
        complete = False
        starttime = lasttime = time.time()

        while not complete and (not timeout or (lasttime-starttime < timeout)):
            time.sleep(0.01)
            # JL:  only expect back one message?
            msgs = [msg for msg in self.c.genCanMsgs(start=currIdx, arbids=[self.rx_arbid])]

            if len(msgs):
                try:
                    for msg in msgs:
                        # TODO will need to change this later to support Event Messages, and call _parse_DTO instead
                        return self._parse_Command_Return_Message(msg, command_type)
                except Exception as e:
                    #print e # debugging only, this is expected
                    pass

            lasttime = time.time()

        return None

    '''
    +---------------------------------------------------------------------+
    |                                                                     |
    |               Command Receive Object helper functions               |
    |                                                                     |
    +---------------------------------------------------------------------+
    '''

    def _constructCRO(self, cmd, ctr, cmd_data):
        msg = _gen_byte(cmd) + _gen_byte(ctr) + cmd_data

        if len(msg) != 8:
            raise Exception("Invalid message length")

        return msg

    def _connect_CRO(self, counter, stat_addr):
        '''
        CRO

        data to be sent after CMD and CTR values:
        +-------+--------+-----------------------------------------------+
        |  2,3  |  word  |  station address (Intel format)               |
        +-------+--------+-----------------------------------------------+
        | 4..7  |  bytes |  don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''
        station_address = _gen_2_byte_val(stat_addr)

        data = station_address + _gen_byte(DONT_CARE_VAL)*4

        msg = self._constructCRO(CCP_CONNECT, counter, data)

        return msg

    def _exchangeID_CRO(self, counter, leader_id_information=None):
        '''
        EXCHANGE_ID CRO

        Note:  unsure what to do for the bytes 2..7 so leaving as "don't cares"
        as shown in the example.

        The CCP leader and follower stations exchange IDs for automatic session
        configuration. This might include automatic assignment of a data
        acquisition setup file depending on the follower's returned ID (Plug-n-Play).

        data to be sent after CMD and CTR values:
        +-------+--------+-----------------------------------------------+
        | 2..7  |  bytes |  CCP leader device ID information             |
        |       |        |  (optional and implementation specific)       |
        +-------+--------+-----------------------------------------------+
        '''

        if leader_id_information is not None:
            if len(leader_id_information) > 6:
                raise Exception("Leader ID info cannot be longer than 6 bytes")
            else:
                padding = 6 - leader_id_information
                dont_care = _gen_byte(DONT_CARE_VAL)*padding
                data = leader_id_information + dont_care
        else:
            data = _gen_byte(DONT_CARE_VAL)*6

        msg = self._constructCRO(CCP_EXCHANGE_ID, counter, data)

        return msg

    def _set_MTA_CRO(self, counter, mta_number, address_extension, address):
        '''
        SET_MTA CRO

        This CRO sets the memory address to later read to or write from.

        This function sets MTA0 or MTA1, depending on bit 2.
        - MTA0 is used by the commands DNLOAD, UPLOAD, DNLOAD_6,
        SELECT_CAL_PAGE, CLEAR_MEMORY, PROGRAM and PROGRAM_6.
        - MTA1 is used by the MOVE command.

        Data to be sent after CMD and CTR values:
        +-------+--------+-----------------------------------------------+
        |   2   |  byte  |  Memory transfer address MTA number (0,1)     |
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  Address extension                            |
        +-------+--------+-----------------------------------------------+
        | 4..7  |  ulong |  Address                                      |
        +-------+--------+-----------------------------------------------+
        '''

        if mta_number != 0 and mta_number != 1:
            raise Exception("Invalid mta_number.  Must be either 1 for MTA1 " \
            "(MOVE) or 1 for MTA0 (all other read/write commands)")

        data = _gen_byte(mta_number) + _gen_byte(address_extension) + _gen_4_byte_val(address)

        msg = self._constructCRO(CCP_SET_MTA, counter, data)

        return msg

    def _download_CRO(self, counter, data_to_download, data_block_size=4):
        '''
        CRO

        Will download value to the follower device at address of MTA0.

        ***************************************************************************
        ** You must set MTA0 with the SET_MTA command before using this function **
        ***************************************************************************

        data to be sent after CMD and CTR values:
        +-------+--------+-----------------------------------------------+
        |   2   |  byte  |  size of data block to follow in bytes        |
        +-------+--------+-----------------------------------------------+
        | 3..7  |  bytes |  data to be transferred (up to 5 bytes)       |
        +-------+--------+-----------------------------------------------+
        '''

        if data_block_size > 5:
            raise Exception("Cannot download data block larger than 5")

        if data_block_size < 5:
            padding = 5 - data_block_size
            dont_care = _gen_byte(DONT_CARE_VAL)*padding

        data = _gen_byte(data_block_size) + _gen_4_byte_val(data_to_download) + dont_care

        msg = self._constructCRO(CCP_DNLOAD, counter, data)

        return msg

    def _upload_CRO(self, counter, data_block_size=4):
        '''
        CRO

        ***************************************************************************
        ** You must set MTA0 with the SET_MTA command before using this function **
        ***************************************************************************

        A data block of the specified length (size), starting at current MTA0,
        will be copied into the corresponding DTO data field.

        The MTA0 pointer will be post-incremented by the value of 'size'.

        data to be sent after CMD and CTR values:
        +-------+--------+-----------------------------------------------+
        |   2   |  byte  | Size of data block to be uploaded in bytes    |
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes | don't care                                    |
        +-------+--------+-----------------------------------------------+
        '''

        if data_block_size > 5:
            raise Exception("Cannot upload data block larger than 5")

        data = _gen_byte(data_block_size) + _gen_byte(DONT_CARE_VAL)*5

        msg = self._constructCRO(CCP_UPLOAD, counter, data)

        return msg

    def _disconnect_CRO(self, counter, disconnect_type, stat_addr):
        '''
        CRO

        Data to be sent after CMD and CTR values:
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

        station_address = _gen_2_byte_val(stat_addr)

        dont_care = _gen_byte(DONT_CARE_VAL)

        data = _gen_byte(disconnect_type) + dont_care \
               + station_address + dont_care*2

        msg = self._constructCRO(CCP_DISCONNECT, counter, data)

        return msg

    def _program_CRO(self, counter, data_to_program, data_block_size=4):
        '''
        PROGRAM CRO

        ***************************************************************************
        ** You must set MTA0 with the SET_MTA command before using this function **
        ***************************************************************************

        Data block will be programmed into non-volatile memory (FLASH, EEPROM),
        starting at current MTA0. The MTA0 pointer will be post-incremented
        by the value of 'size'.

        data to be sent after CMD and CTR values:
        +-------+--------+-----------------------------------------------+
        |   2   |  byte  |  size of data block to follow in bytes        |
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  Data to be programmed (max. 5 bytes)         |
        +-------+--------+-----------------------------------------------+
        '''

        if data_block_size > 5:
            raise Exception("Cannot program data block larger than 5")

        if data_block_size < 5:
            padding = 5 - data_block_size
            dont_care = _gen_byte(DONT_CARE_VAL)*padding

        data = _gen_byte(data_block_size) + _gen_4_byte_val(data_to_program) + dont_care

        msg = self._constructCRO(CCP_PROGRAM, counter, data)

        return msg

    def _move_CRO(self, counter, data_block_size):
        '''
        MOVE CRO

        ***************************************************************************
        ** You must set MTA0 with the SET_MTA command before using this function **
        ***************************************************************************

        ***************************************************************************
        ** You must set MTA1 with the SET_MTA command before using this function **
        ***************************************************************************

        A data block of the specified length (size) will be copied from the
        address defined by MTA 0 (source pointer) to the address defined by
        MTA 1 (destination pointer).

        data to be sent after CMD and CTR values:
        +-------+--------+-----------------------------------------------+
        |  2..5 |  long  | Size (num of bytes) of data block to be moved |
        +-------+--------+-----------------------------------------------+
        |  6,7  |  bytes | Don't care                                    |
        +-------+--------+-----------------------------------------------+
        '''

        dont_care = _gen_byte(DONT_CARE_VAL)*2

        data = _gen_4_byte_val(data_block_size) + dont_care

        msg = self._constructCRO(CCP_MOVE, counter, data)

        return msg

    def _clear_memory_CRO(self, counter, data_block_size):
        '''
        CLEAR_MEMORY CRO

        Can be used to erase FLASH EPROM prior to reprogramming.
        Erases memory at location of the MTA0 pointer.

        ***************************************************************************
        ** You must set MTA0 with the SET_MTA command before using this function **
        ***************************************************************************

        data to be sent after CMD and CTR values:
        +-------+--------+-----------------------------------------------+
        |  2..5 |  long  |  Memory size                                  |
        +-------+--------+-----------------------------------------------+
        |  6,7  |  bytes |  don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        dont_care = _gen_byte(DONT_CARE_VAL)*2

        data = _gen_4_byte_val(data_block_size) + dont_care

        msg = self._constructCRO(CCP_CLEAR_MEMORY, counter, data)

        return msg

    def _test_CRO(self, counter, stat_addr):
        '''
        TEST CRO

        This command is used to test if the slave with the specified station
        address is available for CCP communication. This command does not
        establish a logical connection nor does it trigger any activities in
        the specified follower.

        data to be sent after CMD and CTR values:
        +-------+--------+-----------------------------------------------+
        |  2,3  |  word  |  station address (little-endian)              |
        +-------+--------+-----------------------------------------------+
        | 4..7  |  bytes |  don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        station_address = _gen_2_byte_val(stat_addr)

        dont_care = _gen_byte(DONT_CARE_VAL)*4

        data = station_address + dont_care

        msg = self._constructCRO(CCP_TEST, counter, data)

        return msg

    def _get_ccp_version_CRO(self, counter, major_version, minor_version):
        '''
        GET_CCP_VERSION CRO

        This command performs a mutual identification of the protocol version
        used in the leader and in the follower device to agree on a common
        protocol version. This command is expected to be executed prior to
        the EXCHANGE_ID command.

        Data to be sent after CMD and CTR values:
        +-------+--------+-----------------------------------------------+
        |   2   |  byte  |  Desired Main Protocol version                |
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  Desired minor vers (release w/i major vers)  |
        +-------+--------+-----------------------------------------------+
        | 4..7  |  bytes |  Don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        maj_version = _gen_byte(major_version)

        min_version = _gen_byte(minor_version)

        dont_care = _gen_byte(DONT_CARE_VAL)*4

        data = maj_version + min_version + dont_care

        msg = self._constructCRO(CCP_GET_CCP_VERSION, counter, data)

        return msg

    def _get_seed_CRO(self, counter, requested_resource):
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
        |   2   |  byte  |  Requested follower resource or function **   |
        +-------+--------+-----------------------------------------------+
        | 3..7  |  bytes |  Don't care                                   |
        +-------+--------+-----------------------------------------------+

        ** See "Resource Mask" info above

        '''

        dont_care = _gen_byte(DONT_CARE_VAL)*5

        resource = _gen_byte(requested_resource)

        data = resource + dont_care

        msg = self._constructCRO(CCP_GET_SEED, counter, data)

        return msg

    def _unlock_CRO(self, counter, key):
        '''
        UNLOCK CRO

        Unlocks the follower device's security protection (if applicable) using
        a "key" computed from "seed" (do a GET_SEED CRO first).

        Part of spec makes it sound like the returned value must be turned into
        a key by the leader device, whereas another part makes it sound like the
        follower device will return the key.

        +-------+--------+-----------------------------------------------+
        |  2..  |  bytes |  Key computed with GET_SEED seed              |
        +-------+--------+-----------------------------------------------+
        '''

        # if key is less than 6 bytes long, pad with "don't care"s
        if len(key) > 6:
            raise Exception("Key cannot be longer than 6 bytes")

        if len(key) <= 6:
            padding = 6 - len(key)
            dont_care = _gen_byte(DONT_CARE_VAL)*padding

        data = key + dont_care

        msg = self._constructCRO(CCP_UNLOCK, counter, data)

        return msg

    def _build_chksum_CRO(self, counter, data_block_size):
        '''
        BUILD_CHKSUM CRO

        ***************************************************************************
        ** You must set MTA0 with the SET_MTA command before using this function **
        ***************************************************************************

        Data to be sent after CMD and CTR values:
        +-------+--------+-----------------------------------------------+
        |  2..5 |  ulong |  Block size in bytes                         |
        +-------+--------+-----------------------------------------------+
        |  6,7  |  bytes |  Don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        dont_care = _gen_byte(DONT_CARE_VAL)*2

        data = _gen_4_byte_val(data_block_size) + dont_care

        msg = self._constructCRO(CCP_BUILD_CHKSUM, counter, data)

        return msg

    def _short_upload_CRO(self, counter, address, address_extension, data_block_size=4):
        '''
        BUILD_CHKSUM CRO

        ***************************************************************************
        ** You must set MTA0 with the SET_MTA command before using this function **
        ***************************************************************************

        Data to be sent after CMD and CTR values:
        +-------+--------+-----------------------------------------------+
        |   2   |  byte  | Size of data block to be uploaded (1-5 bytes) |
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  | Address extension                             |
        +-------+--------+-----------------------------------------------+
        |  4..7 |  ulong | Address                                       |
        +-------+--------+-----------------------------------------------+
        '''

        if data_block_size < 1 or data_block_size > 5:
            raise Exception("Data block size must bye 1-5 bytes")

        data = _gen_byte(data_block_size) + _gen_byte(address_extension) + _gen_4_byte_val(address)

        msg = self._constructCRO(CCP_SHORT_UP, counter, data)

        return msg

    def _get_s_status_CRO(self, counter):
        '''
        GET_S_STATUS CRO

        Data to be sent after CMD and CTR values:
        +-------+--------+-----------------------------------------------+
        |  2..7 |  bytes |  don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''
        data = _gen_byte(DONT_CARE_VAL)*6

        msg = self._constructCRO(CCP_GET_S_STATUS, counter, data)

        return msg

    def _set_s_status_CRO(self, counter, session_status_mask):
        '''
        SET_S_STATUS CRO

        Tells follower what the current status is

        Data to be sent after CMD and CTR values:
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

        data = _gen_byte(session_status_mask) + _gen_byte(DONT_CARE_VAL)*5

        msg = self._constructCRO(CCP_GET_S_STATUS, counter, data)

        return msg


    '''
    +---------------------------------------------------------------------+
    |                                                                     |
    |                 Data Transmission Object functions                  |
    |                                                                     |
    +---------------------------------------------------------------------+
    '''

    def _parse_DTO(self, CCP_message):
        if len(CCP_message) != 8:
            raise Exception("CCP message should have length 8")

        if CCP_message[0] == b'\xFF':
            # CRM message: if DTO is sent as an answer to a CRO from the leader device.
            self._parse_Command_Return_Message(CCP_message)
        elif CCP_message[0] == b'\xFE':
            # Event Message: if the DTO reports internal follower status changes
            # in order to invoke error recovery or other services
            self._parse_EventMessage(CCP_message)
        # elif
            # Data Aquisition Message: if the DTO contains measurement data
        else:
            raise Exception("CCP message has invalid starting byte")

    def _parse_Command_Return_Message(self, CCP_message, CCP_CRO_Type):
        '''
        Command Return Messages return data based on the command type originally
        sent to the follower device.

        Currently unsure how the "counter" is used (as a session id, command id, etc)
        
        All DTOs of type CRM* should start off with this format:
        +-------+--------+-----------------------------------------------+
        |   0   |  byte  |  0xFF                                         |
        +-------+--------+-----------------------------------------------+
        |   1   |  byte  |  Command Return Code                          |
        +-------+--------+-----------------------------------------------+
        |   2   |  byte  |  Command Counter = CTR                        |
        +-------+--------+-----------------------------------------------+

        Bytes 3-7 vary by response type.

        *There are other types, like EventMessage, but these are not supported yet.
        '''

        if CCP_CRO_Type == CCP_CONNECT:
            parsed_msg = self._parse_connect_CRM(CCP_message)
        elif CCP_CRO_Type == CCP_DISCONNECT:
            parsed_msg = self._parse_disconnect_CRM(CCP_message)
        elif CCP_CRO_Type == CCP_SET_MTA:
            parsed_msg = self._parse_setMTA_CRM(CCP_message)
        elif CCP_CRO_Type == CCP_DNLOAD:
            parsed_msg = self._parse_dnload_CRM(CCP_message)
        elif CCP_CRO_Type == CCP_UPLOAD:
            parsed_msg = self._parse_upload_CRM(CCP_message)
        elif CCP_CRO_Type == CCP_SHORT_UP:
            parsed_msg = self._parse_upload_CRM(CCP_message)
        elif CCP_CRO_Type == CCP_CLEAR_MEMORY:
            parsed_msg = self._parse_clear_memory_CRM(CCP_message)
        elif CCP_CRO_Type == CCP_MOVE:
            parsed_msg = self._parse_move_CRM(CCP_message)
        elif CCP_CRO_Type == CCP_TEST:
            parsed_msg = self._parse_test_CRM(CCP_message)
        elif CCP_CRO_Type == CCP_PROGRAM:
            parsed_msg = self._parse_program_CRM(CCP_message)
        elif CCP_CRO_Type == CCP_EXCHANGE_ID:
            parsed_msg = self._parse_exchangeID_CRM(CCP_message)
        elif CCP_CRO_Type == CCP_GET_CCP_VERSION:
            parsed_msg = self._parse_ccp_version_CRM(CCP_message)
        elif CCP_CRO_Type == CCP_GET_SEED:
            parsed_msg = self._parse_get_seed_CRM(CCP_message)
        elif CCP_CRO_Type == CCP_BUILD_CHKSUM:
            parsed_msg = self._parse_build_chksum_CRM(CCP_message)
        elif CCP_CRO_Type == CCP_UNLOCK:
            parsed_msg = self._parse_unlock_CRM(CCP_message)
        elif CCP_CRO_Type == CCP_SET_S_STATUS:
            parsed_msg = self._parse_set_s_status_CRM(CCP_message)
        elif CCP_CRO_Type == CCP_GET_S_STATUS:
            parsed_msg = self._parse_get_s_status_CRM(CCP_message)
        else:
            raise Exception("Cannot parse message type ", CCP_CRO_Type)

        return parsed_msg

        # 2nd byte is CTR and should match sent message

    def _parse_connect_CRM(self, CCP_message):
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

        return self._CRM_parser_status_ctr_only(CCP_message)

    def _parse_disconnect_CRM(self, CCP_message):
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

        return self._CRM_parser_status_ctr_only(CCP_message)

    def _parse_setMTA_CRM(self, CCP_message):
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

        return self._CRM_parser_status_ctr_only(CCP_message)

    def _parse_dnload_CRM(self, CCP_message):
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

        crc_byte = ord(CCP_message[1]) # is this python 3 compatible?
        crc_tuple = COMMAND_RET_CODES.get(crc_byte)
        counter = _parse_byte(CCP_message[2])

        if crc_byte == 0x00:
            mta0_address_ext = _parse_byte(CCP_message[3])
            mta0_address = _parse_4_byte_value(CCP_message[4:])
            msg = {'CRC': crc_tuple[0], 'CTR': counter, 'mta_extension': mta0_address_ext, 'mta_address': mta0_address}
        else:
            msg = {'CRC': crc_tuple[0], 'CTR': counter}

        return msg

    def _parse_program_CRM(self, CCP_message):
        '''
        Possible return codes:
        - 0x00:  acknowledge (no error)
        - ???  others not listed

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  MTA0 extension (after post-increment)        |
        +-------+--------+-----------------------------------------------+
        |  4..7 |  ulong |  MTA0 address (after post-increment)          |
        +-------+--------+-----------------------------------------------+
        '''

        crc_byte = ord(CCP_message[1]) # is this python 3 compatible?
        crc_tuple = COMMAND_RET_CODES.get(crc_byte)
        counter = _parse_byte(CCP_message[2])

        if crc_byte == 0x00:
            mta0_address_ext = _parse_byte(CCP_message[3])
            mta0_address = _parse_4_byte_value(CCP_message[4:])
            msg = {'CRC': crc_tuple[0], 'CTR': counter, 'mta_extension': mta0_address_ext, 'mta_address': mta0_address}
        else:
            msg = {'CRC': crc_tuple[0], 'CTR': counter}

        return msg

    def _parse_upload_CRM(self, CCP_message, read_length=4):
        '''
        Possible return codes:
        - 0x00:  acknowledge (no error)
        - 0x33:  Upload of classified data
        - 0x32:  Data block size >5

        Right now, this returns 4 bytes back, not 5.  Will need to change the
        struct.unpack to support variable byte sizes.

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  requested data bytes                         |
        +-------+--------+-----------------------------------------------+
        '''

        crc_byte = ord(CCP_message[1]) # is this python 3 compatible?
        crc_tuple = COMMAND_RET_CODES.get(crc_byte)
        counter = _parse_byte(CCP_message[2])

        if crc_byte == 0x00:
            returned_data = _parse_4_byte_value(CCP_message[3:7])
            msg = {'CRC': crc_tuple[0], 'CTR': counter, 'data': returned_data}
        else:
            msg = {'CRC': crc_tuple[0], 'CTR': counter}

        return msg

    def _parse_clear_memory_CRM(self, CCP_message):
        '''
        Possible return codes:
        - 0x00:  acknowledge (no error)
        - ???  Others not listed

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  Don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        return self._CRM_parser_status_ctr_only(CCP_message)

    def _parse_move_CRM(self, CCP_message):
        '''
        Possible return codes:
        - 0x00:  acknowledge (no error)
        - ??? Others not listed

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  Don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        return self._CRM_parser_status_ctr_only(CCP_message)

    def _parse_test_CRM(self, CCP_message):
        '''
        Possible return codes:
        - 0x00:  acknowledge (no error)
        - ???  Others not listed

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  Don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        return self._CRM_parser_status_ctr_only(CCP_message)

    def _parse_exchangeID_CRM(self, CCP_message):
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

        crc_byte = ord(CCP_message[1]) # is this python 3 compatible?
        crc_tuple = COMMAND_RET_CODES.get(crc_byte)
        counter = ord(CCP_message[2])

        follower_deviceID_length = _parse_byte(CCP_message[3])
        follower_deviceID_data_type_qual = _parse_byte(CCP_message[4])
        resource_availability_mask = _parse_byte(CCP_message[5])
        resource_protection_mask = _parse_byte(CCP_message[6])

        return {'CRC': crc_tuple[0], \
                'CTR': counter, \
                'follower_deviceID_length': follower_deviceID_length, \
                'follower_deviceID_data_type_qual': follower_deviceID_data_type_qual, \
                'resource_availability_mask': resource_availability_mask, \
                'resource_protection_mask': resource_protection_mask, \
               }

    def _parse_ccp_version_CRM(self, CCP_message):
        '''
        Possible return codes:
        - 0x00:  acknowledge (no error)
        - ???  Others not listed

        This mirrors the CTO, where the leader sends out a message with what it
        hopes the major and minor versions are.  Unclear why there's reundancy and
        the follower has to answer back with both a status message and the
        major and minor versions.

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  Main Protocol version as implemented         |
        +-------+--------+-----------------------------------------------+
        |   4   |  byte  |  Release within version as implemented        |                                 |
        +-------+--------+-----------------------------------------------+
        | 5..7  |  bytes |  Don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        crc_byte = ord(CCP_message[1]) # is this python 3 compatible?
        crc_tuple = COMMAND_RET_CODES.get(crc_byte)
        counter = ord(CCP_message[2])

        main_protocol = _parse_byte(CCP_message[3])
        minor_protocol = _parse_byte(CCP_message[4])

        return {'CRC': crc_tuple[0], \
                'CTR': counter, \
                'main_protocol': main_protocol, \
                'minor_protocol': minor_protocol,
               }

    def _parse_get_seed_CRM(self, CCP_message):
        '''
        Possible return codes:
        - 0x00:  acknowledge (no error)
        - ???  Others not listed

        If protection status = false, UNLOCK is not needed.

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  Protection status (TRUE or FALSE)            |
        +-------+--------+-----------------------------------------------+
        |  4..7 |  bytes |  'seed' data                                  |
        +-------+--------+-----------------------------------------------+
        '''

        crc_byte = ord(CCP_message[1]) # is this python 3 compatible?
        crc_tuple = COMMAND_RET_CODES.get(crc_byte)
        counter = ord(CCP_message[2])

        protection_status_bool = ord(CCP_message[3])
        if protection_status_bool == 1:
            protection_status = 'true'
        else:
            protection_status = 'false'

        seed_data = _parse_4_byte_value(CCP_message[4:])

        return {'CRC': crc_tuple[0], \
                'CTR': counter, \
                'protection_status': protection_status, \
                'seed_data': seed_data,
               }

    def _parse_build_chksum_CRM(self, CCP_message):
        '''
        Possible return codes:
        - 0x00:  acknowledge (no error)
        - ???  Others not listed

        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  size of checksum data                        |
        +-------+--------+-----------------------------------------------+
        |  4..7 |  bytes |  checksum data (implementation specific)      |
        +-------+--------+-----------------------------------------------+
        '''
        crc_byte = ord(CCP_message[1]) # is this python 3 compatible?
        crc_tuple = COMMAND_RET_CODES.get(crc_byte)
        counter = ord(CCP_message[2])

        chksum_size = ord(CCP_message[3])

        if chksum_size == 2:
            chksum_data = hex(struct.unpack('>H', CCP_message[4:6])[0])
        elif chksum_size == 4:
            chksum_data = _parse_4_byte_value(CCP_message[4:])
        else:
            raise Exception("Invalid checksum size")

        return {'CRC': crc_tuple[0], \
                'CTR': counter, \
                'chksum_size': chksum_size, \
                'chksum_data': chksum_data \
                }

    def _parse_unlock_CRM(self, CCP_message):
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

        crc_byte = ord(CCP_message[1]) # is this python 3 compatible?
        crc_tuple = COMMAND_RET_CODES.get(crc_byte)
        counter = ord(CCP_message[2])

        resource_mask = _parse_byte(CCP_message[3])

        return {'CRC': crc_tuple[0], \
                'CTR': counter, \
                'resource_mask': resource_mask, \
                }

    def _parse_set_s_status_CRM(self, CCP_message):
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
        return self._CRM_parser_status_ctr_only(CCP_message)

    def _parse_get_s_status_CRM(self, CCP_message):
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
        crc_byte = ord(CCP_message[1]) # is this python 3 compatible?
        crc_tuple = COMMAND_RET_CODES.get(crc_byte)
        counter = _parse_byte(CCP_message[2])

        session_status = _parse_byte(CCP_message[3])
        addl_info_bool = ord(CCP_message[4])

        if addl_info_bool == 0:
            return {'CRC': crc_tuple[0], 'CTR': counter, \
                    'session_status': session_status, 'addl_info_bool': 'false', }

        return {'CRC': crc_tuple[0], 'CTR': counter, \
                'session_status': session_status, 'addl_info_bool': 'true', \
                'addl_info': 'not implemented yet' }

    def _CRM_parser_status_ctr_only(self, CCP_message):
        crc_byte = ord(CCP_message[1]) # is this python 3 compatible?
        crc_tuple = COMMAND_RET_CODES.get(crc_byte)
        counter = ord(CCP_message[2])

        return {'CRC': crc_tuple[0], 'CTR': counter}

    def _parse_EventMessage(self, CCP_message):
        # todo
        return

    '''
    +---------------------------------------------------------------------+
    |                                                                     |
    |                           CCP Sequences                             |
    |                                                                     |
    +---------------------------------------------------------------------+
    '''
    def Send_Connect_Command(self, stat_addr, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._connect_CRO(counter=counter, stat_addr=stat_addr)
        return self._do_Function(msg=msg, command_type=CCP_CONNECT, currIdx=currIdx)

    def Send_Disconnect_Command(self, disconnect_type, stat_addr, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._disconnect_CRO(counter=counter, disconnect_type=disconnect_type, stat_addr=stat_addr)
        return self._do_Function(msg=msg, command_type=CCP_DISCONNECT, currIdx=currIdx)

    def Send_SetMTA_Command(self, mta_number, address_extension, address, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._set_MTA_CRO(counter=counter, mta_number=mta_number, address_extension=address_extension, address=address)
        return self._do_Function(msg=msg, command_type=CCP_SET_MTA, currIdx=currIdx)

    def Send_ExchangeId_Command(self, leader_id_information=None, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._exchangeID_CRO(counter=counter, leader_id_information=leader_id_information)
        return self._do_Function(msg=msg, command_type=CCP_EXCHANGE_ID, currIdx=currIdx)

    def Send_Download_Command(self, data_to_download, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._download_CRO(counter=counter, data_to_download=data_to_download)
        return self._do_Function(msg=msg, command_type=CCP_DNLOAD, currIdx=currIdx)

    def Send_Upload_Command(self, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._upload_CRO(counter=counter)
        return self._do_Function(msg=msg, command_type=CCP_UPLOAD, currIdx=currIdx)

    def Send_Program_Command(self, data_to_program, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._program_CRO(counter=counter, data_to_program=data_to_program)
        return self._do_Function(msg=msg, command_type=CCP_PROGRAM, currIdx=currIdx)

    def Send_Move_Command(self, data_block_size, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._move_CRO(counter=counter, data_block_size=data_block_size)
        return self._do_Function(msg=msg, command_type=CCP_MOVE, currIdx=currIdx)

    def Send_ClearMemory_Command(self, data_block_size, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._clear_memory_CRO(counter=counter, data_block_size=data_block_size)
        return self._do_Function(msg=msg, command_type=CCP_CLEAR_MEMORY, currIdx=currIdx)

    def Send_Test_Command(self, stat_addr, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._test_CRO(counter=counter, stat_addr=stat_addr)
        return self._do_Function(msg=msg, command_type=CCP_TEST, currIdx=currIdx)

    def Send_GetCCPVersion_Command(self, major_version, minor_version, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._get_ccp_version_CRO(counter=counter, major_version=major_version, minor_version=minor_version)
        return self._do_Function(msg=msg, command_type=CCP_GET_CCP_VERSION, currIdx=currIdx)

    def Send_GetSeed_Command(self, requested_resource, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._get_seed_CRO(counter=counter, requested_resource=requested_resource)
        return self._do_Function(msg=msg, command_type=CCP_GET_SEED, currIdx=currIdx)

    def Send_Unlock_Command(self, key, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._unlock_CRO(counter=counter, key=key)
        return self._do_Function(msg=msg, command_type=CCP_UNLOCK, currIdx=currIdx)

    def Send_BuildChksum_Command(self, data_block_size, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._build_chksum_CRO(counter=counter, data_block_size=data_block_size)
        return self._do_Function(msg=msg, command_type=CCP_BUILD_CHKSUM, currIdx=currIdx)

    def Send_UploadShort_Command(self, address, address_extension, data_block_size=4, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._short_upload_CRO(counter=counter, address=address, address_extension=address_extension, data_block_size=data_block_size)
        return self._do_Function(msg=msg, command_type=CCP_SHORT_UP, currIdx=currIdx)

    def Send_GetSStatus_Command(self, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._get_s_status_CRO(counter=counter)
        return self._do_Function(msg=msg, command_type=CCP_GET_S_STATUS, currIdx=currIdx)

    def Send_SetSStatus_Command(self, session_status_mask, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._set_s_status_CRO(counter=counter, session_status_mask=session_status_mask)
        return self._do_Function(msg=msg, command_type=CCP_SET_S_STATUS, currIdx=currIdx)
