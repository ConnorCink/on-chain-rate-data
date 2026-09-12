from pathlib import Path

from aave_usdc_yield.benchmark import (
    compare_realized_to_benchmark,
    load_benchmark_csv,
)


def test_load_and_compare(tmp_path):
    p = tmp_path / "sofr.csv"
    p.write_text("date,rate\n2023-01-01,0.043\n2023-01-02,0.044\n2023-01-03,0.045\n")
    points = load_benchmark_csv(p)
    assert len(points) == 3
    realized = {
        "cumulative_return": 0.001,
        "annualized_realized": 0.05,
        "from_timestamp": 1672531200,  # 2023-01-01 UTC
        "to_timestamp": 1672704000,  # 2023-01-03 UTC
        "from_block": 1,
        "to_block": 2,
    }
    out = compare_realized_to_benchmark(realized, points)
    expected = (0.043 + 0.044 + 0.045) / 3
    assert abs(out["benchmark_avg_apr"] - expected) < 1e-12
    assert abs(out["spread_annualized_minus_benchmark"] - (0.05 - expected)) < 1e-12


def test_percent_flag(tmp_path):
    p = tmp_path / "sofr.csv"
    p.write_text("date,rate\n2023-01-01,4.30\n")
    pts = load_benchmark_csv(p, rate_is_percent=True)
    assert abs(pts[0].rate - 0.043) < 1e-12
