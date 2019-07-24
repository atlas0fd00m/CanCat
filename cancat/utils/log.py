
import sys


class bcolors:
    RED    = '\033[91m'
    ORANGE = '\033[33m'
    YELLOW = '\033[93m'
    GREEN  = '\033[92m'
    CYAN   = '\033[36m'
    BLUE   = '\033[94m'
    PURPLE = '\033[35m'
    ENDC   = '\033[0m'


class LogLevel(object):
    def __init__(self, name, color, val):
        self.name = name
        self.color = color
        self.val = val

    def colorized(self):
        if self.color is not None:
            return '{}{}{}'.format(self.color, self.name, bcolors.ENDC)
        else:
            return self.name

    def __str__(self):
        return self.name

    def __add__(self, other):
        return self.name + other

    def __eq__(self, other):
        return self.val == other

    def __ne__(self, other):
        return self.val != other

    def __gt__(self, other):
        return self.val > other

    def __ge__(self, other):
        return self.val >= other

    def __lt__(self, other):
        return self.val < other

    def __le__(self, other):
        return self.val <= other


MSG      = LogLevel('',           None,           0)
CRITICAL = LogLevel('CRITICAL: ', bcolors.RED,    1)
ERROR    = LogLevel('ERROR: ',    bcolors.ORANGE, 2)
WARNING  = LogLevel('WARNING: ',  bcolors.YELLOW, 3)
INFO     = LogLevel('INFO: ',     bcolors.GREEN,  4)
FIXME    = LogLevel('FIXME: ',    bcolors.BLUE ,  5)
DEBUG    = LogLevel('DEBUG: ',    bcolors.CYAN,   6)


# TODO: make this thread/process safe?
_log_level = -1
_log_filename = None
_log_file = None
_use_color = True
if sys.stdout.encoding is None:
    _use_color = False

def start(level=None, filename=None):
    global _log_level, _log_filename, _log_file

    if level is not None:
        _log_level = level
    elif _log_level == -1:
        # If the log level has not yet been initialized set a default level
        _log_level = MSG

    if filename is not None:
        if _log_filename is not None:
            if _log_filename != filename:
                stop()
                _log_filename = filename
        else:
            _log_filename = filename

    # TODO: add timesamp log output if log file already exists rather than 
    # overwriting?
    if _log_file is None and _log_filename is not None:
        _log_file = open(_log_filename, 'w+')

def stop():
    global _log_file

    if _log_file is not None:
        _log_file.close()
        _log_file = None

def log(level, *args):
    global _log_level, _log_file, _use_color

    if len(args) == 0:
        msg = ''
    elif len(args) == 1:
        msg = str(args[0])
    else:
        msg = str(args)

    if _log_level >= level:
        if _log_file is not None:
            _log_file.write(level + msg + '\n')

        if _use_color:
            print(level.colorized() + msg)
        else:
            print(level + msg)

def crit(*args):
    log(CRITICAL, *args)

def error(*args):
    log(ERROR, *args)

def warn(*args):
    log(WARNING, *args)

def msg(*args):
    log(MSG, *args)

def info(*args):
    log(INFO, *args)

def debug(*args):
    log(DEBUG, *args)
