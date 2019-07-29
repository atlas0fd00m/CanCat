import collections


class ECUAddress(object):
    # Add the kwargs param so we can construct an ECUAddress out of a dictionary 
    # that has extra stuff in it
    def __init__(self, tx_arbid, rx_arbid, extflag, *args, **kwargs):
        self.tx_arbid = tx_arbid
        self.rx_arbid = rx_arbid
        self.extflag = extflag

    def __repr__(self):
        return 'ECU({}, {}, {})'.format( hex(self.tx_arbid), hex(self.rx_arbid), self.extflag)

    def __str__(self):
        return 'ECU({}, {}, {})'.format( hex(self.tx_arbid), hex(self.rx_arbid), self.extflag)

    def __iter__(self):
        return iter((self.tx_arbid, self.rx_arbid, self.extflag))

    def __getitem__(self, key):
        return self.__dict__[key]

    def __len__(self):
        return len(self.__dict__)

    def keys(self):
        return iter(('tx_arbid', 'rx_arbid', 'extflag'))
