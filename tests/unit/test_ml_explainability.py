import pytest
from forpost_prediction_core.explainability import (
    ExplainabilityUnavailableError,
    RawContribution,
    normalize_contributions,
)


def test_normalized_contributions_are_sorted_and_sum_to_one() -> None:
    """Ловит неупорядоченные факторы и веса, не соответствующие контракту UI."""
    factors = normalize_contributions(
        [
            RawContribution("частота", -2.0, "Повышенная частота"),
            RawContribution("тренд", 1.0, "Рост значения"),
        ]
    )

    assert [factor.factor for factor in factors] == ["частота", "тренд"]
    assert sum(factor.weight for factor in factors) == 1.0
    assert factors[0].weight == pytest.approx(2 / 3)


def test_normalized_contributions_refuse_zero_total_influence() -> None:
    """Ловит публикацию фиктивного объяснения при нулевом влиянии всех признаков."""
    with pytest.raises(ExplainabilityUnavailableError, match="вклад"):
        normalize_contributions([RawContribution("тренд", 0.0, "Нет влияния")])
