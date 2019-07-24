import collections


class ECUAddress(object):
    def __init__(self, tx_arbid, rx_arbid, extflag):
        self.tx_arbid = tx_arbid
        self.rx_arbid = rx_arbid
        self.extflag = extflag

    def __repr__(self):
        return 'ECUAddress({}, {}, {})'.format( hex(self.tx_arbid), hex(self.rx_arbid), self.extflag)

    def __str__(self):
        return '({}, {}, {})'.format( hex(self.tx_arbid), hex(self.rx_arbid), self.extflag)

    def __iter__(self):
        return iter((self.tx_arbid, self.rx_arbid, self.extflag))

    def __getitem__(self, key):
        return self.__dict__[key]

    def __len__(self):
        return len(self.__dict__)

    def keys(self):
        return iter(('tx_arbid', 'rx_arbid', 'extflag'))
