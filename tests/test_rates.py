from aave_usdc_yield.rates import (
    RAY,
    SECONDS_PER_YEAR,
    apr_to_apy,
    ray_to_apr,
    ray_to_apr_apy,
)


def test_ray_constant():
    assert RAY == 10**27


def test_seconds_per_year():
    assert SECONDS_PER_YEAR == 31_536_000


def test_ray_to_apr_five_percent():
    ray = int(0.05 * RAY)
    apr = ray_to_apr(ray)
    assert abs(apr - 0.05) < 1e-12


def test_apr_to_apy_formula():
    apr = 0.05
    expected = (1 + apr / SECONDS_PER_YEAR) ** SECONDS_PER_YEAR - 1
    assert abs(apr_to_apy(apr) - expected) < 1e-15
    # APY should be slightly above APR for positive rates
    assert apr_to_apy(apr) > apr


def test_zero_rate():
    apr, apy = ray_to_apr_apy(0)
    assert apr == 0.0
    assert apy == 0.0


def test_ray_to_apr_apy_roundtrip_label_inputs():
    ray = 50_000_000_000_000_000_000_000_000  # exactly 0.05 * 1e27? close
    apr, apy = ray_to_apr_apy(ray)
    assert apr == ray / RAY
    assert apy == apr_to_apy(apr)
