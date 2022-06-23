import unittest
from .ccp_leader import CCPLeader, DTO_TYPE
from . import utils


class TestCcpMessageGeneration(unittest.TestCase):
    def runTest(self):
        unittest.main()

    def test_constructCRO_fails_if_not_8_bytes_long(self):
        ccp = CCPLeader(c=None)

        with self.assertRaises(Exception) as context:
            ccp._constructCRO(0x01, 0x02, b'\x03\x04\x05\x06\x07\x08\x09')

        self.assertTrue('Invalid message length' in str(context.exception))

    def test_Connect_CRO(self):
        ccp = CCPLeader(c=None)
        msg = ccp._connect_CRO(0x22, 0x200)

        expected = b'\x01\x22\x00\x02\x90\x90\x90\x90'

        self.assertEqual(msg, expected)

    def test_Disconnect_CRO(self):
        CTR = 0x23
        ccp = CCPLeader(c=None)
        temporary_disconnect_msg = ccp._disconnect_CRO(CTR, utils.TEMPORARY_DISCONNECT, 0x333)
        temporary_disconnect_expected = b'\x07\x23\x00\x90\x33\x03\x90\x90'
        self.assertEqual(temporary_disconnect_msg, temporary_disconnect_expected)

        EOS_disconnect_msg = ccp._disconnect_CRO(CTR, utils.END_OF_SESSION_DISCONNECT, 0x200)
        EOS_disconnect_expected = b'\x07\x23\x01\x90\x00\x02\x90\x90'
        self.assertEqual(EOS_disconnect_msg, EOS_disconnect_expected)

    def test_SetMTA_CRO(self):
        ccp = CCPLeader(c=None)

        CTR = 0x26

        address = 0xaabbccdd
        address_extension = 0x02
        msg_mta0 = ccp._set_MTA_CRO(CTR, 0, address_extension, address)
        expected_mta0 = b'\x02\x26\x00\x02\xaa\xbb\xcc\xdd'
        self.assertEqual(msg_mta0, expected_mta0)

        address = 0x34002000
        address_extension = 0x01
        msg_mta1 = ccp._set_MTA_CRO(CTR, 1, address_extension, 0x34002000)
        expected_mta1 = b'\x02\x26\x01\x01\x34\x00\x20\x00'
        self.assertEqual(msg_mta1, expected_mta1)

        with self.assertRaises(Exception) as context:
            mta_invalid = ccp._set_MTA_CRO(CTR, 3, 0x02, 0xaabbccdd)  # noqa: F841

        self.assertTrue('Invalid mta_number.  Must be either 1 for MTA1 (MOVE) '
                        'or 1 for MTA0 (all other read/write commands)' in str(context.exception))

    def test_Dnload_CRO(self):
        ccp = CCPLeader(c=None)

        CTR = 0x28
        # data block is 4 unless we specify otherwise
        expected_msg = b'\x03\x28\x04\xde\xad\xbe\xef\x90'
        msg_upload = ccp._download_CRO(CTR, 0xdeadbeef)
        self.assertEqual(msg_upload, expected_msg)

        # if we specify a different data block, needs to be <=5
        with self.assertRaises(Exception) as context:
            mta_invalid = ccp._download_CRO(CTR, 0xdeadbeef, 7)  # noqa: F841

        self.assertTrue("Cannot download data block larger than 5" in str(context.exception))

    def test_Program_CRO(self):
        ccp = CCPLeader(c=None)

        CTR = 0x29
        # data block is 4 unless we specify otherwise
        expected_msg = b'\x18\x29\x04\xca\xfe\xbe\xef\x90'
        msg_program = ccp._program_CRO(CTR, 0xcafebeef)
        self.assertEqual(msg_program, expected_msg)

        # if we specify a different data block, needs to be <=5
        with self.assertRaises(Exception) as context:
            mta_invalid = ccp._program_CRO(CTR, 0xcafebeef, 7)  # noqa: F841

        self.assertTrue("Cannot program data block larger than 5" in str(context.exception))

    def test_Move_CRO(self):
        ccp = CCPLeader(c=None)

        CTR = 0x30

        full_block_size = 0x10203040
        expected_msg = b'\x19\x30\x10\x20\x30\x40\x90\x90'
        msg = ccp._move_CRO(CTR, full_block_size)
        self.assertEqual(msg, expected_msg)

        partial_block = 0x8000
        expected_msg = b'\x19\x30\x00\x00\x80\x00\x90\x90'
        msg = ccp._move_CRO(CTR, partial_block)
        self.assertEqual(msg, expected_msg)

    def test_ClearMemory_CRO(self):
        ccp = CCPLeader(c=None)

        CTR = 0x31

        full_block_size = 0x40302010
        expected_msg = b'\x10\x31\x40\x30\x20\x10\x90\x90'
        msg = ccp._clear_memory_CRO(CTR, full_block_size)
        self.assertEqual(msg, expected_msg)

        partial_block = 0x2400
        expected_msg = b'\x10\x31\x00\x00\x24\x00\x90\x90'
        msg = ccp._clear_memory_CRO(CTR, partial_block)
        self.assertEqual(msg, expected_msg)

    def test_Test_CRO(self):
        ccp = CCPLeader(c=None)

        CTR = 0x32

        msg = ccp._test_CRO(CTR, 0x770)

        expected = b'\x05\x32\x70\x07\x90\x90\x90\x90'

        self.assertEqual(msg, expected)

    def test_ExchangeId_CRO(self):
        ccp = CCPLeader(c=None)

        CTR = 0x33

        expected = b'\x17\x33\x90\x90\x90\x90\x90\x90'

        msg = ccp._exchangeID_CRO(CTR)

        self.assertEqual(msg, expected)

    def test_GetCcpVersion_CRO(self):
        ccp = CCPLeader(c=None)

        CTR = 0x34

        major_version_desired = 2
        minor_version_desired = 1

        expected = b'\x1B\x34\x02\x01\x90\x90\x90\x90'

        msg = ccp._get_ccp_version_CRO(CTR, major_version_desired, minor_version_desired)

        self.assertEqual(msg, expected)

    def test_GetSeed_CRO(self):
        ccp = CCPLeader(c=None)

        CTR = 0x35

        requesting_pgm_resource = 0x32

        expected = b'\x12\x35\x32\x90\x90\x90\x90\x90'

        msg = ccp._get_seed_CRO(CTR, requesting_pgm_resource)

        self.assertEqual(msg, expected)

    def test_Build_Chksum_CRO(self):
        ccp = CCPLeader(c=None)

        CTR = 0x36

        full_block_size = 0x10203040
        expected_msg = b'\x0E\x36\x10\x20\x30\x40\x90\x90'
        msg = ccp._build_chksum_CRO(CTR, full_block_size)
        self.assertEqual(msg, expected_msg)

        partial_block = 0x8000
        expected_msg = b'\x0E\x36\x00\x00\x80\x00\x90\x90'
        msg = ccp._build_chksum_CRO(CTR, partial_block)
        self.assertEqual(msg, expected_msg)

    def test_Unlock_CRO(self):
        ccp = CCPLeader(c=None)

        CTR = 0x37

        key = '\x14\x15\x16\x17'
        expected_msg = b'\x13\x37\x14\x15\x16\x17\x90\x90'
        msg = ccp._unlock_CRO(CTR, key)
        self.assertEqual(msg, expected_msg)

        short_key = '\x13'
        short_key_expected_msg = b'\x13\x37\x13\x90\x90\x90\x90\x90'
        msg = ccp._unlock_CRO(CTR, short_key)
        self.assertEqual(msg, short_key_expected_msg)

        full_key = '\x14\x15\x16\x17\x18\x19'
        full_key_expected_msg = b'\x13\x37\x14\x15\x16\x17\x18\x19'
        msg = ccp._unlock_CRO(CTR, full_key)
        self.assertEqual(msg, full_key_expected_msg)

        with self.assertRaises(Exception) as context:
            too_long_key = '\x14\x15\x16\x17\x18\x19\x20'
            msg = ccp._unlock_CRO(CTR, too_long_key)

        self.assertTrue("Key cannot be longer than 6 bytes" in str(context.exception))

    def test_Upload_CRO(self):
        ccp = CCPLeader(c=None)

        CTR = 0x38

        address = 0x12345678
        address_extension = 0x00

        # data block is 4 unless we specify otherwise
        msg_upload = ccp._short_upload_CRO(CTR, address, address_extension)
        expected_msg = b'\x0F\x38\x04\x00\x12\x34\x56\x78'
        self.assertEqual(msg_upload, expected_msg)

        # if we specify a different data block, needs to be size 1-5
        with self.assertRaises(Exception) as context:
            mta_invalid = ccp._short_upload_CRO(CTR, address, address_extension, 0)  # noqa: F841

        self.assertTrue("Data block size must bye 1-5 bytes" in str(context.exception))

        with self.assertRaises(Exception) as context:
            mta_invalid = ccp._short_upload_CRO(CTR, address, address_extension, 7)  # noqa: F841

        self.assertTrue("Data block size must bye 1-5 bytes" in str(context.exception))

    def test_GetSStatus_CRO(self):
        ccp = CCPLeader(c=None)

        CTR = 0x39

        expected = b'\x0D\x39\x90\x90\x90\x90\x90\x90'
        msg = ccp._get_s_status_CRO(CTR)
        self.assertEqual(msg, expected)

    def test_SetSStatus_CRO(self):
        ccp = CCPLeader(c=None)

        CTR = 0x40

        expected = b'\x0D\x40\x81\x90\x90\x90\x90\x90'
        msg = ccp._set_s_status_CRO(CTR, 0x81)
        self.assertEqual(msg, expected)

    def test_SelectCalPage_CRO(self):
        ccp = CCPLeader(c=None)

        CTR = 0x41

        expected = b'\x11\x41\x90\x90\x90\x90\x90\x90'
        msg = ccp._select_cal_page_CRO(CTR)

        self.assertEqual(msg, expected)

    def test_GetActiveCalPage_CRO(self):
        ccp = CCPLeader(c=None)

        CTR = 0x42

        expected = b'\x09\x42\x90\x90\x90\x90\x90\x90'
        msg = ccp._get_active_cal_page_CRO(CTR)

        self.assertEqual(msg, expected)

    def test_ActionService_CRO(self):
        ccp = CCPLeader(c=None)

        CTR = 0x43
        action_service_num = 0x08
        params = 0x05

        expected = b'\x21\x43\x08\x05\x90\x90\x90\x90'
        msg = ccp._action_service_CRO(CTR, action_service_num, params)

        self.assertEqual(msg, expected)

    def test_DiagService_CRO(self):
        ccp = CCPLeader(c=None)

        CTR = 0x44
        diag_service_num = 0x08

        expected = b'\x20\x44\x08\x90\x90\x90\x90\x90'
        msg = ccp._diag_service_CRO(CTR, diag_service_num)

        self.assertEqual(msg, expected)

    def test_GetDaqSize_CRO(self):
        ccp = CCPLeader(c=None)

        CTR = 0x45
        daq_list_number = 0x3
        can_identifier = 0x01020304

        expected = b'\x14\x45\x03\x90\x01\x02\x03\x04'
        msg = ccp._get_daq_size_CRO(CTR, daq_list_number, can_identifier)

        self.assertEqual(msg, expected)

    def test_SetDaqPtr_CRO(self):
        ccp = CCPLeader(c=None)

        CTR = 0x46

        daq_list_number = 0x3
        odt_number = 0x5
        odt_element_number = 0x2

        expected = b'\x15\x46\x03\x05\x02\x90\x90\x90'
        msg = ccp._set_daq_ptr_CRO(CTR, daq_list_number, odt_number, odt_element_number)

        self.assertEqual(msg, expected)

    def test_WriteDaq_CRO(self):
        ccp = CCPLeader(c=None)

        CTR = 0x47

        daq_element_size = 0x2
        daq_element_addr_extension = 0x1
        daq_element_addr = 0x20004200

        expected = b'\x16\x47\x02\x01\x20\x00\x42\x00'
        msg = ccp._write_daq_CRO(CTR, daq_element_size, daq_element_addr_extension, daq_element_addr)

        self.assertEqual(msg, expected)

    def test_StartStop_CRO(self):
        ccp = CCPLeader(c=None)

        CTR = 0x48

        mode = 0x1  # mode =  start
        daq_list_number = 0x3
        last_odt_num = 0x7
        event_chan_num = 0x2
        transmission_rate_prescaler = 0x1

        expected = b'\x06\x48\x01\x03\x07\x02\x00\x01'
        msg = ccp._start_stop_CRO(CTR, mode, daq_list_number, last_odt_num, event_chan_num, transmission_rate_prescaler)

        self.assertEqual(msg, expected)

    def testStartStopAll_CRO(self):
        ccp = CCPLeader(c=None)

        CTR = 0x49

        start_or_stop = 0x01

        expected = b'\x08\x49\x01\x90\x90\x90\x90\x90'
        msg = ccp._start_stop_all_CRO(CTR, start_or_stop)

        self.assertEqual(msg, expected)

    def test_sanity(self):
        self.assertEqual('beep', 'BEEP'.lower())


class TestCcpMessageParsing(unittest.TestCase):
    def runTest(self):
        unittest.main()

    def test_parse_message_should_be_length_8(self):
        ccp = CCPLeader(c=None)

        with self.assertRaises(Exception) as context:
            too_short_message = b'\xFF\x02\x03\x04'
            ccp._parse_DTO_type(too_short_message)

        self.assertTrue('CCP message should have length 8' in str(context.exception))

        with self.assertRaises(Exception) as context:
            too_long_message = b'\xFF\x02\x03\x04\x05\x06\x07\x08\x09'
            ccp._parse_DTO_type(too_long_message)

        self.assertTrue('CCP message should have length 8' in str(context.exception))

    def test_parse_message_should_interpret_first_byte(self):
        ccp = CCPLeader(c=None)

        message = b'\xff\x00\x03\x04\x05\x06\x07\x08'
        ret = ccp._parse_DTO_type(message)
        self.assertEqual(ret, DTO_TYPE.CRO_TYPE)

        message = b'\xfe\x00\x03\x04\x05\x06\x07\x08'
        ret = ccp._parse_DTO_type(message)
        self.assertEqual(ret, DTO_TYPE.EVENT_TYPE)

        message = b'\xad\x00\x03\x04\x05\x06\x07\x08'
        ret = ccp._parse_DTO_type(message)
        self.assertEqual(ret, DTO_TYPE.DAQ_TYPE)

    def test_parse_Connect_CRM(self):
        ccp = CCPLeader(c=None)

        Connect_CRM = b'\xff\x00\x03\x04\x05\x06\x07\x08'
        parsed = ccp._parse_Command_Return_Message(Connect_CRM, utils.CCP_CONNECT)
        expected = {
            'CRC': 'acknowledge / no error', 'CTR': 0x3}
        self.assertEqual(parsed, expected)

        Connect_CRM_timeout = b'\xff\x33\x18\x04\x05\x06\x07\x08'
        parsed = ccp._parse_Command_Return_Message(Connect_CRM_timeout, utils.CCP_CONNECT)
        expected = {
            'CRC': 'access denied', 'CTR': 0x18}
        self.assertEqual(parsed, expected)

    def test_parse_Disconnect_CRM(self):
        ccp = CCPLeader(c=None)

        Disconnect_CRM = b'\xff\x00\x04\x90\x90\x90\x90\x90'
        parsed = ccp._parse_Command_Return_Message(Disconnect_CRM, utils.CCP_DISCONNECT)
        expected = {
            'CRC': 'acknowledge / no error', 'CTR': 0x4}
        self.assertEqual(parsed, expected)

        Disconnect_CRM_timeout = b'\xff\x12\x19\x90\x90\x90\x90\x90'
        parsed = ccp._parse_Command_Return_Message(Disconnect_CRM_timeout, utils.CCP_DISCONNECT)
        expected = {
            'CRC': 'internal timeout', 'CTR': 0x19}
        self.assertEqual(parsed, expected)

    def test_parse_SetMTA_CRM(self):
        ccp = CCPLeader(c=None)

        SetMTA_CRM = b'\xff\x00\x20\x90\x90\x90\x90\x90'
        parsed = ccp._parse_Command_Return_Message(SetMTA_CRM, utils.CCP_SET_MTA)
        expected = {
            'CRC': 'acknowledge / no error', 'CTR': 0x20}
        self.assertEqual(parsed, expected)

        SetMTA_CRM_timeout = b'\xff\x12\x20\x90\x90\x90\x90\x90'
        parsed = ccp._parse_Command_Return_Message(SetMTA_CRM_timeout, utils.CCP_SET_MTA)
        expected = {
            'CRC': 'internal timeout', 'CTR': 0x20}
        self.assertEqual(parsed, expected)

    def test_parse_Dnload_CRM(self):
        ccp = CCPLeader(c=None)

        Dnload_CRM = b'\xff\x00\x21\x02\x34\x00\x20\x05'
        parsed = ccp._parse_Command_Return_Message(Dnload_CRM, utils.CCP_DNLOAD)
        expected = {
            'CRC': 'acknowledge / no error', 'CTR': 0x21, 'mta_extension': 0x2, 'mta_address': '0x34002005'}
        self.assertEqual(parsed, expected)

    def test_parse_Program_CRM(self):
        ccp = CCPLeader(c=None)

        Dnload_CRM = b'\xff\x00\x18\x02\x34\x00\x20\x04'
        parsed = ccp._parse_Command_Return_Message(Dnload_CRM, utils.CCP_DNLOAD)
        expected = {
            'CRC': 'acknowledge / no error', 'CTR': 0x18, 'mta_extension': 0x2, 'mta_address': '0x34002004'}
        self.assertEqual(parsed, expected)

    def test_parse_Upload_CRM(self):
        ccp = CCPLeader(c=None)

        Upload_CRM = b'\xff\x00\x23\x4e\xee\xee\xe7\x90'
        parsed = ccp._parse_Command_Return_Message(Upload_CRM, utils.CCP_UPLOAD)
        expected = {
            'CRC': 'acknowledge / no error', 'CTR': 0x23, 'data': '0x4eeeeee7'}
        self.assertEqual(parsed, expected)

    def test_parse_Short_Upload_CRM(self):
        # uses same function as UPLOAD
        ccp = CCPLeader(c=None)

        Upload_CRM = b'\xff\x00\x24\x4e\xee\xee\xe7\x90'
        parsed = ccp._parse_Command_Return_Message(Upload_CRM, utils.CCP_SHORT_UP)
        expected = {
            'CRC': 'acknowledge / no error', 'CTR': 0x24, 'data': '0x4eeeeee7'}
        self.assertEqual(parsed, expected)

    def test_parse_ClearMemory_CRM(self):
        ccp = CCPLeader(c=None)

        ClearMemory_CRM = b'\xff\x00\x20\x90\x90\x90\x90\x90'
        parsed = ccp._parse_Command_Return_Message(ClearMemory_CRM, utils.CCP_CLEAR_MEMORY)
        expected = {
            'CRC': 'acknowledge / no error', 'CTR': 0x20}
        self.assertEqual(parsed, expected)

        ClearMemory_CRM_overload = b'\xff\x01\x21\x90\x90\x90\x90\x90'
        parsed = ccp._parse_Command_Return_Message(ClearMemory_CRM_overload, utils.CCP_CLEAR_MEMORY)
        expected = {
            'CRC': 'DAQ processor overload', 'CTR': 0x21}
        self.assertEqual(parsed, expected)

    def test_parse_move_CRM(self):
        ccp = CCPLeader(c=None)

        Move_CRM = b'\xff\x00\x22\x90\x90\x90\x90\x90'
        parsed = ccp._parse_Command_Return_Message(Move_CRM, utils.CCP_MOVE)
        expected = {
            'CRC': 'acknowledge / no error', 'CTR': 0x22}
        self.assertEqual(parsed, expected)

        ClearMemory_CRM_busy = b'\xff\x10\x23\x90\x90\x90\x90\x90'
        parsed = ccp._parse_Command_Return_Message(ClearMemory_CRM_busy, utils.CCP_CLEAR_MEMORY)
        expected = {
            'CRC': 'command processor busy', 'CTR': 0x23}
        self.assertEqual(parsed, expected)

    def test_parse_Test_CRM(self):
        ccp = CCPLeader(c=None)

        Test_CRM = b'\xff\x00\x24\x90\x90\x90\x90\x90'
        parsed = ccp._parse_Command_Return_Message(Test_CRM, utils.CCP_TEST)
        expected = {
            'CRC': 'acknowledge / no error', 'CTR': 0x24}
        self.assertEqual(parsed, expected)

        Test_CRM_timeout = b'\xff\x12\x25\x90\x90\x90\x90\x90'
        parsed = ccp._parse_Command_Return_Message(Test_CRM_timeout, utils.CCP_CLEAR_MEMORY)
        expected = {
            'CRC': 'internal timeout', 'CTR': 0x25}
        self.assertEqual(parsed, expected)

    def test_parse_ExchangeID_CRM(self):
        ccp = CCPLeader(c=None)

        ExchangeID_CRM = b'\xff\x00\x25\x04\x02\x03\x01\x90'
        parsed = ccp._parse_Command_Return_Message(ExchangeID_CRM, utils.CCP_EXCHANGE_ID)
        expected = {
            'CRC': 'acknowledge / no error',
            'CTR': 0x25,
            'follower_deviceID_length': 0x4,
            'follower_deviceID_data_type_qual': 0x2,
            'resource_availability_mask': 0x3,
            'resource_protection_mask': 0x1
        }
        self.assertEqual(parsed, expected)

    def test_parse_CCPVersion_CRM(self):
        ccp = CCPLeader(c=None)

        CCPVersion_CRM = b'\xff\x00\x26\x02\x01\x90\x90\x90'
        parsed = ccp._parse_Command_Return_Message(CCPVersion_CRM, utils.CCP_GET_CCP_VERSION)
        expected = {
            'CRC': 'acknowledge / no error',
            'CTR': 0x26,
            'main_protocol': 0x2,
            'minor_protocol': 0x1
        }
        self.assertEqual(parsed, expected)

    def test_parse_GetSeed_CRM(self):
        ccp = CCPLeader(c=None)

        GetSeed_CRM_true = b'\xff\x00\x27\x01\x14\x15\x16\x17'
        parsed = ccp._parse_Command_Return_Message(GetSeed_CRM_true, utils.CCP_GET_SEED)
        expected = {
            'CRC': 'acknowledge / no error',
            'CTR': 0x27,
            'protection_status': True,
            'seed_data': '0x14151617'
        }
        self.assertEqual(parsed, expected)

        GetSeed_CRM_false = b'\xff\x00\x27\x00\x14\x15\x16\x17'
        parsed = ccp._parse_Command_Return_Message(GetSeed_CRM_false, utils.CCP_GET_SEED)
        expected = {
            'CRC': 'acknowledge / no error',
            'CTR': 0x27,
            'protection_status': False,
            'seed_data': '0x14151617'
        }
        self.assertEqual(parsed, expected)

    def test_parse_BuildChksum_CRM(self):
        ccp = CCPLeader(c=None)

        BuildChksum_CRM_2byte = b'\xff\x00\x28\x02\x12\x34\x90\x90'
        parsed = ccp._parse_Command_Return_Message(BuildChksum_CRM_2byte, utils.CCP_BUILD_CHKSUM)
        expected = {
            'CRC': 'acknowledge / no error',
            'CTR': 0x28,
            'chksum_size': 0x2,
            'chksum_data': '0x1234'
        }
        self.assertEqual(parsed, expected)

        BuildChksum_CRM_4byte = b'\xff\x00\x29\x04\x12\x34\x56\x78'
        parsed = ccp._parse_Command_Return_Message(BuildChksum_CRM_4byte, utils.CCP_BUILD_CHKSUM)
        expected = {
            'CRC': 'acknowledge / no error',
            'CTR': 0x29,
            'chksum_size': 0x4,
            'chksum_data': '0x12345678'
        }

        self.assertEqual(parsed, expected)

    def test_parse_Unlock_CRM(self):
        ccp = CCPLeader(c=None)

        Unlock_CRM = b'\xff\x00\x30\x03\x90\x90\x90\x90'
        parsed = ccp._parse_Command_Return_Message(Unlock_CRM, utils.CCP_UNLOCK)
        expected = {
            'CRC': 'acknowledge / no error',
            'CTR': 0x30,
            'resource_mask': 0x3,
        }
        self.assertEqual(parsed, expected)

    def test_parse_SetSStatus_CRM(self):
        ccp = CCPLeader(c=None)

        SetSStatus_CRM = b'\xff\x00\x31\x90\x90\x90\x90\x90'
        parsed = ccp._parse_Command_Return_Message(SetSStatus_CRM, utils.CCP_SET_S_STATUS)
        expected = {
            'CRC': 'acknowledge / no error',
            'CTR': 0x31
        }
        self.assertEqual(parsed, expected)

    def test_parse_GetSStatus_CRM(self):
        ccp = CCPLeader(c=None)

        GetSStatus_CRM_no_addl_info = b'\xff\x00\x32\x81\x00\x90\x90\x90'
        parsed = ccp._parse_Command_Return_Message(GetSStatus_CRM_no_addl_info, utils.CCP_GET_S_STATUS)
        expected = {
            'CRC': 'acknowledge / no error',
            'CTR': 0x32,
            'session_status': 0x81,
            'addl_info_bool': False
        }
        self.assertEqual(parsed, expected)

        GetSStatus_CRM = b'\xff\x00\x33\x83\x01\x12\x34\x45'
        parsed = ccp._parse_Command_Return_Message(GetSStatus_CRM, utils.CCP_GET_S_STATUS)
        expected = {
            'CRC': 'acknowledge / no error',
            'CTR': 0x33,
            'session_status': 0x83,
            'addl_info_bool': True,
            'addl_info': 'not implemented yet'
        }
        self.assertEqual(parsed, expected)

    def test_parse_select_cal_page_CRM(self):
        ccp = CCPLeader(c=None)

        SelectCalPage_CRM = b'\xff\x00\x33\x90\x90\x90\x90\x90'

        parsed = ccp._parse_select_cal_page_CRM(SelectCalPage_CRM)
        expected = {
            'CRC': 'acknowledge / no error',
            'CTR': 0x33,
        }

        self.assertEqual(parsed, expected)

    def test_parse_get_active_cal_page_CRM(self):
        ccp = CCPLeader(c=None)

        GetActiveCalPage_CRM = b'\xff\x00\x34\x01\xde\xad\xbe\xef'

        parsed = ccp._parse_get_active_cal_page_CRM(GetActiveCalPage_CRM)
        expected = {
            'CRC': 'acknowledge / no error',
            'CTR': 0x34,
            'address_ext': 1,
            'address': '0xdeadbeef'
        }

        self.assertEqual(parsed, expected)

    def test_parse_diag_service_CRM(self):
        ccp = CCPLeader(c=None)

        DiagService_CRM = b'\xff\x00\x35\x20\x00\x90\x90\x90'

        parsed = ccp._parse_diag_service_CRM(DiagService_CRM)
        expected = {
            'CRC': 'acknowledge / no error',
            'CTR': 0x35,
            'length_of_return_info': 0x20,
            'data_type_qual': 0,
        }

        self.assertEqual(parsed, expected)

    def test_parse_action_service_CRM(self):
        ccp = CCPLeader(c=None)

        ActionService_CRM = b'\xff\x00\x36\x20\x00\x90\x90\x90'

        parsed = ccp._parse_action_service_CRM(ActionService_CRM)
        expected = {
            'CRC': 'acknowledge / no error',
            'CTR': 0x36,
            'length_of_return_info': 0x20,
            'data_type_qual': 0
        }

        self.assertEqual(parsed, expected)

    def test_parse_get_daq_size_CRM(self):
        ccp = CCPLeader(c=None)

        GetDaqSize_CRM = b'\xff\x00\x37\x10\x08\x90\x90\x90'

        parsed = ccp._parse_get_daq_size_CRM(GetDaqSize_CRM)
        expected = {
            'CRC': 'acknowledge / no error',
            'CTR': 0x37,
            'daq_list_size': 0x10,
            'first_pid': 0x8,
        }

        self.assertEqual(parsed, expected)

    def test_parse_set_daq_ptr_CRM(self):
        ccp = CCPLeader(c=None)

        SetDaqPtr_CRM = b'\xff\x00\x38\x90\x90\x90\x90\x90'

        parsed = ccp._parse_set_daq_ptr_CRM(SetDaqPtr_CRM)
        expected = {
            'CRC': 'acknowledge / no error', 'CTR': 0x38,
        }

        self.assertEqual(parsed, expected)

    def test_parse_write_daq_CRM(self):
        ccp = CCPLeader(c=None)

        WriteDaq_CRM = b'\xff\x00\x39\x90\x90\x90\x90\x90'

        parsed = ccp._parse_write_daq_CRM(WriteDaq_CRM)
        expected = {
            'CRC': 'acknowledge / no error',
            'CTR': 0x39,
        }

        self.assertEqual(parsed, expected)

    def test_parse_start_stop_CRM(self):
        ccp = CCPLeader(c=None)

        StartStop_CRM = b'\xff\x00\x40\x90\x90\x90\x90\x90'

        parsed = ccp._parse_start_stop_CRM(StartStop_CRM)
        expected = {
            'CRC': 'acknowledge / no error',
            'CTR': 0x40,
        }

        self.assertEqual(parsed, expected)

    def test_parse_start_stop_all_CRM(self):
        ccp = CCPLeader(c=None)

        StartStopAll_CRM = b'\xff\x00\x41\x90\x90\x90\x90\x90'

        parsed = ccp._parse_start_stop_all_CRM(StartStopAll_CRM)
        expected = {
            'CRC': 'acknowledge / no error',
            'CTR': 0x41,
        }

        self.assertEqual(parsed, expected)


if __name__ == '__main__':
    unittest.main()
