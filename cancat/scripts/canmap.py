# CAN bus device mapping tool
from __future__ import print_function

import sys
import argparse
import re
import time
import signal
import importlib
import traceback

import cancat
from cancat.utils.types import SparseHexRange, ECUAddress
from cancat.utils import log
from cancat.uds.ecu import ECU
from cancat.uds.utils import ecu_did_scan, ecu_session_scan

c = None
_config = None
_output_filename = None
_can_session_filename = None


def now():
    # return an ISO 8601 formatted date string
    # 2019-07-18T02:28:16+00:00
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


class ECURange(SparseHexRange):
    def __new__(cls, val):
        # Ensure that values are <= than 0xFF (255)
        if any(int(n, 16) > 0xFF for n in re.findall(r'[A-Za-z0-9]+', val)):
            raise ValueError('range {} exceeds max ECU addr of 0xFF'.format(val))
        return super(ECURange, cls).__new__(cls, val)


class DIDRange(SparseHexRange):
    def __new__(cls, val):
        # Ensure that values are <= than 0xFFFF (65535)
        if any(int(n, 16) > 0xFFFF for n in re.findall(r'[A-Za-z0-9]+', val)):
            raise ValueError('range {} exceeds max DID of 0xFFFF'.format(val))
        return super(DIDRange, cls).__new__(cls, val)


class DiagnosticSessionRange(SparseHexRange):
    def __new__(cls, val):
        # Ensure that values are >= 2 and <= than 0x7F (127)
        if any(int(n, 16) > 0x7F for n in re.findall(r'[A-Za-z0-9]+', val)):
            raise ValueError('range {} exceeds max Diagnostic Session of 0x7F'.format(val))
        elif any(int(n, 16) < 0x02 for n in re.findall(r'[A-Za-z0-9]+', val)):
            raise ValueError('range {} below min Diagnostic Session of 0x02'.format(val))
        return super(DiagnosticSessionRange, cls).__new__(cls, val)


class SecurityAccessKeyRange(SparseHexRange):
    def __new__(cls, val):
        # Ensure that values are >= 2 and <= than 0x7D (125)
        if any(int(n, 16) > 0x7D for n in re.findall(r'[A-Za-z0-9]+', val)):
            raise ValueError('range {} exceeds max Security Access Key of 0x7D'.format(val))
        elif any(int(n, 16) < 0x02 for n in re.findall(r'[A-Za-z0-9]+', val)):
            raise ValueError('range {} below min Security Access Key of 0x02'.format(val))

        # The auth levels alternate
        return super(SecurityAccessKeyRange, cls).__new__(cls, val, 2)

class PayloadLength(SparseHexRange):
    def __new__(cls, val):
        # Ensure that values are <= than 0xFFF (4095)
        if any(int(n, 16) > 0xFFF for n in re.findall(r'[A-Za-z0-9]+', val)):
            raise ValueError('range {} exceeds max payload length of 0xFFF'.format(val))
        return super(PayloadLength, cls).__new__(cls, val)

class OneOrMoreOf(argparse.Action):
    def __init__(self, option_strings, dest, choices, nargs, **kwargs):
        if nargs == 0:
            raise ValueError('nargs must not be 0')
        if choices is None:
            raise ValueError('choices must be supplied')

        self.allowed_values = list(choices)

        # Override choices sent to the parent class constructor
        super(OneOrMoreOf, self).__init__(option_strings, dest, nargs=nargs, choices=None, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        # Handle both -sE -sD and -sED argument styles for the scan type
        items = getattr(namespace, self.dest, [])
        if items:
            items = list(items)
        else:
            items = []

        for val in values:
            if len(val) > 1:
                items.extend(list(val))
            else:
                items.append(val)

        # Get rid of duplicate entries
        items = list(set(items))

        if items and not set(items).issubset(set(self.allowed_values)):
            raise ValueError('invalid choice: {}, choose one or more of {}'.format(
                ''.join(items), ''.join(self.allowed_values)))
        setattr(namespace, self.dest, items)


def _get_baud_options():
    bauds = [b[4:-3] for b in dir(cancat) if b.startswith('CAN_') and b.endswith('BPS')]
    return bauds

def _get_baud_value(baud):
    ret = getattr(cancat, "CAN_{}BPS".format(baud))
    return ret


def udsmap_parse_args():
    # TODO: Add support for a writable did scan?
    # TODO: Add support to attempt memory read
    # TODO: Add support to attempt memory write?
    # TODO: Add support to attempt block data transfer from ECU?
    # TODO: Add support to attempt block data transfer to ECU?
    parser = argparse.ArgumentParser(
            prog='udsmap',
            description='CAN bus network mapping tool')
    parser.add_argument('-s', '--scan', required=True,
            #choices='EDWSAL', nargs='+', action=OneOrMoreOf,
            #help='Type of scan to run, select one or more of: (E) ECUs, (D) read DIDs, (W) write DIDs, (S) diagnostic Sessions, (A) seed/key Authentication levels, (L) authentication key Length')
            # re-enable only after security access levels and key length scanning has been tested
            #choices='EDSAL', nargs='+', action=OneOrMoreOf,
            #help='Type of scan to run, select one or more of: (E) ECUs, (D) read DIDs, (S) diagnostic Sessions, (A) security Authentication levels, (L) authentication key Length')
            choices='EDS', nargs='+', action=OneOrMoreOf,
            help='Type of scan to run, select one or more of: (E) ECUs, (D) read DIDs, (S) diagnostic Sessions')
    parser.add_argument('-p', '--port', default='/dev/ttyACM0',
            help='System device to use to communicate to the CanCat hardware (/dev/ttyACM0)')
    parser.add_argument('-b', '--baud',
            choices=_get_baud_options(), default='AUTO',
            help='Set the CAN Bus Speed')
    parser.add_argument('-t', '--discovery-type',
            choices=['did', 'session'], default='did',
            help='ECU discovery method: attempt to read a DID (F190), or enter diagnostic session 2')
    parser.add_argument('-m', '--bus-mode',
            choices=['std', 'ext', 'both'], default='both',
            help='Bus mode, only run standard 11-bit ECU discovery, extended 29-bit discovery or both - in the default "both" mode a standard 11-bit scan is run and then an exgtended 29-bit scan')
    parser.add_argument('-n', '--no-recursive-session-scanning', action='store_true',
            help='Disable recursive session scanning')
    parser.add_argument('-E', metavar='<ECU Range>',
            type=ECURange, default='00-FF',
            help='ECU address range to search')
    parser.add_argument('-D', metavar='<DID Read Range>',
            type=DIDRange, default='F180-F18E,F190-F1FF',
            help='DID range to search, by default restricted to the ISO14229 specified DIDs (F180-F18E,F190-F1FF), large DID ranges may take a long time')
    parser.add_argument('-S', metavar='<Diagnostic Session Range>',
            type=DiagnosticSessionRange, default='02-7F',
            help='Diagnostic Sessions to search for')
    #parser.add_argument('-A', metavar='<Security Access Key Range>',
    #        type=SecurityAccessKeyRange, default='01-41,61-7D',
    #        help='Security Access Key range to test, by default Security Sessions 43-60 are not tested, those values are used for end-of-life airbag deployment and may cause damage.')

    # According to ISO 14229 there is no upper bound on the size of the key
    # (that I could see) aside from the constraints of the ISO-TP protocol
    # itself. But for sanity's sake the default will be to stop trying when we
    # reach 32 bytes.
    #parser.add_argument('-L', metavar='<Key Length Range>',
    #        type=PayloadLength, default='01-20',
    #        help='Key Length range to test')

    parser.add_argument('-T', '--timeout', type=float, default=0.2,
            help='UDS Timeout, 3 seconds is the ISO14229 standard, standard for this tool is 200 msec (0.2)')
    parser.add_argument('-w', '--startup-wait', type=float, nargs='?', const=2.0,
            help='Wait to receive CAN messages before starting the scan')
    parser.add_argument('-d', '--scan-delay', type=float, default=0.0,
            help='Wait a small time between requests, helps prevent flooding the bus')
    parser.add_argument('-r', '--rescan', action='store_true',
            help='Run a full rescan and merge new results with any existing data')
    #parser.add_argument('-f', '--force', action='store_true',
    #        help='Force udsmap to scan with potentially harmful options')
    #parser.add_argument('-y', '--yes', action='store_true',
    #        help='Automatically answer "yes" to any questions the tool asks')
    parser.add_argument('-v', '--verbose', action='count',
            help='Verbose logging, use -vv for extra verbosity')
    parser.add_argument('-l', '--log-file', nargs='?', const='canmap_%Y%m%d-%H%M%S.log',
            help='Log filename to write to, log filename can contain "time.strftime" formatting like "canmap_%%Y%%m%%d-%%H%%M%%S.log"')
    parser.add_argument('-o', '--output-file', nargs='?', const='canmap_%Y%m%d-%H%M%S.yml',
            help='Scan results output filename, can contain "time.strftime" formatting like "canmap_%%Y%%m%%d-%%H%%M%%S.yml"')
    parser.add_argument('-c', '--can-session-file', nargs='?', const='canmap_%Y%m%d-%H%M%S.sess',
            help='Filename for saving raw cancat session, can contain "time.strftime" formatting like "canmap_%%Y%%m%%d-%%H%%M%%S.sess"')
    parser.add_argument('-i', '--input-file',
            help='Input file containing previous scan results')
    parser.add_argument('-u', '--uds-class',
            help='Custom UDS class, allows for implementing key/seed unlock functions or testing, example: cancat.uds.test.TestUDS')
    return parser.parse_args()


def log_and_save(results, note):
    log.msg(note)
    results['notes'][results['start_time']] += '\n' + note


def import_results(args, c, scancls):
    if args.input_file is not None:
        # TODO: support multiple in/out file types?
        import yaml
        try:
            from yaml import CLoader as yamlLoader
        except ImportError:
            from yaml import Loader as yamlLoader

        with open(args.input_file, 'r') as f:
            imported_data = yaml.load(f, Loader=yamlLoader)

        config = {
            'config': imported_data['config'],
            'notes': imported_data['notes'],
            'ECUs': {},
        }

        if not config['notes']:
            config['notes'] = {}

        # If the input baudrate is AUTO (the default), and the input config
        # file has a baud rate, use the value from the config file, otherwise
        # override the config file.
        if args.baud != 'AUTO' or 'baud' not in config['config']:
            config['config']['baud'] = args.baud

        if 'no_recursive_session_scanning' not in config['config']:
            config['config']['no_recursive_session_scanning'] = args.no_recursive_session_scanning

        if 'timeout' not in config['config']:
            config['config']['timeout'] = args.timeout

        for e in imported_data['ECUs']:
            addr = ECUAddress(**e)
            config['ECUs'][addr] = ECU(c, addr, uds_class=scancls,
                    timeout=config['config']['timeout'], delay=args.scan_delay, **e)
        return config


def save_results(results, filename=None):
    if filename is not None:
        import yaml

        try:
            class literal_unicode(unicode): pass
        except NameError:
            # in python3 just use "str"
            class literal_unicode(str): pass

        def literal_unicode_representer(dumper, data):
            return dumper.represent_scalar(u'tag:yaml.org,2002:str', data, style='|')
        yaml.add_representer(literal_unicode, literal_unicode_representer)

        def hexint_presenter(dumper, data):
            return dumper.represent_int(hex(data))
        yaml.add_representer(int, hexint_presenter)

        def ecu_presenter(dumper, ecu):
            obj = []
            for key, val in ecu.export().items():
                obj.append((dumper.represent_data(key), dumper.represent_data(val)))
            return yaml.nodes.MappingNode(u'tag:yaml.org,2002:map', obj)

        yaml.add_representer(ECU, ecu_presenter)

        # TODO: It'd be more esthetically pleasing in the output files if
        #       response data could be represented as a simple ascii string with
        #       escaped bytes in it rather than the standard yaml "!!binary
        #       + base64 string" method.
        #
        #       This is the closest I got but that makes it difficult to load
        #       the data. For now we will use the default !!binary format, if
        #       someone manually creates the data with escaped strings it'll
        #       still be loaded correctly.
        #
        #       class data_str(str): pass
        #         def data_str_presenter(dumper, data):
        #             return dumper.represent_str(repr(data)[1:-1])
        #         yaml.add_representer(data_str, data_str_presenter)

        # TODO: I should probably make the config a class of it's own also, with
        #       .add_ecu(), .add_note(), .export(), .import()
        output_data = {}
        global _config
        output_data['config'] = results['config']
        output_data['notes'] = dict([(k, literal_unicode(v)) for k, v in results['notes'].items()])
        output_data['ECUs'] = sorted([e for e in results['ECUs'].values()], key=lambda x: x._addr.tx_arbid)

        with open(filename, 'w') as f:
            f.write(yaml.dump(output_data))

def save():
    global _config, _output_filename, _can_session_filename
    if _output_filename:
        save_results(_config, _output_filename)

    if _can_session_filename:
        global c
        c.saveSessionToFile(_can_session_filename)


def save_and_exit(retval):
    save()
    sys.exit(retval)


def sigint_handler(signum, frame):
    global _config
    log_and_save(_config, 'scan aborted @ {}'.format(now()))
    save_and_exit(1)


def scan(config, args, c, scancls):
    if 'E' in args.scan:
        log_and_save(_config, 'ECU scan started @ {}'.format(config['start_time']))

        if not _config['ECUs'] or args.rescan:
            ecus = []
            if args.discovery_type == 'did':
                if args.bus_mode in ['std', 'both']:
                    ecus.extend(ecu_did_scan(c, args.E, ext=0, udscls=scancls,
                        timeout=config['config']['timeout'], delay=args.scan_delay))
                if args.bus_mode in ['ext', 'both']:
                    ecus.extend(ecu_did_scan(c, args.E, ext=1, udscls=scancls,
                        timeout=config['config']['timeout'], delay=args.scan_delay))
            else:
                if args.bus_mode in ['std', 'both']:
                    ecus.extend(ecu_session_scan(c, args.E, ext=0, udscls=scancls,
                        timeout=config['config']['timeout'], delay=args.scan_delay))
                if args.bus_mode in ['ext', 'both']:
                    ecus.extend(ecu_session_scan(c, args.E, ext=1, udscls=scancls,
                        timeout=config['config']['timeout'], delay=args.scan_delay))

            for addr in ecus:
                _config['ECUs'][addr] = ECU(c, addr, uds_class=scancls,
                        timeout=config['config']['timeout'], delay=args.scan_delay)

    if 'D' in args.scan:
        log_and_save(_config, 'DID read scan started @ {}'.format(now()))

        for ecu in _config['ECUs'].values():
            ecu.did_read_scan(args.D, args.rescan)

    #if 'W' in args.scan:
    #    log_and_save(_config, 'DID write scan started @ {}'.format(now()))
    #
    #    for ecu in _config['ECUs'].values():
    #        ecu.did_write_scan(args.D, args.rescan)

    if 'S' in args.scan:
        log_and_save(_config, 'Session scan started @ {}'.format(now()))

        if config['config']['no_recursive_session_scanning']:
            recursive = False
        else:
            recursive = True

        for ecu in _config['ECUs'].values():
            ecu.session_scan(args.S, args.rescan, rescan_did_range=args.D, recursive_scan=recursive)

    if 'A' in args.scan:
        log_and_save(_config, 'Auth scan started @ {}'.format(now()))

        for ecu in _config['ECUs'].values():
            ecu.auth_scan(args.A, args.rescan)

    if 'L' in args.scan:
        log_and_save(_config, 'Key Length scan started @ {}'.format(now()))

        for ecu in _config['ECUs'].values():
            ecu.key_length_scan(args.L, args.rescan)


def main():
    args = udsmap_parse_args()

    # TODO: move this to it's own class in cancat.utils, the config/args global
    #       data thing will be better handled that way
    #cancat.utils.canmap(args)

    if args.verbose == 1:
        loglevel = log.DEBUG
    elif args.verbose and args.verbose >= 2:
        loglevel = log.DETAIL
    else:
        loglevel = log.WARNING

    if args.log_file is not None:
        logfile = time.strftime(args.log_file)
    else:
        logfile = None

    log.start(level=loglevel, filename=logfile)
    log.debug(args)

    # TODO: Check for potentially damaging options

    # TODO: Warn about how long the combined scan options will probably take:
    #   - ECU Scan: if timeout is 3s:
    #                   worst case with both std & ext = (247 + 255) * 3 =
    #                   3012 sec = 25.1 minutes
    #   - ECU Scan: if timeout is 0.1s:
    #                   worst case with both std & ext = (247 + 255) * 0.1 =
    #                   50 sec = ~ 1 minute
    #   - DID Scan:
    #log.warning('ECU scan {} may take up to 25 minutes to complete'.format(args.E))

    global c

    ifaceclass = cancat.CanInterface
    scancls = None
    if args.uds_class:
        pkg, cls = args.uds_class.rsplit('.', 1)
        scanlib = importlib.import_module(pkg)
        scancls = getattr(scanlib, cls)

        # If the custom UDS class package has a "CanInterface" class, use that
        # instead of the real cancat.CanInterface class
        if hasattr(scanlib, 'CanInterface'):
            ifaceclass = getattr(scanlib, 'CanInterface')
    c = ifaceclass(port=args.port)

    global _config
    if args.input_file is not None:
        _config = import_results(args, c, scancls)
    else:
        _config = {
            'config': {
                'baud': args.baud,
                'timeout': args.timeout,
                'no_recursive_session_scanning': args.no_recursive_session_scanning,
            },
            'notes': {},
            'ECUs': {},
        }

    c.setCanBaud(_get_baud_value(_config['config']['baud']))

    if args.output_file:
        global _output_filename
        _output_filename = time.strftime(args.output_file)

    if args.can_session_file:
        global _can_session_filename
        _can_session_filename = time.strftime(args.can_session_file)

    start_time = now()
    _config['notes'][start_time] = []
    _config['start_time'] = start_time
    _config['notes'][start_time] = 'command: {}'.format(' '.join(sys.argv))

    if args.startup_wait:
        # Listen for messages to ensure that the bus is working right
        count1 = c.getCanMsgCount()
        time.sleep(args.startup_wait)
        count2 = c.getCanMsgCount()
        if count2 <= count1:
            log_and_save(_config, 'ERROR: No CAN traffic detected on {} @ {}'.format(args.port, args.baud))
            save_and_exit(2)

    # signal will catch CTRL-C in script contexts
    signal.signal(signal.SIGINT, sigint_handler)

    # catching KeyboardInterrupt will catch CTRL-C in interactive contexts
    try:
        scan(_config, args, c, scancls)

        log_and_save(_config, 'scans completed @ {}'.format(now()))
        save_and_exit(0)
    except KeyboardInterrupt:
        log_and_save(_config, 'scan aborted @ {}'.format(now()))
        save_and_exit(1)
    except Exception as e:
        saved_trace = traceback.format_exc()
        log_and_save(_config, 'Exception @ {}: {}'.format(now(), e))
        save()

        print(saved_trace, file=sys.stderr)
        sys.exit(3)
