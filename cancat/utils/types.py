# Various types used by CanCat utility functions.
from past.builtins import xrange

import re

# Test if this is python2 or python3
try:
    _ = xrange(1, 2)
    _range_func = xrange
except NameError:
    _range_func = range

def _dec_range(val, increment=1):
    parts = re.split(r'-', val)
    if len(parts) == 1:
        return int(parts[0])
    else:
        return _range_func(int(parts[0]), int(parts[1]) + 1, increment)

def _hex_range(val, increment=1):
    parts = re.split(r'-', val)
    if len(parts) == 1:
        return int(parts[0], 16)
    else:
        return _range_func(int(parts[0], 16), int(parts[1], 16) + 1, increment)


class SparseRange(tuple):
    def __new__(cls, val, increment=1):
        return super(SparseRange, cls).__new__(cls, (_dec_range(v, increment) for v in val.split(',')))

    @classmethod
    def _get_classname(cls):
        return cls.__name__

    def __iter__(self):
        for val in super(SparseRange, self).__iter__():
            try:
                for i in val:
                    yield i
            except TypeError:
                yield val

    def __contains__(self, key):
        for val in super(SparseRange, self).__iter__():
            try:
                if key in val:
                    return True
            except TypeError:
                if key == val:
                    return True
        return False

    def __repr__(self):
        return '{}({})'.format(self._get_classname(), super(SparseRange, self).__repr__())

    def __str__(self):
        return '{}'.format(super(SparseRange, self).__str__())


class SparseHexRange(SparseRange):
    def __new__(cls, val, increment=1):
        return super(SparseRange, cls).__new__(cls, (_hex_range(v, increment) for v in val.split(',')))


class ECUAddress(object):
    # Add the kwargs param so we can construct an ECUAddress out of a dictionary 
    # that has extra stuff in it
    def __init__(self, tx_arbid, rx_arbid, extflag, *args, **kwargs):
        self.tx_arbid = tx_arbid
        self.rx_arbid = rx_arbid
        self.extflag = extflag

    def __hash__(self):
        return hash((self.tx_arbid, self.rx_arbid, self.extflag))

    def __repr__(self):
        return 'ECU({}, {}, {})'.format( hex(self.tx_arbid), hex(self.rx_arbid), self.extflag)

    def __iter__(self):
        return iter((self.tx_arbid, self.rx_arbid, self.extflag))

    def __getitem__(self, key):
        return self.__dict__[key]

    def __len__(self):
        return len(self.__dict__)

    def __eq__(self, other):
        return self.tx_arbid == other.tx_arbid and \
                self.rx_arbid == other.rx_arbid and \
                self.extflag == other.extflag

    def keys(self):
        return iter(('tx_arbid', 'rx_arbid', 'extflag'))
