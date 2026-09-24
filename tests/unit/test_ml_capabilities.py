import pytest
from forpost_prediction_core.capabilities import (
    EvidenceTier,
    EvidenceTierError,
    PredictionTask,
    SourceKind,
    assess_task_capability,
    require_evidence_tier,
)


def test_event_only_sources_enable_only_sensor_failure_proxy() -> None:
    """Ловит попытку обучать пожар, доступ или износ без обязательных источников."""
    available_sources = frozenset({SourceKind.EVENTS, SourceKind.CHANNELS, SourceKind.OBJECTS})

    sensor_failure = assess_task_capability(PredictionTask.SENSOR_FAILURE, available_sources)
    fire_risk = assess_task_capability(PredictionTask.FIRE_RISK, available_sources)
    unauthorized_access = assess_task_capability(
        PredictionTask.UNAUTHORIZED_ACCESS, available_sources
    )
    infrastructure_wear = assess_task_capability(
        PredictionTask.INFRASTRUCTURE_WEAR, available_sources
    )

    assert sensor_failure.training_available is True
    assert sensor_failure.label_strategy == "cadence_adjusted_silence_horizon_proxy_v2"
    assert sensor_failure.maximum_evidence_tier is EvidenceTier.PROXY
    assert fire_risk.training_available is False
    assert fire_risk.maximum_evidence_tier is EvidenceTier.ANOMALY
    assert SourceKind.VERIFICATION_RESULTS in fire_risk.missing_sources
    assert unauthorized_access.training_available is False
    assert SourceKind.ACCESS_EVENTS in unauthorized_access.missing_sources
    assert infrastructure_wear.training_available is False
    assert infrastructure_wear.maximum_evidence_tier is EvidenceTier.SCENARIO
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
    assert fire_risk.maximum_evidence_tier is EvidenceTier.VALIDATED


def test_proxy_sources_cannot_be_promoted_to_validated_evidence() -> None:
    """Ловит публикацию proxy-метрик как качества подтверждённого инцидента."""
    capability = assess_task_capability(
        PredictionTask.SENSOR_FAILURE,
        frozenset({SourceKind.EVENTS, SourceKind.CHANNELS}),
    )

    assert require_evidence_tier(capability, EvidenceTier.PROXY) is EvidenceTier.PROXY
    with pytest.raises(EvidenceTierError, match="доказательности"):
        require_evidence_tier(capability, EvidenceTier.VALIDATED)
