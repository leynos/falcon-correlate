"""Unit tests for package public exports."""

from __future__ import annotations

import pytest


class TestPublicExports:
    """Tests for package public exports."""

    def test_public_exports_in_all(self) -> None:
        """Verify expected names are present in __all__."""
        import falcon_correlate

        assert "CorrelationIDMiddleware" in falcon_correlate.__all__
        assert "CorrelationIDConfig" in falcon_correlate.__all__
        assert "default_uuid7_generator" in falcon_correlate.__all__

    def test_default_uuid7_generator_importable_from_root(self) -> None:
        """Verify default_uuid7_generator can be imported from package root."""
        from falcon_correlate import default_uuid7_generator as gen

        with pytest.raises(NotImplementedError):
            gen()
