import pytest

from cthulu.core.trading_loop import PositionSizeDecision


@pytest.mark.parametrize(
    ("base_size", "multiplier", "expected"),
    [
        (0.019, 1.0, 0.01),
        (0.01, 0.5, 0.0),
        (0.05, 2.0, 0.05),
    ],
)
def test_adjusted_size_never_rounds_above_risk_approved_volume(
    base_size, multiplier, expected
):
    decision = PositionSizeDecision(base_size=base_size)
    decision.apply_adjustment("test", multiplier)

    assert decision.compute_final(min_lot=0.01, volume_step=0.01) == expected


def test_invalid_adjustment_fails_closed():
    decision = PositionSizeDecision(base_size=0.1)
    decision.apply_adjustment("test", float("nan"))

    assert decision.compute_final(min_lot=0.01, volume_step=0.01) == 0.0
