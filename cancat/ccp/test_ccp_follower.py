import unittest
from .ccp_follower import CCPFollower
from unittest.mock import MagicMock


class TestCcpFollowerMessageParsing(unittest.TestCase):

    def runTest(self):
        unittest.main()

    def test_parse_CRO(self):
        # this tests top-level if/elif block for correct parsing

        ccp = CCPFollower(c=None)

        ccp._parse_connect_CRO = MagicMock()
        ccp._parse_disconnect_CRO = MagicMock()
        ccp._parse_setMTA_CRO = MagicMock()
        ccp._parse_dnload_CRO = MagicMock()
        ccp._parse_upload_CRO = MagicMock()
        ccp._parse_short_upload_CRO = MagicMock()
        ccp._parse_clear_memory_CRO = MagicMock()
        ccp._parse_move_CRO = MagicMock()
        ccp._parse_test_CRO = MagicMock()
        ccp._parse_program_CRO = MagicMock()
        ccp._parse_exchangeID_CRO = MagicMock()
        ccp._parse_ccp_version_CRO = MagicMock()
        ccp._parse_get_seed_CRO = MagicMock()
        ccp._parse_build_chksum_CRO = MagicMock()
        ccp._parse_unlock_CRO = MagicMock()
        ccp._parse_set_s_status_CRO = MagicMock()
        ccp._parse_get_s_status_CRO = MagicMock()

        msg = b'\x01\x90\x90\x90\x90\x90\x90\x90'
        ccp._parse_CRO(msg)
        self.assertTrue(ccp._parse_connect_CRO.called)

        msg = b'\x07\x90\x90\x90\x90\x90\x90\x90'
        ccp._parse_CRO(msg)
        self.assertTrue(ccp._parse_disconnect_CRO.called)

        msg = b'\x02\x90\x90\x90\x90\x90\x90\x90'
        ccp._parse_CRO(msg)
        self.assertTrue(ccp._parse_setMTA_CRO.called)

        msg = b'\x03\x90\x90\x90\x90\x90\x90\x90'
        ccp._parse_CRO(msg)
        self.assertTrue(ccp._parse_dnload_CRO.called)

        msg = b'\x04\x90\x90\x90\x90\x90\x90\x90'
        ccp._parse_CRO(msg)
        self.assertTrue(ccp._parse_upload_CRO.called)

        msg = b'\x0f\x90\x90\x90\x90\x90\x90\x90'
        ccp._parse_CRO(msg)
        self.assertTrue(ccp._parse_short_upload_CRO.called)

        msg = b'\x10\x90\x90\x90\x90\x90\x90\x90'
        ccp._parse_CRO(msg)
        self.assertTrue(ccp._parse_clear_memory_CRO.called)

        msg = b'\x19\x90\x90\x90\x90\x90\x90\x90'
        ccp._parse_CRO(msg)
        self.assertTrue(ccp._parse_move_CRO.called)

        msg = b'\x05\x90\x90\x90\x90\x90\x90\x90'
        ccp._parse_CRO(msg)
        self.assertTrue(ccp._parse_test_CRO.called)

        msg = b'\x18\x90\x90\x90\x90\x90\x90\x90'
        ccp._parse_CRO(msg)
        self.assertTrue(ccp._parse_program_CRO.called)

        msg = b'\x17\x90\x90\x90\x90\x90\x90\x90'
        ccp._parse_CRO(msg)
        self.assertTrue(ccp._parse_exchangeID_CRO.called)

        msg = b'\x1b\x90\x90\x90\x90\x90\x90\x90'
        ccp._parse_CRO(msg)
        self.assertTrue(ccp._parse_ccp_version_CRO.called)

        msg = b'\x12\x90\x90\x90\x90\x90\x90\x90'
        ccp._parse_CRO(msg)
        self.assertTrue(ccp._parse_get_seed_CRO.called)

        msg = b'\x0e\x90\x90\x90\x90\x90\x90\x90'
        ccp._parse_CRO(msg)
        self.assertTrue(ccp._parse_build_chksum_CRO.called)

        msg = b'\x13\x90\x90\x90\x90\x90\x90\x90'
        ccp._parse_CRO(msg)
        self.assertTrue(ccp._parse_unlock_CRO.called)

        msg = b'\x0c\x90\x90\x90\x90\x90\x90\x90'
        ccp._parse_CRO(msg)
        self.assertTrue(ccp._parse_set_s_status_CRO.called)

        msg = b'\x0d\x90\x90\x90\x90\x90\x90\x90'
        ccp._parse_CRO(msg)
        self.assertTrue(ccp._parse_get_s_status_CRO.called)

        with self.assertRaises(Exception) as context:
            invalid_msg = b'\xff\x90\x90\x90\x90\x90\x90\x90'
            ccp._parse_CRO(invalid_msg)

        self.assertTrue('Cannot parse message type' in str(context.exception))

    def test_parse_connect_CRO(self):
        ccp = CCPFollower(c=None)
        received_CRO = b'\x01\x20\x33\x03\x90\x90\x90\x90'
        expected = {'CMD': 0x1, 'CTR': 0x20, 'stat_addr': '0x333'}
        parsed = ccp._parse_connect_CRO(received_CRO)
        self.assertEqual(parsed, expected)

    def test_parse_exchangeID_CRO(self):
        ccp = CCPFollower(c=None)
        received_CRO = b'\x17\x21\x90\x90\x90\x90\x90\x90'
        expected = {'CMD': 0x17, 'CTR': 0x21, 'DEVICE_ID': '0x909090909090'}
        parsed = ccp._parse_exchangeID_CRO(received_CRO)
        self.assertEqual(parsed, expected)

    def test_parse_set_MTA_CRO(self):
        ccp = CCPFollower(c=None)
        received_CRO = b'\x02\x22\x00\x02\x12\x34\x56\x78'
        expected = {'CMD': 0x2, 'CTR': 0x22, 'mta_number': 0,
                    'address_extension': 2, 'address': '0x12345678'}
        parsed = ccp._parse_set_MTA_CRO(received_CRO)
        self.assertEqual(parsed, expected)

    def test_parse_download_CRO(self):
        ccp = CCPFollower(c=None)
        received_CRO = b'\x03\x23\x04\xde\xad\xbe\xef\x90'
        expected = {'CMD': 0x3, 'CTR': 0x23, 'data_block_size': 4,
                    'data': '0xdeadbeef'}
        parsed = ccp._parse_download_CRO(received_CRO)
        self.assertEqual(parsed, expected)

    def test_parse_upload_CRO(self):
        ccp = CCPFollower(c=None)
        received_CRO = b'\x04\x24\x05\x90\x90\x90\x90\x90'
        expected = {'CMD': 0x4, 'CTR': 0x24, 'data_block_size': 5}
        parsed = ccp._parse_upload_CRO(received_CRO)
        self.assertEqual(parsed, expected)

    def test_parse_disconnect_CRO(self):
        ccp = CCPFollower(c=None)
        received_CRO = b'\x07\x25\x01\x90\x44\x04\x90\x90'
        expected = {'CMD': 0x7, 'CTR': 0x25, 'disconnect_type': 1, 'stat_addr': '0x444'}
        parsed = ccp._parse_disconnect_CRO(received_CRO)
        self.assertEqual(parsed, expected)

    def test_parse_program_CRO(self):
        ccp = CCPFollower(c=None)
        received_CRO = b'\x18\x26\x04\xde\xad\xbe\xef\x90'
        expected = {'CMD': 0x18, 'CTR': 0x26, 'data_block_size': 4, 'data': '0xdeadbeef'}
        parsed = ccp._parse_program_CRO(received_CRO)
        self.assertEqual(parsed, expected)

    def test_parse_move_CRO(self):
        ccp = CCPFollower(c=None)
        received_CRO = b'\x19\x27\x00\x00\x80\x00\x90\x90'
        expected = {'CMD': 0x19, 'CTR': 0x27, 'memory_size': '0x8000'}
        parsed = ccp._parse_move_CRO(received_CRO)
        self.assertEqual(parsed, expected)

    def test_parse_clear_memory_CRO(self):
        ccp = CCPFollower(c=None)
        received_CRO = b'\x10\x28\x00\x00\x80\x00\x90\x90'
        expected = {'CMD': 0x10, 'CTR': 0x28, 'memory_size': '0x8000'}
        parsed = ccp._parse_clear_memory_CRO(received_CRO)
        self.assertEqual(parsed, expected)

    def testrunner_leader_parse_test_CRO(self):
        ccp = CCPFollower(c=None)
        received_CRO = b'\x05\x29\x55\x05\x90\x90\x90\x90'
        expected = {'CMD': 0x5, 'CTR': 0x29, 'stat_addr': '0x555'}
        parsed = ccp._parse_test_CRO(received_CRO)
        self.assertEqual(parsed, expected)

    def test_parse_get_ccp_version_CRO(self):
        ccp = CCPFollower(c=None)
        received_CRO = b'\x1b\x30\x02\x01\x90\x90\x90\x90'
        expected = {'CMD': 0x1b, 'CTR': 0x30, 'main_protocol': 2, 'minor_protocol': 1}
        parsed = ccp._parse_get_ccp_version_CRO(received_CRO)
        self.assertEqual(parsed, expected)

    def test_parse_get_seed_CRO(self):
        ccp = CCPFollower(c=None)
        received_CRO = b'\x12\x31\x02\x90\x90\x90\x90\x90'
        expected = {'CMD': 0x12, 'CTR': 0x31, 'requested_resource': 2}
        parsed = ccp._parse_get_seed_CRO(received_CRO)
        self.assertEqual(parsed, expected)

    def test_parse_unlock_CRO(self):
        ccp = CCPFollower(c=None)
        received_CRO = b'\x13\x32\x4e\xee\xee\xee\xee\xe7'
        expected = {'CMD': 0x13, 'CTR': 0x32, 'key': '0x4eeeeeeeeee7'}
        parsed = ccp._parse_unlock_CRO(received_CRO)
        self.assertEqual(parsed, expected)

    def test_parse_build_chksum_CRO(self):
        ccp = CCPFollower(c=None)
        received_CRO = b'\x0e\x33\x00\x00\x80\x00\x90\x90'
        expected = {'CMD': 0xe, 'CTR': 0x33, 'memory_size': '0x8000'}
        parsed = ccp._parse_build_chksum_CRO(received_CRO)
        self.assertEqual(parsed, expected)

    def test_parse_short_upload_CRO(self):
        ccp = CCPFollower(c=None)
        received_CRO = b'\x0f\x34\x04\x02\x12\x34\x56\x78'
        expected = {'CMD': 0xf, 'CTR': 0x34, 'data_block_size': 0x4,
                    'address_extension': 0x2, 'address': '0x12345678'}
        parsed = ccp._parse_short_upload_CRO(received_CRO)
        self.assertEqual(parsed, expected)

    def test_parse_get_s_status_CRO(self):
        ccp = CCPFollower(c=None)
        received_CRO = b'\x0c\x35\x90\x90\x90\x90\x90\x90'
        expected = {'CMD': 0xc, 'CTR': 0x35}
        parsed = ccp._parse_get_s_status_CRO(received_CRO)
        self.assertEqual(parsed, expected)

    def test_parse_set_s_status_CRO(self):
        ccp = CCPFollower(c=None)
        received_CRO = b'\x0d\x36\x03\x90\x90\x90\x90\x90'
        expected = {'CMD': 0xd, 'CTR': 0x36, 'session_status_bits': 0x3}
        parsed = ccp._parse_set_s_status_CRO(received_CRO)
        self.assertEqual(parsed, expected)

    def test_parse_select_cal_page_CRO(self):
        ccp = CCPFollower(c=None)
        received_CRO = b'\x11\x37\x90\x90\x90\x90\x90\x90'
        expected = {'CMD': 0x11, 'CTR': 0x37}
        parsed = ccp._parse_select_cal_page_CRO(received_CRO)
        self.assertEqual(parsed, expected)

    def test_parse_get_active_cal_page_CRO(self):
        ccp = CCPFollower(c=None)
        received_CRO = b'\x09\x38\x90\x90\x90\x90\x90\x90'
        expected = {'CMD': 0x09, 'CTR': 0x38}
        parsed = ccp._parse_get_active_cal_page_CRO(received_CRO)
        self.assertEqual(parsed, expected)

    def test_parse_diag_service_CRO(self):
        ccp = CCPFollower(c=None)
        received_CRO = b'\x20\x39\x08\x00\x00\x00\x00\x00'
        expected = {'CMD': 0x20, 'CTR': 0x39, 'diag_service_num': '0x8', 'params': '0x0'}
        parsed = ccp._parse_diag_service_CRO(received_CRO)
        self.assertEqual(parsed, expected)

    def test_parse_action_service_CRO(self):
        ccp = CCPFollower(c=None)
        received_CRO = b'\x21\x3a\x08\x00\x05\x00\x00\x00'
        expected = {'CMD': 0x21, 'CTR': 0x3a, 'action_service_num': '0x8', 'params': '0x5000000'}
        parsed = ccp._parse_action_service_CRO(received_CRO)
        self.assertEqual(parsed, expected)

    def test_parse_get_daq_size_CRO(self):
        ccp = CCPFollower(c=None)
        received_CRO = b'\x14\x3b\x01\x90\x33\x44\x55\x66'
        expected = {'CMD': 0x14, 'CTR': 0x3b, 'daq_list_num': 1, 'can_dto_id': '0x33445566'}
        parsed = ccp._parse_get_daq_size_CRO(received_CRO)
        self.assertEqual(parsed, expected)

    def test_parse_set_daq_ptr_CRO(self):
        ccp = CCPFollower(c=None)
        received_CRO = b'\x15\x3c\x02\x01\x03\x90\x90\x90'
        expected = {'CMD': 0x15, 'CTR': 0x3c, 'daq_list_num': 2, 'odt_num': 1, 'odt_elem_num': 3}
        parsed = ccp._parse_set_daq_ptr_CRO(received_CRO)
        self.assertEqual(parsed, expected)

    def test_parse_write_daq_CRO(self):
        ccp = CCPFollower(c=None)
        received_CRO = b'\x16\x3d\x04\x01\xca\xfe\xca\xfe'
        expected = {'CMD': 0x16, 'CTR': 0x3d, 'daq_elem_size': 4, 'address_ext': 1, 'address': '0xcafecafe'}
        parsed = ccp._parse_write_daq_CRO(received_CRO)
        self.assertEqual(parsed, expected)

    def test_parse_start_stop_CRO(self):
        ccp = CCPFollower(c=None)
        received_CRO = b'\x06\x3e\x02\x01\x05\x02\x00\x01'
        expected = {'CMD': 0x06, 'CTR': 0x3e, 'mode': 2, 'daq_list_num': 1,
                    'last_odt_num': 5, 'event_chan_num': 2, 'prescaler': '0x1'}
        parsed = ccp._parse_start_stop_CRO(received_CRO)
        self.assertEqual(parsed, expected)

    def test_parse_start_stop_all_CRO(self):
        ccp = CCPFollower(c=None)
        received_CRO = b'\x08\x3f\x01\x90\x90\x90\x90\x90'
        expected = {'CMD': 0x08, 'CTR': 0x3f, 'mode': 1}
        parsed = ccp._parse_start_stop_all_CRO(received_CRO)
        self.assertEqual(parsed, expected)

    def test_sanity_check(self):
        self.assertEqual('beep', 'BEEP'.lower())


class TestCCPFollowerMessageGeneration(unittest.TestCase):
    def runTest(self):
        unittest.main()

    def test_sanity_check(self):
        self.assertEqual('beep', 'BEEP'.lower())

    def test_generate_connect_CRM(self):
        counter = 0x70
        ccp = CCPFollower(c=None)
        msg = ccp._generate_connect_CRM(0x00, counter)
        expected = b'\xff\x00\x70\x90\x90\x90\x90\x90'
        self.assertEqual(msg, expected)

    def test_generate_disconnect_CRM(self):
        counter = 0x71
        ccp = CCPFollower(c=None)
        msg = ccp._generate_disconnect_CRM(0x33, counter)
        expected = b'\xff\x33\x71\x90\x90\x90\x90\x90'
        self.assertEqual(msg, expected)

    def test_generate_setMTA_CRM(self):
        counter = 0x71
        ccp = CCPFollower(c=None)
        msg = ccp._generate_setMTA_CRM(0x00, counter)
        expected = b'\xff\x00\x71\x90\x90\x90\x90\x90'
        self.assertEqual(msg, expected)

    def test_generate_dnload_CRM(self):
        counter = 0x72
        mta_extension = 2
        mta_address = 0x12345678

        ccp = CCPFollower(c=None)
        msg = ccp._generate_dnload_CRM(0x00, counter, mta_extension, mta_address)
        expected = b'\xff\x00\x72\x02\x12\x34\x56\x78'
        self.assertEqual(msg, expected)

    def test_generate_program_CRM(self):
        counter = 0x73
        mta_extension = 2
        mta_address = 0x12345678

        ccp = CCPFollower(c=None)
        msg = ccp._generate_program_CRM(0x00, counter, mta_extension, mta_address)
        expected = b'\xff\x00\x73\x02\x12\x34\x56\x78'
        self.assertEqual(msg, expected)

    def test_generate_upload_CRM(self):
        counter = 0x74
        data = 0xdeadbeef
        ccp = CCPFollower(c=None)
        msg = ccp._generate_upload_CRM(0x00, counter, data)
        expected = b'\xff\x00\x74\xde\xad\xbe\xef\x90'
        self.assertEqual(msg, expected)

    def test_generate_clear_memory_CRM(self):
        counter = 0x75
        ccp = CCPFollower(c=None)
        msg = ccp._generate_clear_memory_CRM(0x00, counter)
        expected = b'\xff\x00\x75\x90\x90\x90\x90\x90'
        self.assertEqual(msg, expected)

    def test_generate_move_CRM(self):
        counter = 0x76
        ccp = CCPFollower(c=None)
        msg = ccp._generate_move_CRM(0x00, counter)
        expected = b'\xff\x00\x76\x90\x90\x90\x90\x90'
        self.assertEqual(msg, expected)

    def test_generate_test_CRM(self):
        counter = 0x77
        ccp = CCPFollower(c=None)
        msg = ccp._generate_test_CRM(0x00, counter)
        expected = b'\xff\x00\x77\x90\x90\x90\x90\x90'
        self.assertEqual(msg, expected)

    def test_generate_exchangeID_CRM(self):
        counter = 0x78
        follower_device_id_length = 0x4
        data_type_qualifier = 0x2
        resource_availability_mask = 0x2
        resource_protection_mask = 0x1
        ccp = CCPFollower(c=None)
        msg = ccp._generate_exchangeID_CRM(0x00, counter, follower_device_id_length, data_type_qualifier,
                                           resource_availability_mask, resource_protection_mask)
        expected = b'\xff\x00\x78\x04\x02\x02\x01\x90'
        self.assertEqual(msg, expected)

    def test_generate_ccp_version_CRM(self):
        main_protocol = 2
        minor_protocol = 1
        counter = 0x79
        ccp = CCPFollower(c=None)
        msg = ccp._generate_ccp_version_CRM(0x00, counter, main_protocol, minor_protocol)
        expected = b'\xff\x00\x79\x02\x01\x90\x90\x90'
        self.assertEqual(msg, expected)

    def test_generate_get_seed_CRM(self):
        protection_status = 0x01
        counter = 0x80
        seed_data = 0xdeadbeef
        ccp = CCPFollower(c=None)
        msg = ccp._generate_get_seed_CRM(0x00, counter, protection_status, seed_data)
        expected = b'\xff\x00\x80\x01\xde\xad\xbe\xef'
        self.assertEqual(msg, expected)

    def test_generate_build_chksum_CRM(self):
        checksum_data_size = 4
        checksum_data = 0xdeadbeef
        counter = 0x81
        ccp = CCPFollower(c=None)
        msg = ccp._generate_build_chksum_CRM(0x00, counter, checksum_data_size, checksum_data)
        expected = b'\xff\x00\x81\x04\xde\xad\xbe\xef'
        self.assertEqual(msg, expected)

    def test_generate_unlock_CRM(self):
        resource_mask = 3
        counter = 0x82
        ccp = CCPFollower(c=None)
        msg = ccp._generate_unlock_CRM(0x00, counter, resource_mask)
        expected = b'\xff\x00\x82\x03\x90\x90\x90\x90'
        self.assertEqual(msg, expected)

    def test_generate_set_s_status_CRM(self):
        counter = 0x83
        ccp = CCPFollower(c=None)
        msg = ccp._generate_set_s_status_CRM(0x00, counter)
        expected = b'\xff\x00\x83\x90\x90\x90\x90\x90'
        self.assertEqual(msg, expected)

    def test_generate_get_s_status_CRM(self):
        session_status = 0x99
        addl_status_qual = 1
        counter = 0x84

        ccp = CCPFollower(c=None)
        msg = ccp._generate_get_s_status_CRM(0x00, counter, session_status, addl_status_qual)
        expected = b'\xff\x00\x84\x99\x01\x90\x90\x90'
        self.assertEqual(msg, expected)

    def test_generate_get_active_cal_page_CRM(self):
        counter = 0x85

        ccp = CCPFollower(c=None)

        address_ext = 0xb
        address = 0xdeadbeef

        expected = b'\xff\x00\x85\x0b\xde\xad\xbe\xef'
        msg = ccp._generate_get_active_cal_page_CRM(0x00, counter, address_ext, address)
        self.assertEqual(msg, expected)

    def test_generate_diag_service_CRM(self):
        counter = 0x86

        ccp = CCPFollower(c=None)

        return_len = 0x20
        data_type_qual = 0x00

        expected = b'\xff\x00\x86\x20\x00\x90\x90\x90'
        msg = ccp._generate_diag_service_CRM(0x00, counter, return_len, data_type_qual)
        self.assertEqual(msg, expected)

    def test_generate_action_service_CRM(self):
        counter = 0x87

        ccp = CCPFollower(c=None)

        return_len = 0x20
        data_type_qual = 0x00

        expected = b'\xff\x00\x87\x20\x00\x90\x90\x90'
        msg = ccp._generate_action_service_CRM(0x00, counter, return_len, data_type_qual)
        self.assertEqual(msg, expected)

    def test_generate_get_daq_size_CRM(self):
        counter = 0x88
        daq_list_size = 0x10
        first_pid = 0x08

        ccp = CCPFollower(c=None)
        expected = b'\xff\x00\x88\x10\x08\x90\x90\x90'
        msg = ccp._generate_get_daq_size_CRM(0x00, counter, daq_list_size, first_pid)
        self.assertEqual(msg, expected)

    def test_generate_select_cal_page_CRM(self):
        counter = 0x89

        ccp = CCPFollower(c=None)
        expected = b'\xff\x00\x89\x90\x90\x90\x90\x90'
        msg = ccp._generate_set_daq_ptr_CRM(0x00, counter)
        self.assertEqual(msg, expected)

    def test_generate_write_daq_CRM(self):
        counter = 0x8a

        ccp = CCPFollower(c=None)
        expected = b'\xff\x00\x8a\x90\x90\x90\x90\x90'
        msg = ccp._generate_write_daq_CRM(0x00, counter)
        self.assertEqual(msg, expected)

    def test_generate_start_stop_CRM(self):
        counter = 0x8b

        ccp = CCPFollower(c=None)
        expected = b'\xff\x00\x8b\x90\x90\x90\x90\x90'
        msg = ccp._generate_start_stop_CRM(0x00, counter)
        self.assertEqual(msg, expected)

    def test_generate_start_stop_all_CRM(self):
        counter = 0x8c

        ccp = CCPFollower(c=None)
        expected = b'\xff\x00\x8c\x90\x90\x90\x90\x90'
        msg = ccp._generate_start_stop_all_CRM(0x00, counter)
        self.assertEqual(msg, expected)
