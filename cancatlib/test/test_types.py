import unittest

from cancatlib.utils.types import _dec_range, _hex_range, SparseRange, SparseHexRange, ECUAddress


class DecRangeTest(unittest.TestCase):
    def test_single_value(self):
        self.assertEqual(5, _dec_range('5'))

    def test_range(self):
        result = _dec_range('3-7')
        self.assertEqual(range(3, 8), result)
        self.assertEqual([3, 4, 5, 6, 7], list(result))

    def test_range_with_increment(self):
        result = _dec_range('0-10', increment=2)
        self.assertEqual([0, 2, 4, 6, 8, 10], list(result))


class HexRangeTest(unittest.TestCase):
    def test_single_value(self):
        self.assertEqual(0xA, _hex_range('a'))

    def test_range(self):
        result = _hex_range('a-f')
        self.assertEqual(range(0xA, 0x10), result)
        self.assertEqual([0xA, 0xB, 0xC, 0xD, 0xE, 0xF], list(result))

    def test_range_with_increment(self):
        result = _hex_range('0-10', increment=4)
        self.assertEqual([0, 4, 8, 0xC, 0x10], list(result))


class SparseRangeTest(unittest.TestCase):
    def test_single_values(self):
        sr = SparseRange('1,5,10')
        self.assertEqual([1, 5, 10], list(sr))

    def test_mixed_values_and_ranges(self):
        sr = SparseRange('1,3-5,10')
        self.assertEqual([1, 3, 4, 5, 10], list(sr))

    def test_contains_single_value(self):
        sr = SparseRange('1,3-5,10')
        self.assertIn(1, sr)
        self.assertNotIn(2, sr)

    def test_contains_within_range(self):
        sr = SparseRange('1,3-5,10')
        self.assertIn(3, sr)
        self.assertIn(4, sr)
        self.assertIn(5, sr)
        self.assertNotIn(6, sr)
        self.assertNotIn(9, sr)

    def test_repr_and_str(self):
        sr = SparseRange('1,3-5')
        self.assertEqual('SparseRange', sr._get_classname())
        self.assertTrue(repr(sr).startswith('SparseRange('))
        self.assertEqual(str(tuple.__str__(sr)), str(sr))


class SparseHexRangeTest(unittest.TestCase):
    def test_mixed_values_and_ranges(self):
        shr = SparseHexRange('a,3-5,10')
        self.assertEqual([0xA, 3, 4, 5, 0x10], list(shr))

    def test_contains(self):
        shr = SparseHexRange('a,3-5,10')
        self.assertIn(0xA, shr)
        self.assertIn(4, shr)
        self.assertNotIn(6, shr)

    def test_is_a_sparse_range(self):
        shr = SparseHexRange('a')
        self.assertIsInstance(shr, SparseRange)
        self.assertEqual('SparseHexRange', shr._get_classname())


class ECUAddressTest(unittest.TestCase):
    def test_equality(self):
        self.assertEqual(ECUAddress(0x711, 0x719, 0), ECUAddress(0x711, 0x719, 0))
        self.assertNotEqual(ECUAddress(0x711, 0x719, 0), ECUAddress(0x711, 0x71A, 0))

    def test_iter_and_len(self):
        addr = ECUAddress(0x711, 0x719, 0)
        self.assertEqual((0x711, 0x719, 0), tuple(addr))
        self.assertEqual(3, len(addr))

    def test_hashable(self):
        # ECUAddress objects should be usable as dict keys / set members
        s = {ECUAddress(0x711, 0x719, 0), ECUAddress(0x711, 0x719, 0)}
        self.assertEqual(1, len(s))


if __name__ == '__main__':
    unittest.main()
