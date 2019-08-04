# ECU class

import time

from cancat.uds import utils, UDS, SVC_SECURITY_ACCESS, NegativeResponseException 
from cancat.utils import log


class ScanClass(UDS):
    def __init__(self, c, tx_arbid, rx_arbid=None, verbose=True, extflag=0, timeout=3.0):
        super(ScanClass, self).__init__(c, tx_arbid, rx_arbid, verbose=verbose, extflag=extflag, timeout=timeout)

    def get_key(self, session=None, auth_lvl=None):
        # Placeholder function that can be replaced in a subclass to return 
        # a valid key that will be attempted during the auth scan.
        return ''

    def _key_from_seed(self, seed, secret):
        # As long as Scanning
        self.seed = {
            'secret': secret,
            'seed': seed,
            'key': '',
        }

        # For our dumb seed/key scanning purposes, just "send" the secret to the 
        # ECU.
        return secret

    def _do_Function(self, func, data=None, subfunc=None, service=None):
        # Special case to capture the final "key" being sent
        if func == SVC_SECURITY_ACCESS and data is not None:
            self.seed['key'] = data
        return super(ScanClass, self)._do_Function(func, data=data, subfunc=subfunc, service=service)


class ECU(object):
    # Add the kwargs param so we can construct an ECUAddress out of a dictionary 
    # that has extra stuff in it
    def __init__(self, c, addr, scancls=None, timeout=3.0, delay=None, sessions=None, **kwargs):
        self._addr = addr # (arb_id, resp_id, extflag)
        if scancls is None:
            self._scancls = ScanClass
        else:
            self._scancls = scancls
        self._timeout = timeout
        self._delay = delay
        self.c = c

        if sessions is not None:
            # TODO: probably need to validate/massage this object instead of 
            #       assuming it'll be correctly formatted?
            self._sessions = sessions
        else:
            self._sessions = {1: {'dids': {}}}

    def export(self):
        import collections
        data = collections.OrderedDict()
        data['tx_arbid'] = self._addr.tx_arbid
        data['rx_arbid'] = self._addr.rx_arbid
        data['extflag'] = self._addr.extflag
        data['sessions'] = self._sessions
        return data

    def did_read_scan(self, did_range, rescan=False):
        # Only do a scan if we don't already have data, unless rescan is set
        if not self._sessions[1]['dids'] or rescan:
            arb, resp, ext = self._addr
            log.msg('{} starting DID scan'.format(self._addr))
            # The DID scan is more reliable using the standard UDS timeout 
            # because of the length of time that block transfers can take
            u = self._scancls(self.c, arb, resp, extflag=ext, verbose=False, timeout=3.0)
            self._sessions[1]['dids'].update(utils.did_read_scan(u, did_range, delay=self._delay))

    def did_write_scan(self, did_range, rescan=False):
        # Only do a scan if we don't already have data, unless rescan is set
        if not self._sessions[1]['write_dids'] or rescan:
            # Attempt to write an empty array, which probably won't succeed?  
            # but if it does we're pretty screwed.
            arb, resp, ext = self._addr
            log.msg('{} starting DID write scan'.format(self._addr))
            u = self._scancls(self.c, arb, resp, extflag=ext, verbose=False, timeout=self._timeout)
            self._write_dids.update(utils.did_write_scan(u, did_range, b'', delay=self._delay))

    def session_scan(self, session_range, rescan=False, rescan_did_range=None, recursive_scan=True):
        arb, resp, ext = self._addr
        # Unfortunately session scanning (and the later DID scanning) is more 
        # reliable with the standard 3 second timeout
        u = self._scancls(self.c, arb, resp, extflag=ext, verbose=False, timeout=3.0)

        log.msg('{} starting session scan'.format(self._addr))

        # Only scan for new sessions if the session list consists only of session 1
        if len(self._sessions) == 1:
            new_sessions = utils.session_scan(u, session_range, delay=self._delay,
                    recursive_scan=recursive_scan)
            self._sessions.update(new_sessions)

        # For each session that was found, go through the list of DIDs and 
        # identify which DIDs can be read in this session
        for sess in self._sessions:
            if sess != 1 and 'resp' in self._sessions[sess] and (rescan or \
                    'dids' not in self._sessions[sess] or len(self._sessions[sess]['dids']) == 0):
                try:
                    with utils.new_session(u, sess, self._sessions[sess]['prereqs'], True):
                        log.debug('{} session {} ({}) re-reading DIDs'.format(
                            self._addr, sess, self._sessions[sess]['prereqs']))

                        self._sessions[sess]['dids'] = {}
                        # If rescan is set do a full DID scan instead of the short 
                        # scan of only existing DIDs
                        if rescan:
                            results = utils.did_read_scan(u, rescan_did_range, delay=self._delay)
                            self._sessions[sess]['dids'].update(results)
                        else:
                            valid_did_range = [d for d in self._sessions[1]['dids']]
                            results = utils.did_read_scan(u, valid_did_range, delay=self._delay)
                            self._sessions[sess]['dids'].update(results)
                except NegativeResponseException as e:
                    log.error('Failed to enter session {} ({}) to re-scan DIDs, try again later: {}'.format(
                        sess, self._sessions[sess]['prereqs'], e))

    def auth_scan(self, auth_range, rescan=False):
        arb, resp, ext = self._addr
        u = self._scancls(self.c, arb, resp, extflag=ext, verbose=False, timeout=self._timeout)
        u.StartTesterPresent(request_response=False)

        for sess in self._sessions:
            if sess != 1 and \
                    ('auth' not in self._sessions[sess] or \
                    len(self._sessions[sess]['auth']) == 0 or rescan):
                log.msg('{} session {} starting auth scan'.format(self._addr, sess))
                with utils.new_session(u, sess, self._sessions[sess]['prereqs'], True):
                    # Pass the get_key() function in the UDS scan class through
                    results = utils.auth_scan(u, auth_range,
                            lambda x: u.get_key(sess, x), delay=self._delay)

                    if 'auth' in self._sessions[sess]:
                        self._sessions[sess]['auth'].update(results)
                    else:
                        self._sessions[sess]['auth'] = results

    def _try_key(self, u, auth_level, key):
        resp = utils.try_auth(u, auth_level, key)
        if resp is not None and 'err' in resp:
            # Attempt to handle a few common errors
            if 'err' in resp and resp['err'] == 0x36:
                # 0x36:'ExceedNumberOfAttempts'
                log.detail('Retrying session {}, auth {}, length {}'.format(sess, lvl, keylen))
                resp = utils.try_auth(u, level, key)
                log.detail('resp: {}'.format(resp))

            elif 'err' in resp and resp['err'] == 0x37:
                # 0x37:'RequiredTimeDelayNotExpired'
                time.sleep(1.0)
                log.detail('Retrying session {}, auth {}, length {}'.format(sess, lvl, keylen))
                resp = utils.try_auth(u, level, key)
                log.detail('resp: {}'.format(resp))
        return resp

    def _found_key_len(self, sess, auth_level):
        # error 0x35 means that the key is invalid, which also means that the 
        # length is correct
        # 0x35:'InvalidKey'
        if 'resp' in self._sessions[sess]['auth'][auth_level] or \
                ('err' in self._sessions[sess]['auth'][auth_level] and \
                 self._sessions[sess]['auth'][auth_level]['err'] == 0x35):
            return True
        else:
            return False

    def key_length_scan(self, len_range, rescan=False):
        log.msg('{} starting key/seed length scan {}'.format(self._addr, len_range))
        self.c.placeCanBookmark('canmap key_length_scan({}, delay={})'.format(len_range, self._delay))

        arb, resp, ext = self._addr
        u = self._scancls(self.c, arb, resp, extflag=ext, verbose=False, timeout=self._timeout)
        u.StartTesterPresent(request_response=False)

        # I can't think of a good way to turn this into a more generic utility 
        # function
        for sess in self._sessions:
            # Skip session 1
            if sess == 1:
                continue

            with utils.new_session(u, sess, True):
                for lvl in self._sessions[sess]['auth']:
                    if not self._found_key_len(sess, lvl) or rescan:
                        # TODO: For now, we delete the old scan data, not sure how 
                        # best to track to new vs. old key key scans otherwise
                        self._sessions[sess]['auth'][lvl] = { 'seeds': [] }
                        log.msg('{} session {} auth {} starting key length scan'.format(self._addr, sess, lvl))
                        for keylen in len_range:
                            key = '\x00' * keylen
                            log.detail('Trying session {}, auth {}, key \'{}\''.format(sess, lvl, key))
                            self.c.placeCanBookmark('SecurityAccess({}, {})'.format(i, repr(key)))
                            resp = self._try_key(u, lvl, key)
                            self._sessions[sess]['auth'][lvl].update(resp)

                            self._sessions[sess]['auth'][lvl]['seeds'].append(dict(u.seed))

                            if 'resp' in resp:
                                # Get the key attempted from the recorded seed data 
                                # in case the scanning class modified it
                                log.msg('Session {}, auth {} key found! secret {} (seed {})'.format(
                                    sess, lvl, repr(u.seed['secret']), repr(u.seed['seed'])))
                                break
                            elif resp['err'] == 0x35:
                                log.debug('Session {}, auth {} length found! {} (seed {})'.format(
                                    sess, lvl, len(u.seed['secret']), repr(u.seed['seed'])))
                                break

        if self._delay:
            time.sleep(self._delay)

        # Ensure tester present is not being sent anymore
        u.StopTesterPresent()

    def memory_read_test(self):
        raise NotImplementedError()

    def data_transfer_test(self):
        raise NotImplementedError()
