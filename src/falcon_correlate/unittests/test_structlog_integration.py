"""Unit tests for structlog integration patterns.

These tests validate the structlog integration approaches documented in
the users' guide.  They prove that:

1. ``structlog.contextvars.merge_contextvars()`` does NOT automatically
   pick up ``correlation_id_var`` and ``user_id_var`` (negative test
   documenting the limitation).
2. A custom structlog processor that reads from the library's context
   variables works correctly.
3. The ``bind_contextvars`` bridging approach works correctly.

All tests are skipped when ``structlog`` is not installed.
"""

from __future__ import annotations

import typing as typ

import pytest

structlog = pytest.importorskip("structlog")

if typ.TYPE_CHECKING:
    import collections.abc as cabc

from falcon_correlate import correlation_id_var, user_id_var  # noqa: E402


def inject_correlation_context(
    logger: object,
    method_name: str,
    event_dict: dict[str, object],
) -> dict[str, object]:
    """Inject correlation ID and user ID into structlog event dict.

    This is the same processor function documented in the users' guide.
    It reads from ``falcon-correlate``'s context variables and injects
    them into the event dictionary using ``setdefault`` so that
    explicitly bound values are preserved.
    """
    event_dict.setdefault("correlation_id", correlation_id_var.get() or "-")
    event_dict.setdefault("user_id", user_id_var.get() or "-")
    return event_dict


@pytest.fixture(autouse=True)
def _reset_structlog() -> typ.Generator[None, None, None]:
    """Reset structlog configuration after each test."""
    yield
    structlog.contextvars.clear_contextvars()
    structlog.reset_defaults()


def _configure_structlog_with_capture(
    captured: list[dict[str, object]],
    *,
    include_custom_processor: bool = False,
) -> None:
    """Configure structlog with a capture processor.

    Parameters
    ----------
    captured : list[dict[str, object]]
        List to append captured event dicts to.
    include_custom_processor : bool
        If True, include ``inject_correlation_context`` in the
        processor chain.

    """
    processors: list[object] = [
        structlog.contextvars.merge_contextvars,
    ]
    if include_custom_processor:
        processors.append(inject_correlation_context)

    def _capture(
        logger: object,
        method_name: str,
        event_dict: dict[str, object],
    ) -> dict[str, object]:
        captured.append(dict(event_dict))
        raise structlog.DropEvent

    processors.append(_capture)

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(0),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )


def _run_isolated_structlog_test(
    isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    setup_and_log: cabc.Callable[[list[dict[str, object]]], None],
) -> list[dict[str, object]]:
    """Run a structlog test in isolated context.

    Parameters
    ----------
    isolated_context : Callable
        The isolated_context fixture.
    setup_and_log : Callable
        A function that receives the captured list, sets up context
        variables, configures structlog, and logs a test message.

    Returns
    -------
    list[dict[str, object]]
        The captured log events.

    """
    captured: list[dict[str, object]] = []

    def test_logic() -> None:
        setup_and_log(captured)

    isolated_context(test_logic)
    return captured


class TestMergeContextvarsLimitation:
    """Tests proving merge_contextvars does not pick up library variables.

    These negative tests document the limitation that
    ``structlog.contextvars.merge_contextvars()`` only reads context
    variables bound via ``structlog.contextvars.bind_contextvars()``,
    not arbitrary ``contextvars.ContextVar`` instances such as
    ``correlation_id_var`` and ``user_id_var``.
    """

    @pytest.mark.parametrize(
        ("context_var", "field_name", "var_name"),
        [
            (correlation_id_var, "correlation_id", "correlation_id_var"),
            (user_id_var, "user_id", "user_id_var"),
        ],
        ids=["correlation_id", "user_id"],
    )
    def test_merge_contextvars_ignores_library_context_vars(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        context_var: typ.ContextVar[str | None],
        field_name: str,
        var_name: str,
    ) -> None:
        """Verify merge_contextvars does not pick up library context variables."""

        def setup_and_log(
            captured: list[dict[str, object]],
        ) -> None:
            context_var.set("should-not-appear")
            _configure_structlog_with_capture(captured)
            structlog.get_logger().info("test")

        captured = _run_isolated_structlog_test(isolated_context, setup_and_log)

        assert len(captured) == 1
        assert field_name not in captured[0], (
            f"merge_contextvars should NOT pick up {var_name}, "
            f"but event contained: {captured[0]}"
        )


class TestCustomProcessorApproach:
    """Tests for the custom processor integration approach.

    These tests validate the ``inject_correlation_context`` processor
    function documented in the users' guide.
    """

    @pytest.mark.parametrize(
        ("correlation_id_value", "user_id_value", "expected_cid", "expected_uid"),
        [
            ("proc-cid-001", "proc-uid-001", "proc-cid-001", "proc-uid-001"),
            (None, None, "-", "-"),
        ],
        ids=["ids_set", "ids_unset"],
    )
    def test_custom_processor_handles_context_values(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
        correlation_id_value: str | None,
        user_id_value: str | None,
        expected_cid: str,
        expected_uid: str,
    ) -> None:
        """Verify custom processor injects IDs or placeholders appropriately."""

        def setup_and_log(
            captured: list[dict[str, object]],
        ) -> None:
            if correlation_id_value is not None:
                correlation_id_var.set(correlation_id_value)
            if user_id_value is not None:
                user_id_var.set(user_id_value)
            _configure_structlog_with_capture(captured, include_custom_processor=True)
            structlog.get_logger().info("test")

        captured = _run_isolated_structlog_test(isolated_context, setup_and_log)

        assert len(captured) == 1
        assert captured[0]["correlation_id"] == expected_cid, (
            f"expected {expected_cid!r}, got {captured[0].get('correlation_id')!r}"
        )
        assert captured[0]["user_id"] == expected_uid, (
            f"expected {expected_uid!r}, got {captured[0].get('user_id')!r}"
        )

    def test_custom_processor_preserves_explicit_binding(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify setdefault preserves explicitly bound values."""
        captured: list[dict[str, object]] = []

        def test_logic() -> None:
            correlation_id_var.set("contextvar-value")
            structlog.contextvars.bind_contextvars(correlation_id="explicit-value")
            _configure_structlog_with_capture(captured, include_custom_processor=True)
            log = structlog.get_logger()
            log.info("test")

        isolated_context(test_logic)

        assert len(captured) == 1
        assert captured[0]["correlation_id"] == "explicit-value", (
            "setdefault should preserve the explicitly bound value, "
            f"got {captured[0].get('correlation_id')!r}"
        )


class TestBindContextvarsApproach:
    """Tests for the bind_contextvars bridging approach.

    These tests validate the alternative approach where the user calls
    ``structlog.contextvars.bind_contextvars()`` to bridge the library's
    context variables into structlog's own context.
    """

    def test_bind_contextvars_makes_ids_available(
        self,
        isolated_context: cabc.Callable[[cabc.Callable[[], None]], None],
    ) -> None:
        """Verify bind_contextvars bridges library values into structlog."""
        captured: list[dict[str, object]] = []

        def test_logic() -> None:
            correlation_id_var.set("bind-cid-001")
            user_id_var.set("bind-uid-001")

            structlog.contextvars.bind_contextvars(
                correlation_id=correlation_id_var.get(),
                user_id=user_id_var.get(),
            )

            _configure_structlog_with_capture(captured)
            log = structlog.get_logger()
            log.info("test")

        isolated_context(test_logic)

        assert len(captured) == 1
        assert captured[0]["correlation_id"] == "bind-cid-001", (
            f"expected 'bind-cid-001', got {captured[0].get('correlation_id')!r}"
        )
        assert captured[0]["user_id"] == "bind-uid-001", (
            f"expected 'bind-uid-001', got {captured[0].get('user_id')!r}"
        )