# Utility functions for UDS

import cancat.uds
from cancat.uds.types import ECUAddress
from cancat.utils import log


_UDS_CLASS = cancat.uds.UDS


def ecu_did_scan(c, arb_id_range, ext=0, did=0xf190, verbose_flag=False):
    scan_type = ''
    if ext:
        scan_type = ' ext'

    log.debug('Starting{} ECU scan for range: {}'.format(scan_type, arb_id_range))
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

        global _UDS_CLASS 
        log.log(log.FIXME, (c, dict(verbose=verbose_flag, **addr)))
        u = _UDS_CLASS(c, addr.tx_arbid, addr.rx_arbid, extflag=addr.extflag, verbose=verbose_flag)
        log.detail('Trying ECU {}'.format(addr))
        try:
            msg = u.ReadDID(did)
            if msg is not None:
                log.debug('ECU {} DID {}: {}'.format(addr, hex(did), msg))
                log.msg('found ECU: {}'.format(addr))

                ecus.append(addr)
        except cancat.uds.NegativeResponseException as e:
            log.debug('ECU {} DID {}: {}'.format(addr, hex(did), e))
            log.msg('found ECU: {}'.format(addr))

            # If a negative response happened, that means an ECU is present 
            # to respond at this address.
            ecus.append(addr)

    return ecus


def ecu_session_scan(c, arb_id_range, ext=0, session=1, verbose_flag=False):
    ecus = []
    for i in arb_id_range:  
        if ext and i == 0xF1:
            # Skip i == 0xF1 because in that case the sender and receiver IDs 
            # are the same
            print 'continue!'
            continue
        elif ext == False and i >= 0xF8:
            # For non-extended scans the valid range goes from 0x00 to 0xFF, but 
            # stop the scan at 0xF7 because at that time the response is the 
            # largest possible valid value
            print 'break!'
            break
        elif ext:
            arb_id = 0x18db00f1 + (i << 8)
            resp_id = 0x18dbf100 + i
        else:
            arb_id = 0x700 + i
            resp_id = 0x700 + i + 8

        addr = ECUAddress(arb_id, resp_id, ext)
        global _UDS_CLASS 
        log.log(log.FIXME, (c, dict(verbose=verbose_flag, **addr)))
        u = _UDS_CLASS(c, addr.tx_arbid, addr.rx_arbid, extflag=addr.extflag, verbose=verbose_flag)
        log.detail('Trying ECU {}'.format(addr))
        try:
            msg = u.DiagnosticSessionControl(did)
            if msg is not None:
                log.debug('ECU {} session {}: {}'.format(addr, session, msg))
                log.msg('found ECU: {}'.format(addr))

                ecus.append(addr)
        except cancat.uds.NegativeResponseException as e:
            log.debug('ECU {} session {}: {}'.format(addr, session, e))
            log.msg('found ECU: {}'.format(addr))

            # If a negative response happened, that means an ECU is present 
            # to respond at this address.
            ecus.append(addr)

    return ecus


def try_read_did(u, did):
    data = None
    try:
        resp = u.ReadDID(did)
        if resp is not None:
            data = { 'resp':resp }
    except cancat.uds.NegativeResponseException as e:
        # 0x31:'RequestOutOfRange' usually means the DID is not valid
        if e.neg_code != 0x31:
            data = { 'err':e }
    return data


def did_read_scan(u, did_range):
    log.debug('Starting DID read scan for range: {}'.format(did_range))
    dids = {}
    for i in did_range:  
        log.detail('Trying DID {}'.format(hex(i)))
        resp = try_read_did(u, i)
        if resp is not None:
            dids[i] = resp
            log.msg('DID {}: {}'.format(hex(i), resp))
    return dids


def try_write_did(u, did, datg):
    did = None
    try:
        resp = u.WriteDID(i, data)
        if resp is not None:
            did = { 'resp':resp }
    except cancat.uds.NegativeResponseException as e:
        # 0x31:'RequestOutOfRange' usually means the DID is not valid
        if e.neg_code != 0x31:
            did = { 'err':e }
    return did


def did_write_scan(u, did_range, write_data):
    log.debug('Starting DID write scan for range: {}'.format(did_range))
    dids = {}
    for i in did_range:  
        log.detail('Trying DID {}'.format(hex(i)))
        resp = try_write_did(u, i, write_data)
        if resp is not None:
            dids[i] = resp
            log.msg('DID {}: {}'.format(hex(i), resp))
    return dids


def try_session(u, sess_num):
    session = None
    try:
        resp = u.DiagnosticSessionControl(sess_num)
        if resp is not None:
            session = { 'resp':resp }
    except cancat.uds.NegativeResponseException as e:
        # 0x12:'SubFunctionNotSupported',
        if e.neg_code != 0x12:
            session = { 'err':e }
    return session


def session_scan(u, session_range):
    log.debug('Starting session scan for range: {}'.format(session_range))
    sessions = {}
    for i in session_range:  
        log.detail('Trying session {}'.format(i))
        resp = try_session(u, i)
        if resp is not None:
            sessions[i] = resp
            log.msg('session {}: {}'.format(hex(i), resp))
    return sessions


def try_auth(u, level, key):
    auth_data = None
    try:
        resp = u.SecurityAccess(level, key)
        if resp is not None:
            auth_data = { 'resp':resp }
    except cancat.uds.NegativeResponseException as e:
        # 0x12:'SubFunctionNotSupported',
        if e.neg_code != 0x12:
            resp = { 'err':e }
    return resp


def auth_scan(u, auth_range):
    log.debug('Starting auth scan for range: {}'.format(auth_range))
    auth_levels = {}
    for i in auth_range:  
        log.detail('Trying auth level {}'.format(i))
        resp = try_auth(u, i, b'')
        if resp is not None:
            auth_levels[i] = resp
            log.msg('auth {}: {}'.format(hex(i), resp))
    return auth_levels
