from forpost_prediction_core.capabilities import (
    PredictionTask,
    SourceKind,
    assess_task_capability,
)


def test_event_only_sources_enable_only_sensor_failure_proxy() -> None:
    """Ловит попытку обучать пожар, доступ или износ без обязательных источников."""
    available_sources = frozenset(
        {SourceKind.EVENTS, SourceKind.CHANNELS, SourceKind.OBJECTS}
    )

    sensor_failure = assess_task_capability(PredictionTask.SENSOR_FAILURE, available_sources)
    fire_risk = assess_task_capability(PredictionTask.FIRE_RISK, available_sources)
    unauthorized_access = assess_task_capability(
        PredictionTask.UNAUTHORIZED_ACCESS, available_sources
    )
    infrastructure_wear = assess_task_capability(
        PredictionTask.INFRASTRUCTURE_WEAR, available_sources
    )

    assert sensor_failure.training_available is True
    assert sensor_failure.label_strategy == "silence_horizon_proxy"
    assert fire_risk.training_available is False
    assert SourceKind.VERIFICATION_RESULTS in fire_risk.missing_sources
    assert unauthorized_access.training_available is False
    assert SourceKind.ACCESS_EVENTS in unauthorized_access.missing_sources
    assert infrastructure_wear.training_available is False
    assert SourceKind.MAINTENANCE_HISTORY in infrastructure_wear.missing_sources


def test_task_capability_becomes_trainable_only_with_all_required_sources() -> None:
    """Ловит частичную готовность задачи при отсутствии хотя бы одного источника лейблов."""
    available_sources = frozenset(SourceKind)

    fire_risk = assess_task_capability(PredictionTask.FIRE_RISK, available_sources)
    unauthorized_access = assess_task_capability(
        PredictionTask.UNAUTHORIZED_ACCESS, available_sources
    )
    infrastructure_wear = assess_task_capability(
        PredictionTask.INFRASTRUCTURE_WEAR, available_sources
    )

    assert fire_risk.training_available is True
    assert unauthorized_access.training_available is True
    assert infrastructure_wear.training_available is True
    assert not fire_risk.missing_sources
    assert not unauthorized_access.missing_sources
    assert not infrastructure_wear.missing_sources
