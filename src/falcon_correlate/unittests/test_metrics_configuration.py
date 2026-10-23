"""Tests for metrics recorder configuration and public compatibility."""

from __future__ import annotations

import logging
import typing as typ

import pytest

from falcon_correlate import (
    CorrelationIDConfig,
    CorrelationIDMiddleware,
    MetricsRecorder,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc


def test_metrics_recorder_configuration_paths_and_positional_compatibility() -> None:
    """All config entry points accept the callback and retain five old args."""
    events = []
    recorder = events.append
    config = CorrelationIDConfig(metrics_recorder=recorder)
    assert config.metrics_recorder is recorder, "expected direct config callback"

    factory_config = CorrelationIDConfig.from_kwargs(metrics_recorder=recorder)
    assert factory_config.metrics_recorder is recorder, (
        "expected from_kwargs to preserve the recorder callback"
    )
    keyword_middleware = CorrelationIDMiddleware(metrics_recorder=recorder)
    assert keyword_middleware.config.metrics_recorder is recorder, (
        "expected middleware keyword configuration to preserve the recorder"
    )
    config_middleware = CorrelationIDMiddleware(config=config)
    assert config_middleware.config is config, "expected supplied config object"

    should_echo_header = False
    original = CorrelationIDConfig(
        "X-Request-ID",
        ["127.0.0.1"],
        lambda: "generated",
        bool,
        should_echo_header,
    )
    assert original.header_name == "X-Request-ID", "first positional field moved"
    assert original.trusted_sources == frozenset({"127.0.0.1"}), (
        "second positional field moved"
    )
    assert original.generator() == "generated", "third positional field moved"
    assert original.validator is not None, "fourth positional field moved"
    assert original.validator("id"), "fourth positional field moved"
    assert original.echo_header_in_response is False, "fifth positional field moved"


@pytest.mark.parametrize(
    "factory", [CorrelationIDConfig, CorrelationIDConfig.from_kwargs]
)
def test_non_callable_metrics_recorder_logs_type_only(
    caplog: pytest.LogCaptureFixture,
    factory: cabc.Callable[..., CorrelationIDConfig],
) -> None:
    """Configuration rejects and reports a non-callable metrics recorder."""
    with (
        caplog.at_level(
            logging.DEBUG,
            logger="falcon_correlate.middleware_config",
        ),
        pytest.raises(TypeError, match="metrics_recorder must be callable"),
    ):
        factory(metrics_recorder=typ.cast("MetricsRecorder", "private-value"))

    records = [
        record
        for record in caplog.records
        if record.name == "falcon_correlate.middleware_config"
    ]
    assert len(records) == 1, f"expected one config validation record: {records!r}"
    assert records[0].__dict__.get("config_field") == "metrics_recorder", (
        "wrong config field"
    )
    assert records[0].__dict__.get("config_rejected_value") == "str", (
        "expected type-only value"
    )
    assert "private-value" not in records[0].getMessage(), (
        "metrics recorder diagnostic exposed its supplied value"
    )
