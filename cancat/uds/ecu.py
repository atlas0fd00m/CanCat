# ECU class

import time
import cancat.uds
import cancat.uds.utils
from cancat.utils import log


class ScanClass(cancat.uds.UDS):
    def __init__(self, c, tx_arbid, rx_arbid=None, verbose=True, extflag=0, timeout=3.0):
        super(ScanClass, self).__init__(c, tx_arbid, rx_arbid, verbose=verbose, extflag=extflag, timeout=3.0)
        # Collect all the seeds!
        self.clear_saved_seeds()

    def clear_saved_seeds(self):
        self.seeds = {}
        self.current_level = 1
        self.current_try = None

    def SecurityAccess(self, level, *args, **kwargs):
        self.current_level = level
        super(ScanClass, self).SecurityAccess(*args, **kwargs)

    def _key_from_seed(self, seed, secret):
        # Save the seed, this will be useful for our analysis later
        #self.current_try = (self.current_level, secret, seed)
        if self.current_level in self.seeds:
            self.seeds[self.current_level].append((secret, seed))
        else:
            self.seeds[self.current_level] = [(secret, seed)]

        # For our dumb seed/key scanning purposes, just send the secret to the 
        # ECU.
        return secret


class ECU(object):
    def __init__(self, c, addr, uds_class=ScanClass, timeout=3.0, init_data=None):
        # TODO: turn addr into it's own class/object/type
        #       make sure the str/repr is shown in hex
        self._addr = addr # (arb_id, resp_id, extflag)
        self._uds = uds_class
        self._timeout = timeout
        self.c = c

        if init_data is not None:
            # TODO: probably need to validate/massage this object instead of 
            #       assuming it'll be correctly formatted?
            self._sessions = init_data
        else:
            self._sessions = {1: {'dids': {}}}

    def export(self):
        return {'sessions': self._sessions}

    def did_read_scan(self, did_range, rescan=False):
        # Only do a scan if we don't already have data, unless rescan is set
        if not self._sessions[1]['dids'] or rescan:
            arb, resp, ext = self._addr
            u = self._uds(self.c, arb, resp, extflag=ext, verbose=False, timeout=self._timeout)
            self._sessions[1]['dids'].update(cancat.uds.utils.did_read_scan(u, did_range))

    def did_write_scan(self, did_range, rescan=False):
        # Only do a scan if we don't already have data, unless rescan is set
        if not self._sessions[1]['write_dids'] or rescan:
            # Attempt to write an empty array, which probably won't succeed?  
            # but if it does we're pretty screwed.
            arb, resp, ext = self._addr
            u = self._uds(self.c, arb, resp, extflag=ext, verbose=False)
            self._write_dids.update(cancat.uds.utils.did_write_scan(u, did_range, b''))

    def session_scan(self, session_range, rescan=False):
        # Only do a scan if this ECU only has info for session 1 (the default 
        # sssion)
        if len(self._sessions[1]) == 1 or rescan:
            arb, resp, ext = self._addr
            u = self._uds(self.c, arb, resp, extflag=ext, verbose=False)
            self._sessions[sess].update(cancat.uds.utils.session_scan(u, session_range))

            # For each session that was found, go through the list of DIDs and 
            # identify which DIDs can be read in this session
            #
            # TODO: generalize this part of this function so it can be called 
            #   from others?
            for sess in new_sessions:
                if 'resp' in self._sessions[sess]:
                    u.DiagnosticSessionControl(sess)
                    u.StartTesterPresent(request_response=False)
                    log.debug('ECU {} session {} retrying DIDs with errors'.format(self._addr, sess))

                    self._sessions[sess]['dids'] = {}
                    for did in self._dids:
                        log.detail('Trying DID {}'.format(hex(did)))
                        resp = try_read_did(u, did)
                        if resp is not None:
                            log.msg('DID {}: {}'.format(hex(did), resp))
                            self._sessions[sess]['dids'][did] = resp
                    
                    u.StopTesterPresent()

    def auth_scan(self, auth_range, rescan=False):
        # TODO: add rescan check and review debug msgs
        arb, resp, ext = self._addr
        u = self._uds(self.c, arb, resp, extflag=ext, verbose=False)
        for sess in self._sessions:
            # Clear out the seed/key collection dictionary before starting 
            # the scan
            u.seeds = {}
            u.DiagnosticSessionControl(sess)
            u.StartTesterPresent(request_response=False)
            self._sessions[sess]['auth'] = cancat.uds.utils.auth_scan(u, auth_range)
            for lvl in self._sessions[sess]['auth']:
                # Some of the auth attempts may have error-ed out on on the 
                # seed request message, some may have error-ed out when 
                # sending a key, if the first happened there won't be 
                # a recorded seed
                if lvl in u.seeds:
                    if 'seeds' in self._sessions[sess]['auth'][lvl]:
                        self._sessions[sess]['auth'][lvl]['seeds'].extend(u.seeds[lvl])
                    else:
                        self._sessions[sess]['auth'][lvl]['seeds'] = u.seeds[lvl]

    def _try_key_len(self, auth_level):
        for keylen in len_range:
            # Keep checking this
            if 'msg' in level or level['err'].neg_code == 0x35:
                return
            # Only do a key length scan if we don't already know the right 
            # length
            #
            # error 0x35 means that the key is invalid, which also 
            # means that the length is correct
            # 0x35:'InvalidKey'
            else:
                log.debug('Trying session {}, auth {}, length {}'.format(sess, lvl, keylen))
                resp = cancat.uds.utils.try_auth(u, level, key)
                log.debug('resp: {}'.format(resp))
                if resp is not None and 'err' in resp:
                    # Attempt to handle a few errors
                    if 'err' in resp and resp['err'].neg_code == 0x36:
                        # 0x36:'ExceedNumberOfAttempts'
                        log.debug('Retrying session {}, auth {}, length {}'.format(sess, lvl, keylen))
                        resp = cancat.uds.utils.try_auth(u, level, key)
                        log.debug('resp: {}'.format(resp))

                    elif 'err' in resp and resp['err'].neg_code == 0x37:
                        # 0x37:'RequiredTimeDelayNotExpired'
                        time.sleep(1.0)
                        log.debug('Retrying session {}, auth {}, length {}'.format(sess, lvl, keylen))
                        resp = cancat.uds.utils.try_auth(u, level, key)
                        log.debug('resp: {}'.format(resp))

                if resp is not None:
                    if 'msg' in resp:
                        level['msg'] = resp['msg']
                        del level['err']
                    else:
                        level['err'] = resp['err']

    def key_length_scan(self, len_range, rescan=False):
        # TODO: add rescan check and review debug msgs
        arb, resp, ext = self._addr
        log.debug('Starting key/seed length scan for range: {}'.format(len_range))
        u = self._uds(self.c, arb, resp, extflag=ext, verbose=False)
        for sess in self._sessions:
            # Clear out the seed/key collection dictionary before starting 
            # the scan
            u.seeds = {}
            u.DiagnosticSessionControl(sess)
            u.StartTesterPresent(request_response=False)
            for lvl in self._sessions[sess]['auth']:
                log.debug('Starting key length scan for session {} auth {}'.format(sess, lvl))
                level = self._sessions[sess]['auth'][lvl]
                self._try_key_len(level)

                if 'msg' in level:
                    log.debug('Session {}, auth {} length found! secret: {}, key {}'.format(
                        level['seeds'][-1][0], level['seeds'][-1][1]))
                elif level['err'].neg_code == 0x35:
                    log.debug('Session {}, auth {} length found: {} seed: {}'.format(
                        len(level['seeds'][-1][0]), level['seeds'][-1][1]))

                if lvl in u.seeds:
                    level['seeds'].extend(u.seeds[lvl])

    def memory_read_test(self):
        raise NotImplementedError()

    def data_transfer_test(self):
        raise NotImplementedError()
