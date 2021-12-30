# Utility functions for UDS

import time
import string
import struct
from contextlib import contextmanager

from cancat import uds
from cancat.uds import UDS
from cancat.utils import log
from cancat.utils.types import ECUAddress, _range_func


def get_uds_29bit_srcid(arbid):
    consts = uds.ARBID_CONSTS['29bit']
    return arbid & consts['srcid_mask']


def get_uds_29bit_destid(arbid):
    consts = uds.ARBID_CONSTS['29bit']
    return (arbid & consts['destid_mask']) >> consts['destid_shift']


def gen_uds_resp_range(arbid):
    if arbid > uds.ARBID_CONSTS['29bit']['prefix']:
        # Normally if a request is sent to 0x18DA01F1, the response should have
        # an arbitration ID of 0x18DAF101, but not all ECUs do things in
        # a "normal" way, so generate a range of possible response IDs.

        # The src from the request will be come the destination in the response
        dest_id = get_uds_29bit_srcid(arbid)
        base_id = uds.ARBID_CONSTS['29bit']['prefix'] & (dest_id << uds.ARBID_CONSTS['29bit']['destid_shift'])

        return _range_func(base_id, base_id + 0x100)
    else:
        # Assume this is an 11-bit request
        #
        # Normally if a request is sent to 0x710, the response should have an
        # arbitration ID of 0x718, but not all ECUs do things in a "normal" way,
        # so generate a range of possible response IDs.
        return _range_func(0x700, 0x800)


def gen_arbids(idx, ext=0):
    if ext:
        prefix = uds.ARBID_CONSTS['29bit']['prefix']
        tester = uds.ARBID_CONSTS['29bit']['tester']
        dest_shift = uds.ARBID_CONSTS['29bit']['destid_shift']

        arb_id = prefix + (idx << dest_shift) + tester
        resp_id = prefix + (tester << dest_shift) + idx
    else:
        prefix = uds.ARBID_CONSTS['11bit']['prefix']

        arb_id = prefix + idx
        resp_id = prefix + idx + uds.ARBID_CONSTS['11bit']['resp_offset']

    return (arb_id, resp_id)


def enter_session(u, session, prereq_sessions=None):
    # Enter any required preq sessions
    if prereq_sessions:
        for prereq in prereq_sessions:
            #u.DiagnosticSessionControl(prereq)
            enter_session(u, prereq)

    return u.DiagnosticSessionControl(session)

@contextmanager
def new_session(u, session, prereq_sessions=None, tester_present=False):
    try:
        # Enter any required preq sessions
        if prereq_sessions:
            for prereq in prereq_sessions:
                #u.DiagnosticSessionControl(prereq)
                enter_session(u, prereq)

        msg = u.DiagnosticSessionControl(session)

        # Start tester present again
        if tester_present:
            u.StartTesterPresent(request_response=False)

        yield msg
    finally:
        if tester_present:
            u.StopTesterPresent()


def find_possible_resp(u, start_index, tx_arbid, service, subfunction=None, timeout=3.0):
    # Starting at the supplied starting index, find the service request, and
    # then look for possible responses until the supplied timeout

    if subfunction:
        tx_match_bytes = struct.pack('>BH', service, subfunction)
        rx_match_bytes = struct.pack('>BH', service + 0x40, subfunction)
        match_len = 3
    else:
        tx_match_bytes = struct.pack('>B', service)
        rx_match_bytes = struct.pack('>B', service + 0x40)
        match_len = 1

    for idx, _, _, msg in u.c.genCanMsgs(start=start_index, arbids=[tx_arbid], maxsecs=timeout):
        ftype = msg[0] >> 4
        # Our Tx arbid is probably a 0, but check for frame type 1 as well.
        if (ftype == 0 and msg[1:1+match_len] == tx_match_bytes) or \
                (ftype == 1 and msg[2:2+match_len] == tx_match_bytes):
            tx_index = idx
            tx_msg = msg
            break
    else:
        # error case handling, if 0 messages are generated
        tx_index = 0
        tx_msg = None

    rx_range = gen_uds_resp_range(tx_arbid)
    err_match = struct.pack('>BB', uds.SVC_NEGATIVE_RESPONSE, service)

    for idx, _, arbid, msg in u.c.genCanMsgs(start=tx_index+1, arbids=rx_range, maxsecs=timeout):
        ftype = msg[0] >> 4
        # Check for frame types 0 (positive and negative responses) and 1
        if (ftype == 0 and msg[1:1+match_len] == rx_match_bytes) or \
                (ftype == 0 and msg[1:3] == err_match) or \
                (ftype == 1 and msg[2:2+match_len] == rx_match_bytes):
            return tx_msg, (arbid, msg)

    return tx_msg, None


def err_str(err):
    try:
        return uds.NEG_RESP_CODES.get(err)
    except IndexError:
        return 'ISOSAEReserved({})'.format(hex(err))


def did_str(did):
    name_str = uds.ISO_14229_DIDS.get(did)

    # Handle some generic DID ranges
    if name_str is None:
        if did in _range_func(0xf1a0, 0xf1ef+1):
            name_str = 'identificationOptionVehicleManufacturerSpecific'
        elif did in _range_func(0xf1f0, 0xf1ff+1):
            name_str = 'identificationOptionSystemSupplierSpecific'

    if name_str:
        return '{} ({})'.format(hex(did), name_str)
    else:
        return hex(did)


def ecu_did_scan(c, arb_id_range, ext=0, did=0xf190, udscls=None, timeout=3.0, delay=None, verbose_flag=False):
    scan_type = ''
    if ext:
        scan_type = ' ext'

    if udscls is None:
        udscls = UDS

    log.debug('Starting{} DID read ECU scan for range: {}'.format(scan_type, arb_id_range))
    c.placeCanBookmark('ecu_did_scan({}, ext={}, did={}, timeout={}, delay={})'.format(
        arb_id_range, ext, did, timeout, delay))
    ecus = []
    possible_ecus = []
    for i in arb_id_range:
        if ext and i == uds.ARBID_CONSTS['29bit']['tester']:
            # Skip i == 0xF1 because in that case the sender and receiver IDs
            # are the same
            log.detail('Skipping 0xF1 in ext ECU scan: invalid ECU address')
            continue
        elif ext == False and i > uds.ARBID_CONSTS['11bit']['max_req_id']:
            # For non-extended scans the valid range goes from 0x00 to 0xFF, but
            # stop the scan at 0xf7 because at that time the response is the
            # largest possible valid value
            log.detail('Stopping std ECU scan at 0xF7: last valid ECU address')
            break

        arb_id, resp_id = gen_arbids(i, ext)

        addr = ECUAddress(arb_id, resp_id, ext)

        u = udscls(c, addr.tx_arbid, addr.rx_arbid, extflag=addr.extflag,
                verbose=verbose_flag, timeout=timeout)
        log.detail('Trying {}'.format(addr))
        try:
            start_index = u.c.getCanMsgCount()
            msg = u.ReadDID(did)
            if msg is not None:
                log.debug('{} DID {}: {}'.format(addr, hex(did), repr(msg)))
                log.msg('found {}'.format(addr))

                ecus.append(addr)
            else:
                tx_msg, possible_match = find_possible_resp(u, start_index, arb_id,
                        uds.SVC_READ_DATA_BY_IDENTIFIER, did, timeout)
                if possible_match:
                    log.warn('Possible non-standard responses for {} found:'.format(addr))
                    rx_arbid, msg = possible_match
                    log.warn('{}: {}'.format(hex(rx_arbid), msg.hex()))
                    possible_ecus.append(ECUAddress(arb_id, rx_arbid, ext))
        except uds.NegativeResponseException as e:
            log.debug('{} DID {}: {}'.format(addr, hex(did), e))
            log.msg('found {}'.format(addr))

            # If a negative response happened, that means an ECU is present
            # to respond at this address.
            ecus.append(addr)

        if delay:
            time.sleep(delay)

    # Double check any non-standard responses that were found
    for addr in possible_ecus:
        u = udscls(c, addr.tx_arbid, addr.rx_arbid, extflag=addr.extflag,
                verbose=verbose_flag, timeout=timeout)
        log.detail('Trying {}'.format(addr))
        try:
            msg = u.ReadDID(did)
            if msg is not None:
                log.debug('{} DID {}: {}'.format(addr, hex(did), repr(msg)))
                log.msg('found {}'.format(addr))
                ecus.append(addr)
        except uds.NegativeResponseException as e:
            log.debug('{} DID {}: {}'.format(addr, hex(did), e))
            log.msg('found {}'.format(addr))

            # If a negative response happened, that means an ECU is present
            # to respond at this address.
            ecus.append(addr)

        if delay:
            time.sleep(delay)

    return ecus


def ecu_session_scan(c, arb_id_range, ext=0, session=1, udscls=None, timeout=3.0, delay=None, verbose_flag=False):
    scan_type = ''
    if ext:
        scan_type = ' ext'

    if udscls is None:
        udscls = UDS

    log.debug('Starting{} Session ECU scan for range: {}'.format(scan_type, arb_id_range))
    c.placeCanBookmark('ecu_session_scan({}, ext={}, session={}, timeout={}, delay={})'.format(
        arb_id_range, ext, session, timeout, delay))

    ecus = []
    possible_ecus = []
    for i in arb_id_range:
        if ext and i == uds.ARBID_CONSTS['29bit']['tester']:
            # Skip i == 0xF1 because in that case the sender and receiver IDs
            # are the same
            log.detail('Skipping 0xF1 in ext ECU scan: invalid ECU address')
            continue
        elif ext == False and i > uds.ARBID_CONSTS['11bit']['max_req_id']:
            # For non-extended scans the valid range goes from 0x00 to 0xFF, but
            # stop the scan at 0xf7 because at that time the response is the
            # largest possible valid value
            log.detail('Stopping std ECU scan at 0xF7: last valid ECU address')
            break

        arb_id, resp_id = gen_arbids(i, ext)

        addr = ECUAddress(arb_id, resp_id, ext)
        u = udscls(c, addr.tx_arbid, addr.rx_arbid, extflag=addr.extflag, verbose=verbose_flag, timeout=timeout)
        log.detail('Trying {}'.format(addr))
        try:
            start_index = u.c.getCanMsgCount()
            with new_session(u, session) as msg:
                if msg is not None:
                    log.debug('{} session {}: {}'.format(addr, session, repr(msg)))
                    log.msg('found {}'.format(addr))

                    ecus.append(addr)
                else:
                    tx_msg, responses = find_possible_resp(u, start_index, arb_id,
                            uds.SVC_DIAGNOSTICS_SESSION_CONTROL, session, timeout)
                    if responses:
                        log.warn('Possible non-standard responses for {} found:'.format(addr))
                        rx_arbid, msg = possible_match
                        log.warn('{}: {}'.format(hex(rx_arbid), msg.hex()))
                        possible_ecus.append(ECUAddress(arb_id, rx_arbid, ext))
        except uds.NegativeResponseException as e:
            log.debug('{} session {}: {}'.format(addr, session, e))
            log.msg('found {}'.format(addr))

            # If a negative response happened, that means an ECU is present
            # to respond at this address.
            ecus.append(addr)

        if delay:
            time.sleep(delay)

    # Double check any non-standard responses that were found
    for addr in possible_ecus:
        u = udscls(c, addr.tx_arbid, addr.rx_arbid, extflag=addr.extflag,
                verbose=verbose_flag, timeout=timeout)
        log.detail('Trying {}'.format(addr))
        try:
            with new_session(u, sess) as msg:
                if msg is not None:
                    log.debug('{} session {}: {}'.format(addr, sess, repr(msg)))
                    log.msg('found {}'.format(addr))
                    ecus.append(addr)
        except uds.NegativeResponseException as e:
            log.debug('{} session {}: {}'.format(addr, sess, e))
            log.msg('found {}'.format(addr))

            # If a negative response happened, that means an ECU is present
            # to respond at this address.
            ecus.append(addr)

        if delay:
            time.sleep(delay)

    return ecus


def try_read_did(u, did):
    data = None
    try:
        resp = u.ReadDID(did)
        if resp is not None:
            data = { 'resp':resp }
    except uds.NegativeResponseException as e:
        # 0x12:'SubFunctionNotSupported' - not standard, but I've seen it
        # 0x31:'RequestOutOfRange'       - means the DID is not valid
        if e.neg_code not in [0x12, 0x31]:
            data = { 'err':e.neg_code }
    return data


def did_read_scan(u, did_range, delay=None):
    log.debug('Starting DID read scan for range: {}'.format(did_range))
    u.c.placeCanBookmark('did_read_scan({}, delay={})'.format(did_range, delay))
    dids = {}
    for i in did_range:
        log.detail('Trying DID read {}'.format(hex(i)))
        u.c.placeCanBookmark('ReadDID({})'.format(hex(i)))
        resp = try_read_did(u, i)

        if resp is not None:
            log.debug('DID {}: {}'.format(hex(i), resp))
            if 'resp' in resp:
                printable_did = ''.join([x if x in string.printable else '' for x in resp['resp'][3:]])
                log.msg('DID {}: {} ({})'.format(did_str(i), resp['resp'], printable_did))
            else:
                log.msg('DID {}: ERR {}'.format(did_str(i), err_str(resp['err'])))
            dids[i] = resp

        if delay:
            time.sleep(delay)

    return dids


def try_write_did(u, did, datg):
    did = None
    try:
        resp = u.WriteDID(i, data)
        if resp is not None:
            did = { 'resp':resp }
    except uds.NegativeResponseException as e:
        # 0x31:'RequestOutOfRange' usually means the DID is not valid
        if e.neg_code != 0x31:
            did = { 'err':e.neg_code }
    return did


def did_write_scan(u, did_range, write_data, delay=None):
    log.debug('Starting DID write scan for range: {}'.format(did_range))
    u.c.placeCanBookmark('did_write_scan({}, write_data={}, delay={})'.format(did_range, write_data, delay))
    dids = {}
    for i in did_range:
        log.detail('Trying DID write {}'.format(hex(i)))
        u.c.placeCanBookmark('WriteDID({})'.format(hex(i)))
        resp = try_write_did(u, i, write_data)
        if resp is not None:
            log.detail('DID {}: {}'.format(hex(i), resp))
            if 'resp' in resp:
                log.msg('DID {}: {}'.format(did_str(i), resp['resp'].hex()))
            else:
                log.msg('DID {}: {}'.format(did_str(i), err_str(resp['err'])))
            dids[i] = resp

        if delay:
            time.sleep(delay)

    return dids


def try_session(u, sess_num):
    session = None
    try:
        with new_session(u, sess_num) as resp:
            if resp is not None:
                session = { 'resp':resp }
    except uds.NegativeResponseException as e:
        # 0x11:'ServiceNotSupported'
        # 0x12:'SubFunctionNotSupported'
        if e.neg_code not in [0x11, 0x12]:
            session = { 'err':e.neg_code }
    return session

def try_session_scan(u, session_range, prereq_sessions, found_sessions, delay=None, recursive_scan=True, try_ecu_reset=True, try_sess_ctrl_reset=True):
    log.debug('Starting session scan for range: {}'.format(session_range))
    u.c.placeCanBookmark('session_scan({}, delay={})'.format(session_range, delay))
    sessions = {}
    for i in session_range:
        # If this session matches any one of the prereqs, or one of the
        # sessions already found, skip it
        if i in prereq_sessions or i in found_sessions:
            continue

        log.detail('Trying session {}'.format(i))
        u.c.placeCanBookmark('DiagnosticSessionControl({})'.format(i))

        # Enter any required preq sessions
        try:
            for prereq in prereq_sessions:
                enter_session(u, prereq)
        except uds.NegativeResponseException as e:
            # 0x7f:'ServiceNotSupportedInActiveSession'
            if e.neg_code == 0x7f:
                log.detail('SESSION ({}): Can\'t enter prereqs, stopping session scan'.format(prereq_sessions))
                return sessions
            else:
                raise e

        resp = try_session(u, i)
        if resp is not None:
            resp['prereqs'] = list(prereq_sessions)
            log.debug('session {}: {}'.format(i, resp))
            if 'resp' in resp:
                log.msg('SESSION {}: {} ({})'.format(i, resp['resp'].hex(), prereq_sessions))
            else:
                log.msg('SESSION {}: {} ({})'.format(i, err_str(resp['err']), prereq_sessions))
            sessions[i] = resp

        # Only bother with this if a successful response was received
        if resp and 'resp' in resp:
            if try_ecu_reset:
                try:
                    u.EcuReset()

                    # Small delay to allow for the reset to complete
                    time.sleep(0.2)
                except uds.NegativeResponseException as e:
                    # 0x11:'ServiceNotSupported'
                    # 0x22:'ConditionsNotCorrect'
                    if e.neg_code in [0x11, 0x22]:
                        try_ecu_reset = False
            elif try_sess_ctrl_reset:
                try:
                    # Try just changing back to session 1
                    new_session(u, 1)
                except uds.NegativeResponseException as e:
                    # The default method to try returning to session 1 is EcuReset, if
                    # EcuReset doesn't work (or isn't enabled), then try using the
                    # DiagnosticSessionControl message to return to session 1, if that
                    # doesn't work then we can't attempt recursive session scanning
                    try_sess_ctrl_reset = False

        # Extra delay between attempts if configured
        if delay:
            time.sleep(delay)

    # For each session found re-scan for new sessions that can be entered from
    # those, but only if we have a valid reset method:
    if recursive_scan and (try_ecu_reset or try_sess_ctrl_reset):
        subsessions = {}
        for sess in sessions:
            # Only attempt this with sessions that we got a successful response
            # for
            if 'msg' in sessions[sess]:
                log.debug('Scanning for sessions from session {} ({})'.format(sess, prereq_sessions))
                prereqs = prereq_sessions + [sess]
                subsessions.update(try_session_scan(u, session_range, prereqs, sessions.keys(),
                    delay=delay, recursive_scan=recursive_scan,
                    try_ecu_reset=try_ecu_reset, try_sess_ctrl_reset=try_sess_ctrl_reset))
        sessions.update(subsessions)

    return sessions


def session_scan(u, session_range, delay=None, recursive_scan=True):
    prereq_sessions = []
    session_results = try_session_scan(u, session_range, prereq_sessions, [], delay, recursive_scan)
    return session_results


def try_auth(u, level, secret):
    auth_data = None
    try:
        resp = u.SecurityAccess(level, secret)
        if resp is not None:
            auth_data = { 'resp':resp }
    except uds.NegativeResponseException as e:
        # 0x12:'SubFunctionNotSupported',
        if e.neg_code != 0x12:
            auth_data = { 'err':e.neg_code }
    return auth_data


def auth_scan(u, auth_range, key_func=None, delay=None):
    log.debug('Starting auth scan for range: {}'.format(auth_range))
    u.c.placeCanBookmark('auth_scan({}, key_func={}, delay={})'.format(auth_range, key_func, delay))
    auth_levels = {}
    for i in auth_range:
        if key_func:
            secret = ''
        else:
            secret = key_func(i)

        log.detail('Trying auth level {}: secret \'{}\''.format(i, secret))
        u.c.placeCanBookmark('SecurityAccess({}, {})'.format(i, repr(secret)))

        resp = try_auth(u, i, secret)
        if resp is not None:
            log.debug('auth {}: {}'.format(i, resp))
            if 'resp' in resp:
                log.msg('SECURITY {}: {}'.format(i, resp['resp'].hex()))
            else:
                log.msg('SECURITY {}: {}'.format(i, err_str(resp['err'])))
            auth_levels[i] = resp

        if delay:
            time.sleep(delay)

    return auth_levels
