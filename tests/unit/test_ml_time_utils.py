import pandas as pd
from forpost_prediction_core.time_utils import normalize_cutoff, normalize_event_times


def test_naive_source_time_is_localized_as_moscow_then_converted_to_utc():
    result = normalize_event_times(pd.Series(["2026-01-01 12:00:00"]))

    assert result.iloc[0] == pd.Timestamp("2026-01-01T09:00:00Z")
    assert normalize_cutoff(pd.Timestamp("2026-01-01 12:00:00")) == pd.Timestamp(
        "2026-01-01T09:00:00Z"
    )
