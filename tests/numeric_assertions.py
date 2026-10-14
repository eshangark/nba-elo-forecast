"""Compare replay structures exactly except for bounded platform rounding."""

import math


def assert_nested_close(case, actual, expected, path='root'):
    case.assertEqual(type(actual), type(expected), path)
    if isinstance(expected, float):
        case.assertTrue(math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12),
                        f'{path}: {actual} != {expected}')
    elif isinstance(expected, dict):
        case.assertEqual(actual.keys(), expected.keys(), path)
        for key in expected:
            assert_nested_close(case, actual[key], expected[key], f'{path}.{key}')
    elif isinstance(expected, list):
        case.assertEqual(len(actual), len(expected), path)
        for index, (a, b) in enumerate(zip(actual, expected)):
            assert_nested_close(case, a, b, f'{path}[{index}]')
    else:
        case.assertEqual(actual, expected, path)
