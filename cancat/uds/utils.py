# Utility functions for UDS

import time
import string
from contextlib import contextmanager
from cancat.uds import NegativeResponseException, NEG_RESP_CODES, UDS
from cancat.uds.types import ECUAddress
from cancat.utils import log

def enter_session(u, session, prereq_sessions=None):
    # Enter any required preq sessions
    if prereq_sessions:
        for prereq in prereq_sessions:
            #u.DiagnosticSessionControl(prereq)
            enter_session(u, prereq)

    msg = None
    # Handle 0x7f:'ServiceNotSupportedInActiveSession' errors
    for i in range(30):
        try:
            msg = u.DiagnosticSessionControl(session)
            break
        except NegativeResponseException as e:
            if e.neg_code != 0x7f:
                raise e

        # Wait until 
        time.sleep(0.1)

    return msg

@contextmanager
def new_session(u, session, prereq_sessions=None, tester_present=False):
    try:
        # Enter any required preq sessions
        if prereq_sessions:
            for prereq in prereq_sessions:
                #u.DiagnosticSessionControl(prereq)
                enter_session(u, prereq)

        msg = None
        # Handle 0x7f:'ServiceNotSupportedInActiveSession' errors
        for i in range(30):
            try:
                msg = u.DiagnosticSessionControl(session)
                break
            except NegativeResponseException as e:
                if e.neg_code != 0x7f:
                    raise e

            # Wait until 
            time.sleep(0.1)

        # Start tester present again
        if tester_present:
            u.StartTesterPresent(request_response=False)

        yield msg
    finally:
        if tester_present:
            u.StopTesterPresent()


def ecu_did_scan(c, udsclass, arb_id_range, ext=0, did=0xf190, timeout=3.0, delay=None, verbose_flag=False):
    scan_type = ''
    if ext:
        scan_type = ' ext'

    log.debug('Starting{} DID read ECU scan for range: {}'.format(scan_type, arb_id_range))
    c.placeCanBookmark('ecu_did_scan({}, ext={}, did={}, timeout={}, delay={})'.format(
        arb_id_range, ext, did, timeout, delay))
    ecus = []
    for i in arb_id_range:  
        if ext and i == 0xF1:
            # Skip i == 0xF1 because in that case the sender and receiver IDs 
            # are the same
            log.detail('Skipping 0xF1 on ext ECU scan: invalid ECU address')
            continue
        elif ext == False and i >= 0xF8:
            # For non-extended scans the valid range goes from 0x00 to 0xFF, but 
            # stop the scan at 0xF7 because at that time the response is the 
            # largest possible valid value
            log.detail('Stopping std ECU scan at 0xF7: last valid ECU address')
            break
        elif ext:
            arb_id = 0x18db00f1 + (i << 8)
            resp_id = 0x18dbf100 + i
        else:
            arb_id = 0x700 + i
            resp_id = 0x700 + i + 8

        addr = ECUAddress(arb_id, resp_id, ext)

        u = udsclass(c, addr.tx_arbid, addr.rx_arbid, extflag=addr.extflag, verbose=verbose_flag, timeout=timeout)
        log.detail('Trying {}'.format(addr))
        try:
            msg = u.ReadDID(did)
            if msg is not None:
                log.debug('{} DID {}: {}'.format(addr, hex(did), repr(msg)))
                log.msg('found {}'.format(addr))

                ecus.append(addr)
        except NegativeResponseException as e:
            log.debug('{} DID {}: {}'.format(addr, hex(did), e))
            log.msg('found {}'.format(addr))

            # If a negative response happened, that means an ECU is present 
            # to respond at this address.
            ecus.append(addr)

        if delay:
            time.sleep(delay)

    return ecus


def ecu_session_scan(c, udsclass, arb_id_range, ext=0, session=1, verbose_flag=False, timeout=3.0, delay=None):
    scan_type = ''
    if ext:
        scan_type = ' ext'

    log.debug('Starting{} Session ECU scan for range: {}'.format(scan_type, arb_id_range))
    c.placeCanBookmark('ecu_session_scan({}, ext={}, session={}, timeout={}, delay={})'.format(
        arb_id_range, ext, session, timeout, delay))

    ecus = []
    for i in arb_id_range:  
        if ext and i == 0xF1:
            # Skip i == 0xF1 because in that case the sender and receiver IDs 
            # are the same
            continue
        elif ext == False and i >= 0xF8:
            # For non-extended scans the valid range goes from 0x00 to 0xFF, but 
            # stop the scan at 0xF7 because at that time the response is the 
            # largest possible valid value
            break
        elif ext:
            arb_id = 0x18db00f1 + (i << 8)
            resp_id = 0x18dbf100 + i
        else:
            arb_id = 0x700 + i
            resp_id = 0x700 + i + 8

        addr = ECUAddress(arb_id, resp_id, ext)
        u = udsclass(c, addr.tx_arbid, addr.rx_arbid, extflag=addr.extflag, verbose=verbose_flag, timeout=timeout)
        log.detail('Trying {}'.format(addr))
        try:
            with new_session(u, sess) as msg:
                if msg is not None:
                    log.debug('{} session {}: {}'.format(addr, session, repr(msg)))
                    log.msg('found {}'.format(addr))

                    ecus.append(addr)
        except NegativeResponseException as e:
            log.debug('{} session {}: {}'.format(addr, session, e))
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
    except NegativeResponseException as e:
        # 0x31:'RequestOutOfRange' usually means the DID is not valid
        if e.neg_code != 0x31:
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
                log.msg('DID {}: {} ({})'.format(hex(i), resp['resp'].encode('hex'), printable_did))
            else:
                log.msg('DID {}: {}'.format(hex(i), NEG_RESP_CODES.get(resp['err'])))
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
    except NegativeResponseException as e:
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
            log.msg('DID {}: {}'.format(hex(i), resp))
            if 'resp' in resp:
                log.msg('DID {}: {}'.format(hex(i), resp['resp'].encode('hex')))
            else:
                log.msg('DID {}: {}'.format(hex(i), NEG_RESP_CODES.get(resp['err'])))
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
    except NegativeResponseException as e:
        # 0x12:'SubFunctionNotSupported',
        if e.neg_code != 0x12:
            session = { 'err':e.neg_code }
    return session

def try_session_scan(u, session_range, prereq_sessions, delay=None, try_ecu_reset=True, try_sess_ctrl_reset=True):
    log.debug('Starting session scan for range: {}'.format(session_range))
    u.c.placeCanBookmark('session_scan({}, delay={})'.format(session_range, delay))
    sessions = {}
    for i in session_range:  
        # If this session matches any one of the prereqs, skip it
        if i in prereq_sessions:
            continue

        log.detail('Trying session {}'.format(i))
        u.c.placeCanBookmark('DiagnosticSessionControl({})'.format(i))

        # Enter any required preq sessions
        for prereq in prereq_sessions:
            new_session(u, prereq)

        resp = try_session(u, i)
        if resp is not None:
            resp['prereqs'] = prereq_sessions
            log.debug('session {}: {}'.format(i, resp))
            if 'resp' in resp:
                log.msg('SESSION {}: {} ({})'.format(i, resp['resp'].encode('hex'), prereq_sessions))
            else:
                log.msg('SESSION {}: {} ({})'.format(i, NEG_RESP_CODES.get(resp['err'], prereq_sessions)))
            sessions[i] = resp

        if try_ecu_reset:
            try:
                u.EcuReset()

                # Small delay to allow for the reset to complete
                time.sleep(0.2)
            except NegativeResponseException as e:
                # 0x22:'ConditionsNotCorrect'
                if e.neg_code == 0x22:
                    try_ecu_reset = False
        elif try_sess_ctrl_reset:
            # Try just changing back to session 1
            new_session(u, 1)
            #except NegativeResponseException as e:
            #   # The default method to try returning to session 1 is EcuReset, if
            #   # EcuReset doesn't work (or isn't enabled), then try using the
            #   # DiagnosticSessionControl message to return to session 1, if that
            #   # doesn't work then we can't attempt recursive session scanning

        # Extra delay if configured
        if delay:
            time.sleep(delay)

    # For each session found re-scan for new sessions that can be entered from those, but only if we have a valid reset method:
    if try_ecu_reset or try_sess_ctrl_reset:
        subsessions = {}
        for sess in sessions:
            log.debug('Scanning for sessions from session {} ({})'.format(sess, prereq_sessions))
            prereqs = prereq_sessions + [sess]
            subsessions.update(try_session_scan(u, session_range, prereqs, delay=delay,
                    try_ecu_reset=try_ecu_reset, try_sess_ctrl_reset=try_sess_ctrl_reset))
        sessions.update(subsessions)

    return sessions


def session_scan(u, session_range, delay=None):
    prereq_sessions = []
    session_results = try_session_scan(u, session_range, prereq_sessions, delay)
    return session_results


def try_auth(u, level, key):
    auth_data = None
    try:
        resp = u.SecurityAccess(level, key)
        if resp is not None:
            auth_data = { 'resp':resp }
    except NegativeResponseException as e:
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
            key = ''
        else:
            key = key_func(i)

        log.detail('Trying auth level {}: key \'{}\''.format(i, key))
        u.c.placeCanBookmark('SecurityAccess({}, {})'.format(i, repr(key)))

        resp = try_auth(u, i, key)
        if resp is not None:
            log.debug('auth {}: {}'.format(i, resp))
            if 'resp' in resp:
                log.msg('SECURITY {}: {}'.format(i, resp['resp'].encode('hex')))
            else:
                log.msg('SECURITY {}: {}'.format(i, NEG_RESP_CODES.get(resp['err'])))
            auth_levels[i] = resp

        if delay:
            time.sleep(delay)

    return auth_levels
