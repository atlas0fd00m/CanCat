# Various types used by CanCat utility functions.

import re

# Test if this is python2 or python3
try:
    _ = xrange(1, 2)
    _range_func = xrange
except NameError:
    _range_func = range

def _dec_range(val, incr=1):
    parts = re.split(r'([0-9]+)-([0-9]+)', val)
    if len(parts) == 1:
        return int(parts[0], incr)
    else:
        return _range_func(int(parts[1]), int(parts[2]) + 1)

def _hex_range(val, incr=1):
    parts = re.split(r'([A-Fa-f0-9]+)-([A-Fa-f0-9]+)', val)
    if len(parts) == 1:
        return int(parts[0], 16, incr)
    else:
        return _range_func(int(parts[1], 16), int(parts[2], 16) + 1)


class SparseRange(tuple):
    def __new__(cls, val):
        return super(SparseRange, cls).__new__(cls, (_dec_range(v) for v in val.split(',')))

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
    def __new__(cls, val):
        return super(SparseRange, cls).__new__(cls, (_hex_range(v) for v in val.split(',')))
