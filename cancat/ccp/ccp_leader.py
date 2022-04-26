#!/usr/bin/env python
import time
import cancat
import struct
from . import utils
from cancat.vstruct.primitives import v_enum

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

COUNTER_VAL = 0x20

DTO_TYPE = v_enum()
DTO_TYPE.CRO_TYPE = 0xFF
DTO_TYPE.EVENT_TYPE = 0xFE
DTO_TYPE.DAQ_TYPE = 0xFD


class CCPLeader(object):
    def __init__(self, c, tx_arbid=None, rx_arbid=None, verbose=True, extflag=0):
        self.c = c
        self.verbose = verbose
        self.extflag = extflag

        self.tx_arbid = tx_arbid
        self.rx_arbid = rx_arbid

    def _do_Function(self, msg, command_type, currIdx, timeout=1):
        self.c._send(cancat.CMD_CAN_SEND, msg)

        complete = False
        starttime = lasttime = time.time()

        while not complete and (not timeout or (lasttime-starttime < timeout)):
            time.sleep(0.01)
            msgs = [msg for msg in self.c.genCanMsgs(start=currIdx, arbids=[self.rx_arbid])]

            if len(msgs):
                try:
                    for msg in msgs:
                        msg_type = self._parse_DTO_type(msg)

                        if msg_type == DTO_TYPE.CRO_TYPE:
                            return self._parse_Command_Return_Message(msg, command_type)
                        elif msg_type == DTO_TYPE.EVENT_TYPE:
                            return self._parse_EventMessage(msg)
                        elif msg_type == DTO_TYPE.DAQ_TYPE:
                            return self._parse_DAQMessage(msg)
                        else:
                            raise Exception("Error sorting message type")

                except Exception as e:
                    raise Exception("Something went wrong: ", e)

            lasttime = time.time()

        return None

    '''
    +---------------------------------------------------------------------+
    |                                                                     |
    |               Command Receive Object helper functions               |
    |                                                                     |
    +---------------------------------------------------------------------+
    | Use these to generate messages from the leader to send to followers |
    +---------------------------------------------------------------------+
    '''

    def _constructCRO(self, cmd, ctr, cmd_data):
        msg = utils._gen_byte(cmd) + utils._gen_byte(ctr) + cmd_data

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
        station_address = utils._gen_2_byte_val(stat_addr)

        data = station_address + utils._gen_byte(utils.DONT_CARE_VAL)*4

        msg = self._constructCRO(utils.CCP_CONNECT, counter, data)

        return msg

    def _exchangeID_CRO(self, counter, leader_id_information=None):
        '''
        EXCHANGE_ID CRO

        Note: bytes 2..7 are left as "don't cares" here, but you may have to
        change them based on your device's expected implementation.

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
                dont_care = utils._gen_byte(utils.DONT_CARE_VAL)*padding
                data = leader_id_information + dont_care
        else:
            data = utils._gen_byte(utils.DONT_CARE_VAL)*6

        msg = self._constructCRO(utils.CCP_EXCHANGE_ID, counter, data)

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
            raise Exception("Invalid mta_number.  Must be either 1 for MTA1 "
                            "(MOVE) or 1 for MTA0 (all other read/write commands)")

        data = utils._gen_byte(mta_number) + utils._gen_byte(address_extension) + utils._gen_4_byte_val(address)

        msg = self._constructCRO(utils.CCP_SET_MTA, counter, data)

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
            dont_care = utils._gen_byte(utils.DONT_CARE_VAL)*padding

        data = utils._gen_byte(data_block_size) + utils._gen_4_byte_val(data_to_download) + dont_care

        msg = self._constructCRO(utils.CCP_DNLOAD, counter, data)

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

        data = utils._gen_byte(data_block_size) + utils._gen_byte(utils.DONT_CARE_VAL)*5

        msg = self._constructCRO(utils.CCP_UPLOAD, counter, data)

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

        station_address = utils._gen_2_byte_val(stat_addr)

        dont_care = utils._gen_byte(utils.DONT_CARE_VAL)

        data = utils._gen_byte(disconnect_type) + dont_care + \
            station_address + dont_care*2

        msg = self._constructCRO(utils.CCP_DISCONNECT, counter, data)

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
            dont_care = utils._gen_byte(utils.DONT_CARE_VAL)*padding

        data = utils._gen_byte(data_block_size) + utils._gen_4_byte_val(data_to_program) + dont_care

        msg = self._constructCRO(utils.CCP_PROGRAM, counter, data)

        return msg

    def _move_CRO(self, counter, data_block_size):
        '''
        MOVE CRO

        ************************************************************************************
        ** You must set MTA0 and MTA1 with the SET_MTA command before using this function **
        ************************************************************************************

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

        dont_care = utils._gen_byte(utils.DONT_CARE_VAL)*2

        data = utils._gen_4_byte_val(data_block_size) + dont_care

        msg = self._constructCRO(utils.CCP_MOVE, counter, data)

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

        dont_care = utils._gen_byte(utils.DONT_CARE_VAL)*2

        data = utils._gen_4_byte_val(data_block_size) + dont_care

        msg = self._constructCRO(utils.CCP_CLEAR_MEMORY, counter, data)

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

        station_address = utils._gen_2_byte_val(stat_addr)

        dont_care = utils._gen_byte(utils.DONT_CARE_VAL)*4

        data = station_address + dont_care

        msg = self._constructCRO(utils.CCP_TEST, counter, data)

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

        maj_version = utils._gen_byte(major_version)

        min_version = utils._gen_byte(minor_version)

        dont_care = utils._gen_byte(utils.DONT_CARE_VAL)*4

        data = maj_version + min_version + dont_care

        msg = self._constructCRO(utils.CCP_GET_CCP_VERSION, counter, data)

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

        dont_care = utils._gen_byte(utils.DONT_CARE_VAL)*5

        resource = utils._gen_byte(requested_resource)

        data = resource + dont_care

        msg = self._constructCRO(utils.CCP_GET_SEED, counter, data)

        return msg

    def _unlock_CRO(self, counter, key):
        '''
        UNLOCK CRO

        Unlocks the follower device's security protection (if applicable) using
        a "key" computed from "seed" (do a GET_SEED CRO first).

        Spec is vague as to whether the returned value is the key (generated by the follower)
        or if the returned value has to be made into the key by the leader.
        May be implementation-specific.

        +-------+--------+-----------------------------------------------+
        |  2..  |  bytes |  Key computed with GET_SEED seed              |
        +-------+--------+-----------------------------------------------+
        '''

        # if key is less than 6 bytes long, pad with "don't care"s
        if len(key) > 6:
            raise Exception("Key cannot be longer than 6 bytes")

        if len(key) <= 6:
            padding = 6 - len(key)
            dont_care = utils._gen_byte(utils.DONT_CARE_VAL)*padding

        data = utils._bytesHelper(key) + dont_care

        msg = self._constructCRO(utils.CCP_UNLOCK, counter, data)

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

        dont_care = utils._gen_byte(utils.DONT_CARE_VAL)*2

        data = utils._gen_4_byte_val(data_block_size) + dont_care

        msg = self._constructCRO(utils.CCP_BUILD_CHKSUM, counter, data)

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

        data = utils._gen_byte(data_block_size) + utils._gen_byte(address_extension) + utils._gen_4_byte_val(address)

        msg = self._constructCRO(utils.CCP_SHORT_UP, counter, data)

        return msg

    def _get_s_status_CRO(self, counter):
        '''
        GET_S_STATUS CRO

        Data to be sent after CMD and CTR values:
        +-------+--------+-----------------------------------------------+
        |  2..7 |  bytes |  don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''
        data = utils._gen_byte(utils.DONT_CARE_VAL)*6

        msg = self._constructCRO(utils.CCP_GET_S_STATUS, counter, data)

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

        data = utils._gen_byte(session_status_mask) + utils._gen_byte(utils.DONT_CARE_VAL)*5

        msg = self._constructCRO(utils.CCP_GET_S_STATUS, counter, data)

        return msg

    def _select_cal_page_CRO(self, counter):
        '''
        SELECT_CAL_PAGE CRO

        data to be sent after CMD and CTR values:
        +-------+--------+-----------------------------------------------+
        |  2..7 |  bytes |  don't care                                             |
        +-------+--------+-----------------------------------------------+
        '''

        data = utils._gen_byte(utils.DONT_CARE_VAL)*6

        msg = self._constructCRO(utils.CCP_SELECT_CAL_PAGE, counter, data)

        return msg

    def _get_active_cal_page_CRO(self, counter):
        '''
        GET_ACTIVE_CAL_PAGE CRO

        data to be sent after CMD and CTR values:
        +-------+--------+-----------------------------------------------+
        |  2..7 |  bytes |  don't care                                             |
        +-------+--------+-----------------------------------------------+
        '''

        data = utils._gen_byte(utils.DONT_CARE_VAL)*6

        msg = self._constructCRO(utils.CCP_GET_ACTIVE_CAL_PAGE, counter, data)

        return msg

    def _diag_service_CRO(self, counter, diagnostic_service_num, parameters=None):
        '''
        DIAG_SERVICE CRO

        Diagnostic service # is supposed to be two bytes but example shows it as one byte.

        Valid values for diag service #s and corresponding parameters not defined
        by the spec, may be implementation-specific.

        data to be sent after CMD and CTR values:
        +-------+--------+-----------------------------------------------+
        |  2,3  |  word  |   Diagnostic service number                   |
        +-------+--------+-----------------------------------------------+
        |  4..7 |  bytes |   Parameters, if applicable                   |
        +-------+--------+-----------------------------------------------+
        '''

        data = utils._gen_byte(diagnostic_service_num) + utils._gen_byte(utils.DONT_CARE_VAL)*5

        msg = self._constructCRO(utils.CCP_DIAG_SERVICE, counter, data)

        return msg

    def _action_service_CRO(self, counter, action_service_num, parameters):
        '''
        ACTION_SERVICE CRO

        Action service # is supposed to be two bytes but example shows it as one byte.

        Valid values for diag service #s and corresponding parameters not defined
        by the spec, may be implementation-specific.

        data to be sent after CMD and CTR values:
        +-------+--------+-----------------------------------------------+
        |  2,3  |  word  |   Action service number                       |
        +-------+--------+-----------------------------------------------+
        |  4..7 |  bytes |   Parameters, if applicable                   |
        +-------+--------+-----------------------------------------------+
        '''

        data = utils._gen_byte(action_service_num) + utils._gen_byte(parameters) + utils._gen_byte(utils.DONT_CARE_VAL)*4

        msg = self._constructCRO(utils.CCP_ACTION_SERVICE, counter, data)

        return msg

    def _get_daq_size_CRO(self, counter, daq_list_number, can_identifier):
        '''
        GET_DAQ_SIZE CRO

        data to be sent after CMD and CTR values:
        +-------+--------+-----------------------------------------------+
        |   2   |  byte  |  DAQ list number (0,1,...)                    |
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  don't care                                   |
        +-------+--------+-----------------------------------------------+
        |  4..7 |  ulong |  CAN Identifier of DTO dedicated              |
        |       |        |  to list number                               |
        +-------+--------+-----------------------------------------------+
        '''

        data = utils._gen_byte(daq_list_number) + utils._gen_byte(utils.DONT_CARE_VAL) + \
            utils._gen_4_byte_val(can_identifier)

        msg = self._constructCRO(utils.CCP_GET_DAQ_SIZE, counter, data)

        return msg

    def _set_daq_ptr_CRO(self, counter, daq_list_number, odt_number, odt_element_number):
        '''
        SET_DAQ_PTR CRO

        data to be sent after CMD and CTR values:
        +-------+--------+-----------------------------------------------+
        |   2   |        |  DAQ list number (0,1,...)                    |
        +-------+--------+-----------------------------------------------+
        |   3   |        |  Object Descriptor Table ODT number (0,1,...) |
        +-------+--------+-----------------------------------------------+
        |   4   |        |  Element number within ODT (0,1,...)          |
        +-------+--------+-----------------------------------------------+
        |  5..7 |        |  don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        data = utils._gen_byte(daq_list_number) + utils._gen_byte(odt_number) + \
            utils._gen_byte(odt_element_number) + utils._gen_byte(utils.DONT_CARE_VAL)*3 \

        msg = self._constructCRO(utils.CCP_SET_DAQ_PTR, counter, data)

        return msg

    def _write_daq_CRO(self, counter, daq_element_size, daq_element_addr_extension, daq_element_addr):
        '''
        WRITE_DAQ CRO

        data to be sent after CMD and CTR values:
        +-------+--------+-----------------------------------------------+
        |   2   |  byte  |  Size of DAQ element in bytes { 1, 2, 4 }     |
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  Address extension of DAQ element             |
        +-------+--------+-----------------------------------------------+
        |  4..7 |  ulong |  Address of DAQ element                       |
        +-------+--------+-----------------------------------------------+
        '''

        data = utils._gen_byte(daq_element_size) + utils._gen_byte(daq_element_addr_extension) + \
            utils._gen_4_byte_val(daq_element_addr)

        msg = self._constructCRO(utils.CCP_WRITE_DAQ, counter, data)

        return msg

    def _start_stop_CRO(self, counter, mode, daq_list_number, last_odt_num, event_chan_num, transmission_rate_prescaler):
        '''
        START_STOP CRO

        data to be sent after CMD and CTR values:
        +-------+--------+-----------------------------------------------+
        |   2   |  byte  |  Mode: start/stop/prepare data tranmission    |
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  DAQ list number                              |
        +-------+--------+-----------------------------------------------+
        |   4   |  byte  |  Last ODT number                              |
        +-------+--------+-----------------------------------------------+
        |   5   |  byte  |  Event Channel No.                            |
        +-------+--------+-----------------------------------------------+
        |  6,7  |  word  |  Transmission rate prescaler                  |
        +-------+--------+-----------------------------------------------+
        '''

        # this one is motorola instead of intel format, according to the spec
        trans_rate_prescaler = struct.pack('>H', transmission_rate_prescaler)

        data = utils._gen_byte(mode) + utils._gen_byte(daq_list_number) + \
            utils._gen_byte(last_odt_num) + utils._gen_byte(event_chan_num) + \
            trans_rate_prescaler

        msg = self._constructCRO(utils.CCP_START_STOP, counter, data)

        return msg

    def _start_stop_all_CRO(self, counter, start_or_stop):
        '''
        START_STOP_ALL CRO

        data to be sent after CMD and CTR values:
        +-------+--------+-----------------------------------------------+
        |   2   |  byte  |  0x00 stops, 0x01 starts data transmission    |
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        data = utils._gen_byte(start_or_stop) + utils._gen_byte(utils.DONT_CARE_VAL)*5

        msg = self._constructCRO(utils.CCP_START_STOP_ALL, counter, data)

        return msg

    '''
    +---------------------------------------------------------------------+
    |                                                                     |
    |                 Data Transmission Object functions                  |
    |                                                                     |
    +---------------------------------------------------------------------+
    |   Use these to parse messages sent by a follower, back to a leader  |
    +---------------------------------------------------------------------+
    '''

    def _parse_DTO_type(self, CCP_message):
        '''
        Data Transmission Object (DTO): message sent from follower to leader

        Can be one of three types:
        * Command Return Message: follower sending message back in response to CRO from leader
        * Event Message: reporting internal status change in order to invoke error recovery
        * Data Acquisition Message: Packet ID must correspond to ODT (Object Descriptor Table)
        '''

        if len(CCP_message) != 8:
            raise Exception("CCP message should have length 8")

        if CCP_message[0] == DTO_TYPE.CRO_TYPE:
            return DTO_TYPE.CRO_TYPE
        elif CCP_message[0] == DTO_TYPE.EVENT_TYPE:
            return DTO_TYPE.EVENT_TYPE
        elif (0x00 < CCP_message[0]) and (CCP_message[0] < 0xFD):
            return DTO_TYPE.DAQ_TYPE
        else:
            raise Exception("CCP message has invalid starting byte")

    def _parse_Command_Return_Message(self, CCP_message, CCP_CRO_Type):  # noqa: C901
        '''
        Command Return Messages return data based on the command type originally
        sent to the follower device.

        Unclear if counter is used as session ID or command ID (implementation-specific?)

        All DTOs of type CRM* should start off with this format:
        +-------+--------+-----------------------------------------------+
        |   0   |  byte  |  0xFF                                         |
        +-------+--------+-----------------------------------------------+
        |   1   |  byte  |  Command Return Code                          |
        +-------+--------+-----------------------------------------------+
        |   2   |  byte  |  Command Counter = CTR                        |
        +-------+--------+-----------------------------------------------+

        2nd byte is CTR and should match original message, but we are not checking for this

        Bytes 3-7 vary by response type.

        *There are other types, like EventMessage, but these are not supported yet.
        '''

        if CCP_CRO_Type == utils.CCP_CONNECT:
            parsed_msg = self._parse_connect_CRM(CCP_message)
        elif CCP_CRO_Type == utils.CCP_DISCONNECT:
            parsed_msg = self._parse_disconnect_CRM(CCP_message)
        elif CCP_CRO_Type == utils.CCP_SET_MTA:
            parsed_msg = self._parse_setMTA_CRM(CCP_message)
        elif CCP_CRO_Type == utils.CCP_DNLOAD:
            parsed_msg = self._parse_dnload_CRM(CCP_message)
        elif CCP_CRO_Type == utils.CCP_UPLOAD:
            parsed_msg = self._parse_upload_CRM(CCP_message)
        elif CCP_CRO_Type == utils.CCP_SHORT_UP:
            parsed_msg = self._parse_upload_CRM(CCP_message)
        elif CCP_CRO_Type == utils.CCP_CLEAR_MEMORY:
            parsed_msg = self._parse_clear_memory_CRM(CCP_message)
        elif CCP_CRO_Type == utils.CCP_MOVE:
            parsed_msg = self._parse_move_CRM(CCP_message)
        elif CCP_CRO_Type == utils.CCP_TEST:
            parsed_msg = self._parse_test_CRM(CCP_message)
        elif CCP_CRO_Type == utils.CCP_PROGRAM:
            parsed_msg = self._parse_program_CRM(CCP_message)
        elif CCP_CRO_Type == utils.CCP_EXCHANGE_ID:
            parsed_msg = self._parse_exchangeID_CRM(CCP_message)
        elif CCP_CRO_Type == utils.CCP_GET_CCP_VERSION:
            parsed_msg = self._parse_ccp_version_CRM(CCP_message)
        elif CCP_CRO_Type == utils.CCP_GET_SEED:
            parsed_msg = self._parse_get_seed_CRM(CCP_message)
        elif CCP_CRO_Type == utils.CCP_BUILD_CHKSUM:
            parsed_msg = self._parse_build_chksum_CRM(CCP_message)
        elif CCP_CRO_Type == utils.CCP_UNLOCK:
            parsed_msg = self._parse_unlock_CRM(CCP_message)
        elif CCP_CRO_Type == utils.CCP_SET_S_STATUS:
            parsed_msg = self._parse_set_s_status_CRM(CCP_message)
        elif CCP_CRO_Type == utils.CCP_GET_S_STATUS:
            parsed_msg = self._parse_get_s_status_CRM(CCP_message)
        else:
            raise Exception("Cannot parse message type ", CCP_CRO_Type)

        return parsed_msg

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

        crc_byte = utils._parse_byte(CCP_message[1])
        crc_tuple = utils.COMMAND_RET_CODES.get(crc_byte)
        counter = utils._parse_byte(CCP_message[2])

        if crc_byte == 0x00:
            mta0_address_ext = utils._parse_byte(CCP_message[3])
            mta0_address = utils._parse_4_byte_value(CCP_message[4:])
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

        crc_byte = utils._parse_byte(CCP_message[1])
        crc_tuple = utils.COMMAND_RET_CODES.get(crc_byte)
        counter = utils._parse_byte(CCP_message[2])

        if crc_byte == 0x00:
            mta0_address_ext = utils._parse_byte(CCP_message[3])
            mta0_address = utils._parse_4_byte_value(CCP_message[4:])
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

        crc_byte = utils._parse_byte(CCP_message[1])
        crc_tuple = utils.COMMAND_RET_CODES.get(crc_byte)
        counter = utils._parse_byte(CCP_message[2])

        if crc_byte == 0x00:
            returned_data = utils._parse_4_byte_value(CCP_message[3:7])
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

        crc_byte = utils._parse_byte(CCP_message[1])
        crc_tuple = utils.COMMAND_RET_CODES.get(crc_byte)
        counter = utils._parse_byte(CCP_message[2])

        follower_deviceID_length = utils._parse_byte(CCP_message[3])
        follower_deviceID_data_type_qual = utils._parse_byte(CCP_message[4])
        resource_availability_mask = utils._parse_byte(CCP_message[5])
        resource_protection_mask = utils._parse_byte(CCP_message[6])

        return {
            'CRC': crc_tuple[0],
            'CTR': counter,
            'follower_deviceID_length': follower_deviceID_length,
            'follower_deviceID_data_type_qual': follower_deviceID_data_type_qual,
            'resource_availability_mask': resource_availability_mask,
            'resource_protection_mask': resource_protection_mask,
        }

    def _parse_ccp_version_CRM(self, CCP_message):
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

        crc_byte = utils._parse_byte(CCP_message[1])
        crc_tuple = utils.COMMAND_RET_CODES.get(crc_byte)
        counter = utils._parse_byte(CCP_message[2])

        main_protocol = utils._parse_byte(CCP_message[3])
        minor_protocol = utils._parse_byte(CCP_message[4])

        return {
            'CRC': crc_tuple[0],
            'CTR': counter,
            'main_protocol': main_protocol,
            'minor_protocol': minor_protocol,
        }

    def _parse_get_seed_CRM(self, CCP_message):
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

        crc_byte = utils._parse_byte(CCP_message[1])
        crc_tuple = utils.COMMAND_RET_CODES.get(crc_byte)
        counter = utils._parse_byte(CCP_message[2])

        protection_status_bool = utils._parse_byte(CCP_message[3])
        if protection_status_bool == 1:
            protection_status = True
        else:
            protection_status = False

        seed_data = utils._parse_4_byte_value(CCP_message[4:])

        return {
            'CRC': crc_tuple[0],
            'CTR': counter,
            'protection_status': protection_status,
            'seed_data': seed_data,
        }

    def _parse_build_chksum_CRM(self, CCP_message):
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
        crc_byte = utils._parse_byte(CCP_message[1])
        crc_tuple = utils.COMMAND_RET_CODES.get(crc_byte)
        counter = utils._parse_byte(CCP_message[2])

        chksum_size = utils._parse_byte(CCP_message[3])

        if chksum_size == 2:
            chksum_data = hex(struct.unpack('>H', CCP_message[4:6])[0])
        elif chksum_size == 4:
            chksum_data = utils._parse_4_byte_value(CCP_message[4:])
        else:
            raise Exception("Invalid checksum size")

        return {
            'CRC': crc_tuple[0],
            'CTR': counter,
            'chksum_size': chksum_size,
            'chksum_data': chksum_data,
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

        crc_byte = utils._parse_byte(CCP_message[1])
        crc_tuple = utils.COMMAND_RET_CODES.get(crc_byte)
        counter = utils._parse_byte(CCP_message[2])

        resource_mask = utils._parse_byte(CCP_message[3])

        return {
            'CRC': crc_tuple[0],
            'CTR': counter,
            'resource_mask': resource_mask,
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
        crc_byte = utils._parse_byte(CCP_message[1])
        crc_tuple = utils.COMMAND_RET_CODES.get(crc_byte)
        counter = utils._parse_byte(CCP_message[2])

        session_status = utils._parse_byte(CCP_message[3])
        addl_info_bool = utils._parse_byte(CCP_message[4])

        if addl_info_bool == 0:
            return {
                'CRC': crc_tuple[0],
                'CTR': counter,
                'session_status': session_status,
                'addl_info_bool': False,
            }

        return {
            'CRC': crc_tuple[0],
            'CTR': counter,
            'session_status': session_status,
            'addl_info_bool': True,
            'addl_info': 'not implemented yet'
        }

    def _parse_select_cal_page_CRM(self, CCP_message):
        '''
        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  Don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        return self._CRM_parser_status_ctr_only(CCP_message)

    def _parse_get_active_cal_page_CRM(self, CCP_message):
        '''
        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  Address extension                            |
        +-------+--------+-----------------------------------------------+
        |  4..7 |  ulong |  Address                                      |
        +-------+--------+-----------------------------------------------+
        '''

        crc_byte = utils._parse_byte(CCP_message[1])
        crc_tuple = utils.COMMAND_RET_CODES.get(crc_byte)
        counter = utils._parse_byte(CCP_message[2])

        address_ext = utils._parse_byte(CCP_message[3])
        address = utils._parse_4_byte_value(CCP_message[4:])

        msg = {'CRC': crc_tuple[0], 'CTR': counter, 'address_ext': address_ext, 'address': address}

        return msg

    def _parse_action_service_CRM(self, CCP_message):
        '''
        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  length of return information in bytes        |
        +-------+--------+-----------------------------------------------+
        |   4   |  byte  |  data type qualifier of return information    |
        |       |        |  (to be defined)                              |
        +-------+--------+-----------------------------------------------+
        |  5..7 |  bytes |  don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        crc_byte = utils._parse_byte(CCP_message[1])
        crc_tuple = utils.COMMAND_RET_CODES.get(crc_byte)
        counter = utils._parse_byte(CCP_message[2])

        length_of_return_info = utils._parse_byte(CCP_message[3])
        data_type_qual = utils._parse_byte(CCP_message[4])

        msg = {
            'CRC': crc_tuple[0],
            'CTR': counter,
            'length_of_return_info': length_of_return_info,
            'data_type_qual': data_type_qual,
        }

        return msg

    def _parse_diag_service_CRM(self, CCP_message):
        '''
        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  |  length of return information in bytes        |
        +-------+--------+-----------------------------------------------+
        |   4   |  byte  |  data type qualifier of return information    |
        |       |        |  (to be defined)                              |
        +-------+--------+-----------------------------------------------+
        |  5..7 |  bytes |  don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        crc_byte = utils._parse_byte(CCP_message[1])
        crc_tuple = utils.COMMAND_RET_CODES.get(crc_byte)
        counter = utils._parse_byte(CCP_message[2])

        length_of_return_info = utils._parse_byte(CCP_message[3])
        data_type_qual = utils._parse_byte(CCP_message[4])

        msg = {
            'CRC': crc_tuple[0],
            'CTR': counter,
            'length_of_return_info': length_of_return_info,
            'data_type_qual': data_type_qual
        }

        return msg

    def _parse_get_daq_size_CRM(self, CCP_message):
        '''
        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |   3   |  byte  | DAQ list size (= number of ODTs in this list) |
        +-------+--------+-----------------------------------------------+
        |   4   |  byte  | First PID of DAQ list                         |
        +-------+--------+-----------------------------------------------+
        |  5..7 |  bytes | don't care                                    |
        +-------+--------+-----------------------------------------------+
        '''

        crc_byte = utils._parse_byte(CCP_message[1])
        crc_tuple = utils.COMMAND_RET_CODES.get(crc_byte)
        counter = utils._parse_byte(CCP_message[2])

        daq_list_size = utils._parse_byte(CCP_message[3])
        first_pid = utils._parse_byte(CCP_message[4])

        msg = {
            'CRC': crc_tuple[0],
            'CTR': counter,
            'daq_list_size': daq_list_size,
            'first_pid': first_pid,
        }

        return msg

    def _parse_set_daq_ptr_CRM(self, CCP_message):
        '''
        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  Don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        return self._CRM_parser_status_ctr_only(CCP_message)

    def _parse_write_daq_CRM(self, CCP_message):
        '''
        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  Don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        return self._CRM_parser_status_ctr_only(CCP_message)

    def _parse_start_stop_CRM(self, CCP_message):
        '''
        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  Don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        return self._CRM_parser_status_ctr_only(CCP_message)

    def _parse_start_stop_all_CRM(self, CCP_message):
        '''
        Bytes after 0xFF, return code and counter:
        +-------+--------+-----------------------------------------------+
        |  3..7 |  bytes |  Don't care                                   |
        +-------+--------+-----------------------------------------------+
        '''

        return self._CRM_parser_status_ctr_only(CCP_message)

    def _CRM_parser_status_ctr_only(self, CCP_message):
        crc_byte = utils._parse_byte(CCP_message[1])
        crc_tuple = utils.COMMAND_RET_CODES.get(crc_byte)
        counter = utils._parse_byte(CCP_message[2])

        return {'CRC': crc_tuple[0], 'CTR': counter}

    def _parse_EventMessage(self, CCP_message):
        print("Not Implemented")
        return

    def _parse_DAQMessage(self, CCP_message):
        print("Not Implemented")
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
        return self._do_Function(msg=msg, command_type=utils.CCP_CONNECT, currIdx=currIdx)

    def Send_Disconnect_Command(self, disconnect_type, stat_addr, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._disconnect_CRO(counter=counter, disconnect_type=disconnect_type, stat_addr=stat_addr)
        return self._do_Function(msg=msg, command_type=utils.CCP_DISCONNECT, currIdx=currIdx)

    def Send_SetMTA_Command(self, mta_number, address_extension, address, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._set_MTA_CRO(counter=counter, mta_number=mta_number, address_extension=address_extension, address=address)
        return self._do_Function(msg=msg, command_type=utils.CCP_SET_MTA, currIdx=currIdx)

    def Send_ExchangeId_Command(self, leader_id_information=None, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._exchangeID_CRO(counter=counter, leader_id_information=leader_id_information)
        return self._do_Function(msg=msg, command_type=utils.CCP_EXCHANGE_ID, currIdx=currIdx)

    def Send_Download_Command(self, data_to_download, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._download_CRO(counter=counter, data_to_download=data_to_download)
        return self._do_Function(msg=msg, command_type=utils.CCP_DNLOAD, currIdx=currIdx)

    def Send_Upload_Command(self, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._upload_CRO(counter=counter)
        return self._do_Function(msg=msg, command_type=utils.CCP_UPLOAD, currIdx=currIdx)

    def Send_Program_Command(self, data_to_program, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._program_CRO(counter=counter, data_to_program=data_to_program)
        return self._do_Function(msg=msg, command_type=utils.CCP_PROGRAM, currIdx=currIdx)

    def Send_Move_Command(self, data_block_size, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._move_CRO(counter=counter, data_block_size=data_block_size)
        return self._do_Function(msg=msg, command_type=utils.CCP_MOVE, currIdx=currIdx)

    def Send_ClearMemory_Command(self, data_block_size, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._clear_memory_CRO(counter=counter, data_block_size=data_block_size)
        return self._do_Function(msg=msg, command_type=utils.CCP_CLEAR_MEMORY, currIdx=currIdx)

    def Send_Test_Command(self, stat_addr, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._test_CRO(counter=counter, stat_addr=stat_addr)
        return self._do_Function(msg=msg, command_type=utils.CCP_TEST, currIdx=currIdx)

    def Send_GetCCPVersion_Command(self, major_version, minor_version, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._get_ccp_version_CRO(counter=counter, major_version=major_version, minor_version=minor_version)
        return self._do_Function(msg=msg, command_type=utils.CCP_GET_CCP_VERSION, currIdx=currIdx)

    def Send_GetSeed_Command(self, requested_resource, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._get_seed_CRO(counter=counter, requested_resource=requested_resource)
        return self._do_Function(msg=msg, command_type=utils.CCP_GET_SEED, currIdx=currIdx)

    def Send_Unlock_Command(self, key, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._unlock_CRO(counter=counter, key=key)
        return self._do_Function(msg=msg, command_type=utils.CCP_UNLOCK, currIdx=currIdx)

    def Send_BuildChksum_Command(self, data_block_size, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._build_chksum_CRO(counter=counter, data_block_size=data_block_size)
        return self._do_Function(msg=msg, command_type=utils.CCP_BUILD_CHKSUM, currIdx=currIdx)

    def Send_UploadShort_Command(self, address, address_extension, data_block_size=4, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._short_upload_CRO(counter=counter, address=address,
                                     address_extension=address_extension, data_block_size=data_block_size)
        return self._do_Function(msg=msg, command_type=utils.CCP_SHORT_UP, currIdx=currIdx)

    def Send_GetSStatus_Command(self, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._get_s_status_CRO(counter=counter)
        return self._do_Function(msg=msg, command_type=utils.CCP_GET_S_STATUS, currIdx=currIdx)

    def Send_SetSStatus_Command(self, session_status_mask, counter=COUNTER_VAL, timeout=1):
        currIdx = self.c.getCanMsgCount()

        msg = self._set_s_status_CRO(counter=counter, session_status_mask=session_status_mask)
        return self._do_Function(msg=msg, command_type=utils.CCP_SET_S_STATUS, currIdx=currIdx)

    def Send_SelectCalPage_Command(self, counter):
        currIdx = self.c.getCanMsgCount()

        msg = self._select_cal_page_CRO(self, counter)

        return self._do_Function(msg=msg, command_type=utils.CCP_SELECT_CAL_PAGE, currIdx=currIdx)

    def Send_GetActiveCalPage_Command(self, counter):
        currIdx = self.c.getCanMsgCount()

        msg = self._get_active_cal_page_CRO(self, counter)

        return self._do_Function(msg=msg, command_type=utils.CCP_GET_ACTIVE_CAL_PAGE, currIdx=currIdx)

    def Send_DiagService_Command(self, counter, diagnostic_service_num, parameters=None):
        currIdx = self.c.getCanMsgCount()

        msg = self._diag_service_CRO(self, counter, diagnostic_service_num, parameters)

        return self._do_Function(msg=msg, command_type=utils.CCP_DIAG_SERVICE, currIdx=currIdx)

    def Send_ActionService_Command(self, counter, action_service_num, parameters):
        currIdx = self.c.getCanMsgCount()

        msg = self._action_service_CRO(self, counter, action_service_num, parameters)

        return self._do_Function(msg=msg, command_type=utils.CCP_ACTION_SERVICE, currIdx=currIdx)

    def Send_GetDaqSize_Command(self, counter, daq_list_number, can_identifier):
        currIdx = self.c.getCanMsgCount()

        msg = self._get_daq_size_CRO(self, counter, daq_list_number, can_identifier)

        return self._do_Function(msg=msg, command_type=utils.CCP_GET_DAQ_SIZE, currIdx=currIdx)

    def Send_SetDaqPtr_Command(self, counter, daq_list_number, odt_number, odt_element_number):
        currIdx = self.c.getCanMsgCount()

        msg = self._set_daq_ptr_CRO(self, counter, daq_list_number, odt_number, odt_element_number)

        return self._do_Function(msg=msg, command_type=utils.CCP_SET_DAQ_PTR, currIdx=currIdx)

    def Send_WriteDaq_Command(self, counter, daq_element_size, daq_element_addr_extension, daq_element_addr):
        currIdx = self.c.getCanMsgCount()

        msg = self._write_daq_CRO(self, counter, daq_element_size, daq_element_addr_extension, daq_element_addr)

        return self._do_Function(msg=msg, command_type=utils.CCP_WRITE_DAQ, currIdx=currIdx)

    def Send_StartStop_Command(self, counter, mode, daq_list_number,
                               last_odt_num, event_chan_num, transmission_rate_prescaler):
        currIdx = self.c.getCanMsgCount()

        msg = self._start_stop_CRO(self, counter, mode, daq_list_number, last_odt_num,
                                   event_chan_num, transmission_rate_prescaler)

        return self._do_Function(msg=msg, command_type=utils.CCP_START_STOP, currIdx=currIdx)

    def Send_StartStopAll_Command(self, counter, start_or_stop):
        currIdx = self.c.getCanMsgCount()

        msg = self._start_stop_all_CRO(self, counter, start_or_stop)

        return self._do_Function(msg=msg, command_type=utils.CCP_START_STOP_ALL, currIdx=currIdx)
