"""Unit tests for public httpx wrapper exports."""

from __future__ import annotations

import pytest

pytest.importorskip("httpx")


class TestHttpxWrapperExports:
    """Tests for public API exports of httpx wrapper functions."""

    def test_request_with_correlation_id_in_all(self) -> None:
        """Verify request_with_correlation_id is in __all__."""
        import falcon_correlate

        failure_message = (
            "expected condition: 'request_with_correlation_id' in falcon_c..."
        )
        assert "request_with_correlation_id" in falcon_correlate.__all__, (
            failure_message
        )

    def test_async_request_with_correlation_id_in_all(self) -> None:
        """Verify async_request_with_correlation_id is in __all__."""
        import falcon_correlate

        failure_message = (
            "expected condition: 'async_request_with_correlation_id' in fa..."
        )
        assert "async_request_with_correlation_id" in falcon_correlate.__all__, (
            failure_message
        )

    def test_request_with_correlation_id_importable(self) -> None:
        """Verify request_with_correlation_id is importable from root."""
        from falcon_correlate import request_with_correlation_id

        failure_message = "expected callable(request_with_correlation_id) to be truthy"
        assert callable(request_with_correlation_id), failure_message

    def test_async_request_with_correlation_id_importable(self) -> None:
        """Verify async_request_with_correlation_id is importable."""
        from falcon_correlate import async_request_with_correlation_id

        failure_message = (
            "expected condition: callable(async_request_with_correlation_i..."
        )
        assert callable(async_request_with_correlation_id), failure_message
