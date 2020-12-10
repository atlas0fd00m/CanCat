from __future__ import print_function

import sys


class bcolors:
    ENDC        = '\033[0m'
    BLACK       = '\033[30m'
    RED         = '\033[31m'
    GREEN       = '\033[32m'
    YELLOW      = '\033[33m'
    BLUE        = '\033[34m'
    MAGENTA     = '\033[35m'
    CYAN        = '\033[36m'
    LGT_GRAY    = '\033[37m'
    DEFAULT     = '\033[39m'
    DRK_GRAY    = '\033[90m'
    LGT_RED     = '\033[91m'
    LGT_GREEN   = '\033[92m'
    LGT_YELLOW  = '\033[93m'
    LGT_BLUE    = '\033[94m'
    LGT_MAGENTA = '\033[95m'
    LGT_CYAN    = '\033[96m'

def _color_test():
    colors = [
        bcolors.BLACK,
        bcolors.RED,
        bcolors.GREEN,
        bcolors.YELLOW,
        bcolors.BLUE,
        bcolors.MAGENTA,
        bcolors.CYAN,
        bcolors.LGT_GRAY,
        bcolors.DEFAULT,
        bcolors.DRK_GRAY,
        bcolors.LGT_RED,
        bcolors.LGT_GREEN,
        bcolors.LGT_YELLOW,
        bcolors.LGT_BLUE,
        bcolors.LGT_MAGENTA,
        bcolors.LGT_CYAN,
    ]
    for color in colors:
        print('{}{}{}'.format(color, 'TEST', bcolors.ENDC))


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


MSG         = LogLevel('',           None,                0)
CRITICAL    = LogLevel('CRITICAL: ', bcolors.LGT_MAGENTA, 1)
ERROR       = LogLevel('ERROR: ',    bcolors.LGT_RED,     2)
WARNING     = LogLevel('WARNING: ',  bcolors.LGT_YELLOW,  3)
INFO        = LogLevel('INFO: ',     bcolors.LGT_GREEN,   4)
FIXME       = LogLevel('FIXME: ',    bcolors.DRK_GRAY,    5)
DEBUG       = LogLevel('DEBUG: ',    bcolors.LGT_BLUE,    6)
DETAIL      = LogLevel('DETAIL: ',   bcolors.LGT_CYAN,    7)


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

def detail(*args):
    log(DETAIL, *args)
