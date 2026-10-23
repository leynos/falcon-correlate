"""Unit tests for CorrelationIDConfig validation."""

from __future__ import annotations

import logging
import typing as typ

import pytest

from falcon_correlate import CorrelationIDConfig

if typ.TYPE_CHECKING:
    import collections.abc as cabc


_CONFIG_LOGGER_NAME = "falcon_correlate.middleware_config"
_CONFIG_FAILURE_TEMPLATE = (
    "Correlation ID configuration validation failed for %s: rejected value %s"
)


class _ValidationFailureCase(typ.NamedTuple):
    """Expected exception and diagnostic details for one invalid field."""

    field: str
    value: object
    exception_type: type[Exception]
    message: str
    rejected_value: str
    cause: type[Exception] | None


class TestCorrelationIDConfigValidation:
    """Direct unit tests for CorrelationIDConfig validation."""

    def test_config_empty_header_name_raises_value_error(self) -> None:
        """Verify empty header_name on CorrelationIDConfig raises ValueError."""
        with pytest.raises(ValueError, match="header_name must not be empty"):
            CorrelationIDConfig(header_name="")

    def test_config_whitespace_header_name_raises_value_error(self) -> None:
        """Verify whitespace-only header_name raises ValueError."""
        with pytest.raises(ValueError, match="header_name must not be empty"):
            CorrelationIDConfig(header_name="   ")

    def test_config_empty_trusted_source_raises_value_error(self) -> None:
        """Verify empty string in trusted_sources raises ValueError."""
        with pytest.raises(
            ValueError,
            match="trusted_sources must not contain empty strings",
        ):
            CorrelationIDConfig(trusted_sources=frozenset(["127.0.0.1", ""]))

    def test_config_whitespace_trusted_source_raises_value_error(self) -> None:
        """Verify whitespace-only string in trusted_sources raises ValueError."""
        with pytest.raises(
            ValueError,
            match="trusted_sources must not contain empty strings",
        ):
            CorrelationIDConfig(trusted_sources=frozenset(["127.0.0.1", "   "]))

    def test_config_scalar_trusted_source_raises_type_error(self) -> None:
        """Verify trusted_sources rejects a single string value."""
        with pytest.raises(TypeError, match="trusted_sources must be an iterable"):
            CorrelationIDConfig(trusted_sources="127.0.0.1")

    def test_config_non_string_trusted_source_raises_type_error(self) -> None:
        """Verify trusted_sources rejects non-string members."""
        with pytest.raises(TypeError, match="trusted_sources must contain strings"):
            CorrelationIDConfig(
                trusted_sources=typ.cast("cabc.Iterable[str]", ["127.0.0.1", 123])
            )

    def test_from_kwargs_scalar_trusted_source_raises_type_error(self) -> None:
        """Verify from_kwargs rejects a single string trusted source."""
        with pytest.raises(TypeError, match="trusted_sources must be an iterable"):
            CorrelationIDConfig.from_kwargs(trusted_sources="127.0.0.1")

    @pytest.mark.parametrize(
        "trusted_sources",
        [None, [], set()],
        ids=["none", "empty_list", "empty_set"],
    )
    def test_from_kwargs_empty_trusted_sources_are_empty_frozensets(
        self,
        trusted_sources: cabc.Iterable[str] | None,
    ) -> None:
        """Verify from_kwargs preserves empty trusted source containers."""
        config = CorrelationIDConfig.from_kwargs(trusted_sources=trusted_sources)

        failure_message = "expected config.trusted_sources to equal frozenset()"
        assert config.trusted_sources == frozenset(), failure_message
        failure_message = (
            "expected condition: isinstance(config.trusted_sources, frozen..."
        )
        assert isinstance(config.trusted_sources, frozenset), failure_message

    def test_config_non_callable_generator_raises_type_error(self) -> None:
        """Verify non-callable generator on CorrelationIDConfig raises TypeError."""
        with pytest.raises(TypeError, match="generator must be callable"):
            CorrelationIDConfig(
                generator=typ.cast("cabc.Callable[[], str]", "not-a-callable")
            )

    def test_config_non_callable_validator_raises_type_error(self) -> None:
        """Verify non-callable validator on CorrelationIDConfig raises TypeError."""
        with pytest.raises(TypeError, match="validator must be callable"):
            CorrelationIDConfig(
                validator=typ.cast("cabc.Callable[[str], bool]", "not-a-callable")
            )

    @pytest.mark.parametrize(
        "case",
        [
            pytest.param(
                _ValidationFailureCase(
                    "header_name",
                    "",
                    ValueError,
                    "header_name must not be empty",
                    "''",
                    None,
                ),
                id="empty-header",
            ),
            pytest.param(
                _ValidationFailureCase(
                    "header_name",
                    "\r\n\t",
                    ValueError,
                    "header_name must not be empty",
                    repr("\r\n\t"),
                    None,
                ),
                id="escaped-whitespace-header",
            ),
            pytest.param(
                _ValidationFailureCase(
                    "trusted_sources",
                    [""],
                    ValueError,
                    "trusted_sources must not contain empty strings",
                    "''",
                    None,
                ),
                id="empty-source-member",
            ),
            pytest.param(
                _ValidationFailureCase(
                    "trusted_sources",
                    [123],
                    TypeError,
                    "trusted_sources must contain strings",
                    "int",
                    None,
                ),
                id="non-string-source-member",
            ),
            pytest.param(
                _ValidationFailureCase(
                    "trusted_sources",
                    ["10.1.2.3/24"],
                    ValueError,
                    "Invalid CIDR notation '10.1.2.3/24': has host bits set",
                    repr("10.1.2.3/24"),
                    ValueError,
                ),
                id="cidr-host-bits",
            ),
            pytest.param(
                _ValidationFailureCase(
                    "trusted_sources",
                    ["not-an-ip"],
                    ValueError,
                    "Invalid IP address or CIDR notation: 'not-an-ip'",
                    repr("not-an-ip"),
                    ValueError,
                ),
                id="malformed-source",
            ),
            pytest.param(
                _ValidationFailureCase(
                    "generator",
                    123,
                    TypeError,
                    "generator must be callable",
                    "int",
                    None,
                ),
                id="non-callable-generator",
            ),
            pytest.param(
                _ValidationFailureCase(
                    "validator",
                    123,
                    TypeError,
                    "validator must be callable",
                    "int",
                    None,
                ),
                id="non-callable-validator",
            ),
        ],
    )
    @pytest.mark.parametrize(
        "factory",
        [
            pytest.param(CorrelationIDConfig, id="direct-construction"),
            pytest.param(CorrelationIDConfig.from_kwargs, id="from-kwargs"),
        ],
    )
    def test_validation_failures_log_the_rejected_value(
        self,
        caplog: pytest.LogCaptureFixture,
        factory: cabc.Callable[..., CorrelationIDConfig],
        case: _ValidationFailureCase,
    ) -> None:
        """Verify failures log safe field details without changing errors."""
        with (
            caplog.at_level(logging.DEBUG, logger=_CONFIG_LOGGER_NAME),
            pytest.raises(case.exception_type) as exc_info,
        ):
            factory(**{case.field: case.value})

        assert str(exc_info.value) == case.message, (
            f"expected unchanged exception message {case.message!r}, got "
            f"{str(exc_info.value)!r}"
        )
        if case.cause is None:
            assert exc_info.value.__cause__ is None, (
                "expected exception chaining to remain unchanged"
            )
        else:
            assert isinstance(exc_info.value.__cause__, case.cause), (
                "expected wrapped parsing exception to remain chained"
            )

        records = [
            record for record in caplog.records if record.name == _CONFIG_LOGGER_NAME
        ]
        assert len(records) == 1, f"expected one validation record, got {records!r}"
        record = records[0]
        assert record.levelno == logging.DEBUG, "expected DEBUG validation record"
        assert record.msg == _CONFIG_FAILURE_TEMPLATE, "expected constant log template"
        assert record.args == (case.field, case.rejected_value), (
            "expected lazy log arguments"
        )
        assert record.__dict__.get("config_field") == case.field, (
            "expected structured configuration field"
        )
        assert record.__dict__.get("config_rejected_value") == case.rejected_value, (
            "expected structured safe rejected value"
        )
        assert not hasattr(record, "correlation_id"), (
            "configuration validation logs must not attach a correlation ID"
        )
        message = record.getMessage()
        assert "\r" not in message, "carriage returns must be escaped in log output"
        assert "\n" not in message, "newlines must be escaped in log output"

    @pytest.mark.parametrize(
        ("factory", "expected_message"),
        [
            pytest.param(
                CorrelationIDConfig,
                "trusted_sources must be an iterable of strings, not a string",
                id="direct-construction",
            ),
            pytest.param(
                CorrelationIDConfig.from_kwargs,
                "trusted_sources must be an iterable of strings, not a str",
                id="from-kwargs",
            ),
        ],
    )
    def test_bare_string_trusted_sources_log_and_keep_factory_message(
        self,
        caplog: pytest.LogCaptureFixture,
        factory: cabc.Callable[..., CorrelationIDConfig],
        expected_message: str,
    ) -> None:
        """Verify bare-string rejection is logged at each construction path."""
        with (
            caplog.at_level(logging.DEBUG, logger=_CONFIG_LOGGER_NAME),
            pytest.raises(TypeError) as exc_info,
        ):
            factory(trusted_sources="127.0.0.1")

        assert str(exc_info.value) == expected_message, (
            f"expected unchanged exception message {expected_message!r}, got "
            f"{str(exc_info.value)!r}"
        )
        records = [
            record for record in caplog.records if record.name == _CONFIG_LOGGER_NAME
        ]
        assert len(records) == 1, f"expected one validation record, got {records!r}"
        assert records[0].__dict__.get("config_field") == "trusted_sources", (
            "expected the bare-string diagnostic to identify trusted_sources"
        )
        assert records[0].__dict__.get("config_rejected_value") == repr("127.0.0.1"), (
            "expected the bare-string diagnostic to render the supplied value"
        )

    @pytest.mark.parametrize("field", ["generator", "validator"])
    @pytest.mark.parametrize(
        "factory",
        [
            pytest.param(CorrelationIDConfig, id="direct-construction"),
            pytest.param(CorrelationIDConfig.from_kwargs, id="from-kwargs"),
        ],
    )
    def test_non_callable_string_logs_only_its_type(
        self,
        caplog: pytest.LogCaptureFixture,
        factory: cabc.Callable[..., CorrelationIDConfig],
        field: str,
    ) -> None:
        """Verify callback-shaped strings cannot leak into diagnostics."""
        callback_text = "credential-like-callback-value"
        with (
            caplog.at_level(logging.DEBUG, logger=_CONFIG_LOGGER_NAME),
            pytest.raises(TypeError),
        ):
            factory(**{field: callback_text})

        records = [
            record for record in caplog.records if record.name == _CONFIG_LOGGER_NAME
        ]
        assert len(records) == 1, f"expected one validation record, got {records!r}"
        assert records[0].__dict__.get("config_field") == field, (
            "expected the rejected callback field"
        )
        assert records[0].__dict__.get("config_rejected_value") == "str", (
            "expected callback details to use only the supplied value's type"
        )
        assert callback_text not in records[0].getMessage(), (
            "callback string contents must not appear in the diagnostic"
        )

    def test_valid_construction_does_not_log_validation_records(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Verify successful configuration construction emits no records."""
        with caplog.at_level(logging.DEBUG, logger=_CONFIG_LOGGER_NAME):
            CorrelationIDConfig(trusted_sources=["127.0.0.1"])

        records = [
            record for record in caplog.records if record.name == _CONFIG_LOGGER_NAME
        ]
        assert not records, f"expected no validation records, got {records!r}"
