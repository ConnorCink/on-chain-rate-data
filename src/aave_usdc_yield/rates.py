"""RAY → APR → APY conversions (Aave UI / aave-utilities continuous style).

Pins (docs/decisions.md):
- Supply field is liquidityRate / currentLiquidityRate in RAY (1e27).
- RAY is treated as APR: APR = ray / 1e27
- APY = (1 + APR / SECONDS_PER_YEAR) ** SECONDS_PER_YEAR - 1
  with SECONDS_PER_YEAR = 31536000
- Always return RAY + APR; APY is derived and labeled.
"""

from __future__ import annotations

RAY = 10**27
SECONDS_PER_YEAR = 31_536_000


def ray_to_apr(liquidity_rate_ray: int | float) -> float:
    """Convert RAY-encoded liquidity rate to decimal APR (e.g. 0.05 = 5%)."""
    return float(liquidity_rate_ray) / RAY


def apr_to_apy(apr: float) -> float:
    """Aave-utilities continuous compounding from APR to APY."""
    if apr <= -1.0:
        raise ValueError(f"APR must be > -1 for APY formula; got {apr}")
    return (1.0 + apr / SECONDS_PER_YEAR) ** SECONDS_PER_YEAR - 1.0


def ray_to_apr_apy(liquidity_rate_ray: int | float) -> tuple[float, float]:
    """Return (supply_apr, supply_apy) from a RAY liquidity rate."""
    apr = ray_to_apr(liquidity_rate_ray)
    apy = apr_to_apy(apr)
    return apr, apy
