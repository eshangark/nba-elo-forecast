import unittest
from numeric_assertions import assert_nested_close


class NumericComparisonTests(unittest.TestCase):
    def test_rounding_is_allowed_but_changed_forecasts_or_identity_are_rejected(self):
        assert_nested_close(self, {'p': .7 + 1e-16, 'id': '1', 'scored': True},
                            {'p': .7, 'id': '1', 'scored': True})
        for changed in [{'p': .7001, 'id': '1', 'scored': True},
                        {'p': .7, 'id': '2', 'scored': True},
                        {'p': .7, 'id': '1', 'scored': 1}]:
            with self.assertRaises(AssertionError):
                assert_nested_close(self, changed, {'p': .7, 'id': '1', 'scored': True})
