"""Unit tests for CorrelationIDConfig validation."""

from __future__ import annotations

import logging
import typing as typ

import pytest

from falcon_correlate import CorrelationIDConfig
from falcon_correlate.middleware_config import DEFAULT_HEADER_NAME
from falcon_correlate.middleware_utils import default_uuid7_generator

if typ.TYPE_CHECKING:
    import collections.abc as cabc

    from falcon_correlate.middleware_config import CorrelationIDConfigKwargs


class _FalseyGenerator:
    """Callable generator that is falsey to exercise identity preservation."""

    def __bool__(self) -> bool:
        """Report false while remaining callable."""
        return False

    def __call__(self) -> str:
        """Return a stable ID for tests."""
        return "generated-id"


class _SubclassCorrelationIDConfig(CorrelationIDConfig):
    """Exercise subclass construction through the inherited factory."""


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

    def test_from_kwargs_uses_all_defaults(self) -> None:
        """Verify from_kwargs supplies each documented default."""
        config = CorrelationIDConfig.from_kwargs()

        assert config.header_name == DEFAULT_HEADER_NAME, "expected the default header"
        assert config.trusted_sources == frozenset(), "expected no trusted sources"
        assert config.generator is default_uuid7_generator, (
            "expected the default generator"
        )
        assert config.validator is None, "expected no validator by default"
        assert config.echo_header_in_response is True, (
            "expected response echo by default"
        )

    def test_from_kwargs_explicit_none_generator_uses_default(self) -> None:
        """Verify an explicit None generator resolves to the UUIDv7 default."""
        config = CorrelationIDConfig.from_kwargs(generator=None)

        assert config.generator is default_uuid7_generator, (
            "expected None to resolve to the default generator"
        )

    def test_from_kwargs_preserves_falsey_generator_identity(self) -> None:
        """Verify a falsey callable generator is not replaced by the default."""
        generator = _FalseyGenerator()
        config = CorrelationIDConfig.from_kwargs(generator=generator)

        assert config.generator is generator, "expected the supplied generator identity"

    def test_from_kwargs_preserves_explicit_none_validator(self) -> None:
        """Verify an explicit None validator remains unset."""
        config = CorrelationIDConfig.from_kwargs(validator=None)

        assert config.validator is None, "expected explicit None to remain unchanged"

    def test_from_kwargs_rejects_unknown_keywords_in_sorted_order(self) -> None:
        """Verify unknown keys are rejected with deterministic ordering."""
        factory = typ.cast(
            "cabc.Callable[..., CorrelationIDConfig]",
            CorrelationIDConfig.from_kwargs,
        )
        with pytest.raises(TypeError) as exc_info:
            factory(unknown_z=1, unknown_a=2)

        assert str(exc_info.value) == (
            "Unknown keyword arguments: unknown_a, unknown_z"
        ), "expected unknown keyword names to be sorted"

    def test_from_kwargs_rejects_positional_arguments(self) -> None:
        """Verify from_kwargs retains its keyword-only call contract."""
        factory = typ.cast(
            "cabc.Callable[..., CorrelationIDConfig]",
            CorrelationIDConfig.from_kwargs,
        )
        with pytest.raises(TypeError, match="positional"):
            factory("X-Request-ID")

    def test_from_kwargs_returns_subclass_instance(self) -> None:
        """Verify the classmethod constructs through its receiving subclass."""
        config = _SubclassCorrelationIDConfig.from_kwargs()

        assert type(config) is _SubclassCorrelationIDConfig, (
            "expected the inherited factory to construct the subclass"
        )

    def test_from_kwargs_does_not_mutate_caller_inputs(self) -> None:
        """Verify kwargs and trusted-source input remain unchanged."""
        trusted_sources = ["127.0.0.1", "10.0.0.0/8"]
        kwargs: CorrelationIDConfigKwargs = {"trusted_sources": trusted_sources}
        original_kwargs = kwargs.copy()

        config = CorrelationIDConfig.from_kwargs(**kwargs)

        assert kwargs == original_kwargs, "expected the caller's kwargs to be unchanged"
        assert kwargs["trusted_sources"] is trusted_sources, (
            "expected the original trusted-source list to remain in kwargs"
        )
        assert trusted_sources == ["127.0.0.1", "10.0.0.0/8"], (
            "expected the caller's trusted-source list to be unchanged"
        )
        assert config.trusted_sources == frozenset(trusted_sources), (
            "expected the configuration to freeze trusted sources"
        )

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
