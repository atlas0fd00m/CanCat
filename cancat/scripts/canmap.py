# CAN bus device mapping tool

import sys
import argparse
import sets
import re
import time
import signal
import importlib

import cancat
import cancat.uds
import cancat.uds.ecu
import cancat.uds.utils
import cancat.utils.types
from cancat.utils import log


c = None
_config = None
_output_filename = None


def now():
    # return an ISO 8601 formatted date string
    # 2019-07-18T02:28:16+00:00
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime())


class ECURange(cancat.utils.types.SparseHexRange):
    def __new__(cls, val):
        # Ensure that values are <= than 0xFF (255)
        if any(int(n, 16) > 0xFF for n in re.findall(r'[A-Za-z0-9]+', val)):
            raise ValueError('range %s exceeds max ECU addr of 0xFF' % val)
        return super(ECURange, cls).__new__(cls, val)


class DIDRange(cancat.utils.types.SparseHexRange):
    def __new__(cls, val):
        # Ensure that values are <= than 0xFFFF (65535)
        if any(int(n, 16) > 0xFFFF for n in re.findall(r'[A-Za-z0-9]+', val)):
            raise ValueError('range %s exceeds max DID of 0xFFFF' % val)
        return super(DIDRange, cls).__new__(cls, val)


class DiagnosticSessionRange(cancat.utils.types.SparseHexRange):
    def __new__(cls, val):
        # Ensure that values are <= than 0x7F (127)
        if any(int(n, 16) > 0x7F for n in re.findall(r'[A-Za-z0-9]+', val)):
            raise ValueError('range %s exceeds max Diagnostic Session of 0x7F' % val)
        return super(DiagnosticSessionRange, cls).__new__(cls, val)


class SecurityAccessKeyRange(cancat.utils.types.SparseHexRange):
    def __new__(cls, val):
        # Ensure that values are <= than 0x7D (125)
        if any(int(n, 16) > 0x7D for n in re.findall(r'[A-Za-z0-9]+', val)):
            raise ValueError('range %s exceeds max Security Access Key of 0x7D' % val)

        # The auth levels alternate
        return super(cancat.utils.types.SparseRange, cls).__new__(cls, (cancat.utils.types._hex_range(v, 2) for v in val.split(',')))


class PayloadLength(cancat.utils.types.SparseHexRange):
    def __new__(cls, val):
        # Ensure that values are <= than 0xFFF (4095)
        if any(int(n, 16) > 0xFFF for n in re.findall(r'[A-Za-z0-9]+', val)):
            raise ValueError('range %s exceeds max payload length of 0xFFF' % val)
        return super(PayloadLength, cls).__new__(cls, val)


def _get_baud_options():
    bauds = [b[4:-3] for b in dir(cancat) if b.startswith('CAN_') and b.endswith('BPS')]
    return bauds

def _get_baud_value(baud):
    ret = getattr(cancat, "CAN_{}BPS".format(baud))
    return ret


def udsmap_parse_args():
    parser = argparse.ArgumentParser(
            prog='udsmap',
            description='CAN bus network mapping tool')
    parser.add_argument('-s', '--scan', nargs='?', action='append',
            #choices='EDWSAL', required=True,
            #help='Type of scan to run, select one or more of: (E) ECUs, (D) read DIDs, (W) write DIDs, (S) diagnostic Sessions, (A) seed/key Authentication levels, (L) authentication key Length')
            choices='EDSAL', required=True,
            help='Type of scan to run, select one or more of: (E) ECUs, (D) read DIDs, (S) diagnostic Sessions, (A) seed/key Authentication levels, (L) authentication key Length')
    parser.add_argument('-p', '--port', default='/dev/ttyACM0',
            help='System device to use to communicate to the CanCat hardware (/dev/ttyACM0)') 
    parser.add_argument('-b', '--baud',
            choices=_get_baud_options(), default='500K',
            help='Set the CAN Bus Speed') 
    parser.add_argument('-t', '--discovery-type',
            choices=['did', 'session'], default='did',
            help='ECU discovery method: attempt to read a DID (F190), or enter diagnostic session 2')
    parser.add_argument('-m', '--bus-mode',
            choices=['std', 'ext', 'both'], default='both',
            help='Bus mode, only run standard 11-bit ECU discovery, extended 29-bit discovery or both - in the default "both" mode a standard 11-bit scan is run and then an exgtended 29-bit scan')
    parser.add_argument('-E', metavar='<ECU Range>',
            type=ECURange, default='00-FF',
            help='ECU address range to search')
    parser.add_argument('-D', metavar='<DID Read Range>',
            type=DIDRange, default='F180-F1FF',
            help='DID range to search, by default restricted to the ISO14229 specified DIDs, large DID ranges may take a long time')
    parser.add_argument('-S', metavar='<Diagnostic Session Range>',
            type=DiagnosticSessionRange, default='02-7F',
            help='Diagnostic Sessions to search for')
    parser.add_argument('-A', metavar='<Security Access Key Range>',
            type=SecurityAccessKeyRange, default='01-41,61-7D',
            help='Security Access Key range to test, by default Security Sessions 43-60 are not tested, those values are used for end-of-life airbag deployment and may cause damage.')

    # According to ISO 14229 there is no upper bound on the size of the key 
    # (that I could see) aside from the constraints of the ISO-TP protocol 
    # itself. But for sanity's sake the default will be to stop trying when we 
    # reach 32 bytes.
    parser.add_argument('-L', metavar='<Key Length Range>',
            type=PayloadLength, default='01-20',
            help='Key Length range to test')

    # TODO: Add support to attempt memory read
    # TODO: Add support to attempt memory write?
    # TODO: Add support to attempt block data transfer from ECU?
    # TODO: Add support to attempt block data transfer to ECU?

    parser.add_argument('-T', '--timeout', type=float, default=3.0,
            help='UDS Timeout, 3 seconds is standard')
    parser.add_argument('-w', '--wait', action='store_true',
            help='Wait to receive CAN messages before starting the scan')
    parser.add_argument('-r', '--rescan', action='store_true',
            help='Run a full rescan and merge new results with any existing data')

    parser.add_argument('-f', '--force', action='store_true',
            help='Force udsmap to scan with potentially harmful options')
    parser.add_argument('-y', '--yes', action='store_true',
            help='Automatically answer "yes" to any questions the tool asks')
    parser.add_argument('-v', '--verbose', action='count',
            help='Verbose logging, use -vv for extra verbosity')
    parser.add_argument('-l', '--log-file',
            help='Log filename to write to, log filename can contain "time.strftime" formatting like "udsscan_%%Y%%m%%d-%%H%%M%%S.log"')
    parser.add_argument('-o', '--output-file', default='udsscan.yml',
            help='Scan results output filename, can contain "time.strftime" formatting like "udsscan_%%Y%%m%%d-%%H%%M%%S.yml"')
    parser.add_argument('-c', '--can-session-file',
            help='Filename for saving raw cancat session')
    parser.add_argument('-i', '--input-file',
            help='Input file containing previous scan results')
    parser.add_argument('-u', '--uds-class', default='cancat.uds.ecu.ScanClass',
            help='Custom UDS class, allows for implementing key/seed unlock functions or testing')

    return parser.parse_args()


def log_and_save(results, note):
    log.msg(note)
    results['notes'][results['start_time']] += '\n' + note


def import_results(filename=None):
    if filename is not None:
        # TODO: support multiple in/out file types?
        import yaml

        with open(filename, 'r') as f:
            imported_data = yaml.read(f.read())

        config['notes'] = imported_data['notes']
        config['ECUs'] = [cancat.uds.ecu(e) for e in imported_data['ECUs']]
        return config


def save_results(results, filename=None):
    if filename is not None:
        # TODO: support multiple in/out file types?
        import yaml

        class literal_unicode(unicode): pass

        def literal_unicode_representer(dumper, data):
            return dumper.represent_scalar(u'tag:yaml.org,2002:str', data, style='|')
        yaml.add_representer(literal_unicode, literal_unicode_representer)

        def hexint_presenter(dumper, data):
            return dumper.represent_int(hex(data))
        yaml.add_representer(int, hexint_presenter)

        # TODO: It'd be more esthetically pleasing in the output files if 
        #       response data could be represented as a simple ascii string with 
        #       escaped bytes in it rather than the standard yaml "!!binary 
        #       + base64 string" method.

        # TODO: I should probably make the config a class of it's own also, with 
        #       .add_ecu(), .add_note(), .export(), .import()
        output_data = {}
        output_data['notes'] = dict([(k, literal_unicode(v)) for k, v in results['notes'].items()])
        output_data['ECUs'] = []
        for addr, ecu in results['ECUs'].items():
            data = dict(addr)
            data.update(ecu.export())
            output_data['ECUs'].append(data)

        with open(filename, 'w') as f:
            f.write(yaml.dump(output_data))


def save_and_exit(retval):
    save_results(_config, _output_filename)

    if _can_session_filename:
        global c
        c.saveSessionToFile(_can_session_filename)

    sys.exit(retval)


def sigint_handler(signum, frame):
    global _config
    log_and_save(_config, 'scan aborted @ {}'.format(now()))
    save_and_exit(1)


def main():
    args = udsmap_parse_args()
    
    # TODO: move this to it's own class in cancat.utils, the config/args global 
    #       data thing will be better handled that way
    #cancat.utils.canmap(args)

    if args.verbose == 1:
        loglevel = log.DEBUG
    elif args.verbose >= 2:
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
    #   - ECU Scan: worst case with both std & ext = (247 + 255) * 3sec =
    #               3012sec = 25.1 minutes
    #   - DID Scan: 
    #log.warning('ECU scan {} may take up to 25 minutes to complete'.format(args.E))

    pkg, cls = args.uds_class.rsplit('.', 1)
    scanlib = importlib.import_module(pkg)
    scancls = getattr(scanlib, cls)

    # TODO: there should be a better way to do this... I think?
    #       It would probably be better organized if I turned this scan function 
    #       into it's own class?
    cancat.uds.utils._UDS_CLASS = scancls

    # If the custom UDS class package has a "CanInterface" class, use that 
    # instead of the real cancat.CanInterface class
    global c
    if hasattr(scanlib, 'CanInterface'):
        c = getattr(scanlib, 'CanInterface')(port=args.port)
    else:
        c = cancat.CanInterface(port=args.port)

    c.setCanBaud(_get_baud_value(args.baud))

    global _config
    if args.input_file is not None:
        # TODO: test reading input config to make sure valid data is not 
        #       overwritten or re-scanned
        _config = import_results(args.input_file)
    else:
        _config = {
            'notes': {},
            'ECUs': {},
        }

    global _output_filename, _can_session_filename
    _output_filename = time.strftime(args.output_file)

    _can_session_filename = None
    if args.can_session_file:
        _can_session_filename = time.strftime(args.can_session_file)

    # wait a short delay and check how many can messages have been received
    time.sleep(1.0)

    start_time = now()
    _config['notes'][start_time] = []
    _config['start_time'] = start_time
    _config['notes'][start_time] = 'command: {}'.format(' '.join(sys.argv))

    if args.wait:
        # Listen for messages to ensure that the bus is working right
        count1 = c.getCanMsgCount()
        count2 = c.getCanMsgCount()
        if count2 <= count1:
            log_and_save(_config, 'ERROR: No CAN traffic detected on {} @ {}'.format(args.port, args.baud))
            save_and_exit(2)
    
    signal.signal(signal.SIGINT, sigint_handler)

    # Handle both -sE -sD and -sED argument styles for the scan type
    scan_types = []
    for scan in args.scan:
        if len(scan) > 1:
            scan_types.extend(list(scan))
        else:
            scan_types.append(scan)

    if 'E' in scan_types:
        log_and_save(_config, 'ECU scan started @ {}'.format(start_time))

        if not _config['ECUs'] or args.rescan:
            ecus = []
            if args.discovery_type == 'did':
                c.placeCanBookmark("Start_ECU_DID_Scan", str(args.E))
                if args.bus_mode in ['std', 'both']:
                    ecus.extend(cancat.uds.utils.ecu_did_scan(c, args.E, ext=0, timeout=args.timeout))
                if args.bus_mode in ['ext', 'both']:
                    ecus.extend(cancat.uds.utils.ecu_did_scan(c, args.E, ext=1, timeout=args.timeout))
                c.placeCanBookmark("Stop_ECU_DID_Scan", None)
            else:
                c.placeCanBookmark("Start_ECU_Session_Scan", str(args.E))
                if args.bus_mode in ['std', 'both']:
                    ecus.extend(cancat.uds.utils.ecu_session_scan(c, args.E, ext=0, timeout=args.timeout))
                if args.bus_mode in ['ext', 'both']:
                    ecus.extend(cancat.uds.utils.ecu_session_scan(c, args.E, ext=1, timeout=args.timeout))
                c.placeCanBookmark("Stop_ECU_Session_Scan", None)

            for addr in ecus:
                _config['ECUs'][addr] = cancat.uds.ecu.ECU(c, addr, uds_class=scancls, timeout=args.timeout)

    if 'D' in scan_types:
        log_and_save(_config, 'DID read scan started @ {}'.format(now()))

        c.placeCanBookmark("Start_DID_Read_Scan", str(args.D))
        for ecu in _config['ECUs'].values():
            ecu.did_read_scan(args.D, args.rescan)
        c.placeCanBookmark("Stop_DID_Read_Scan", None)

    #if 'W' in scan_types:
    #    log_and_save(_config, 'DID write scan started @ {}'.format(now()))
    #
    #    c.placeCanBookmark("Start_DID_Write_Scan", str(args.D))
    #    for ecu in _config['ECUs'].values():
    #        ecu.did_write_scan(args.D, args.rescan)
    #    c.placeCanBookmark("Stop_DID_Write_Scan", None)

    if 'S' in scan_types:
        log_and_save(_config, 'Session scan started @ {}'.format(now()))

        c.placeCanBookmark("Start_Session_Scan", str(args.S))
        for ecu in _config['ECUs'].values():
            ecu.session_scan(args.S, args.rescan)
        c.placeCanBookmark("Stop_Session_Scan", None)

    if 'A' in scan_types:
        log_and_save(_config, 'Auth scan started @ {}'.format(now()))

        c.placeCanBookmark("Start_Auth_Level_Scan", str(args.A))
        for ecu in _config['ECUs'].values():
            ecu.auth_scan(args.A, args.rescan)
        c.placeCanBookmark("Stop_Auth_Level_Scan", None)

    if 'L' in scan_types:
        log_and_save(_config, 'Key Length scan started @ {}'.format(now()))

        c.placeCanBookmark("Start_Key_Length_Scan", str(args.L))
        for ecu in _config['ECUs'].values():
            ecu.key_length_scan(args.L, args.rescan)
        c.placeCanBookmark("Stop_Key_Length_Scan", None)

    log_and_save(_config, 'scans completed @ {}'.format(now()))
    save_and_exit(0)
