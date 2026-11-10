from akca.analysis.technical import _rsi

def test_wilder_rsi_handles_monotonic_and_flat_series():
    rising = [float(i) for i in range(20)]
    falling = [float(20 - i) for i in range(20)]
    flat = [100.0] * 20

    assert _rsi(rising, period=14) == 100.0
    assert _rsi(falling, period=14) == 0.0
    assert _rsi(flat, period=14) == 50.0

def test_rsi_returns_none_without_enough_observations():
    assert _rsi([10.0] * 14, period=14) is None
