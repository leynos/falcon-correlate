"""Unit tests for trusted source IP/CIDR checking."""

from __future__ import annotations

import typing as typ

import falcon
import falcon.testing
import pytest

from falcon_correlate import CorrelationIDMiddleware
from tests.conftest import CorrelationEchoResource


class TestTrustedSourceChecking:
    """Tests for trusted source IP/CIDR matching."""

    # Exact IP matching tests

    def test_exact_ipv4_match_is_trusted(self) -> None:
        """Verify exact IPv4 match returns True."""
        middleware = CorrelationIDMiddleware(trusted_sources=["10.0.0.1"])
        assert middleware._is_trusted_source("10.0.0.1") is True

    def test_exact_ipv4_no_match_is_not_trusted(self) -> None:
        """Verify non-matching IPv4 returns False."""
        middleware = CorrelationIDMiddleware(trusted_sources=["10.0.0.1"])
        assert middleware._is_trusted_source("10.0.0.2") is False

    def test_exact_ipv6_match_is_trusted(self) -> None:
        """Verify exact IPv6 match returns True."""
        middleware = CorrelationIDMiddleware(trusted_sources=["::1"])
        assert middleware._is_trusted_source("::1") is True

    def test_exact_ipv6_no_match_is_not_trusted(self) -> None:
        """Verify non-matching IPv6 returns False."""
        middleware = CorrelationIDMiddleware(trusted_sources=["::1"])
        assert middleware._is_trusted_source("::2") is False

    # CIDR subnet matching tests

    def test_cidr_ipv4_subnet_match_is_trusted(self) -> None:
        """Verify IPv4 within CIDR range returns True."""
        middleware = CorrelationIDMiddleware(trusted_sources=["10.0.0.0/24"])
        assert middleware._is_trusted_source("10.0.0.50") is True

    def test_cidr_ipv4_subnet_no_match_is_not_trusted(self) -> None:
        """Verify IPv4 outside CIDR range returns False."""
        middleware = CorrelationIDMiddleware(trusted_sources=["10.0.0.0/24"])
        assert middleware._is_trusted_source("10.0.1.1") is False

    def test_cidr_ipv6_subnet_match_is_trusted(self) -> None:
        """Verify IPv6 within CIDR range returns True."""
        middleware = CorrelationIDMiddleware(trusted_sources=["2001:db8::/32"])
        assert middleware._is_trusted_source("2001:db8::1") is True

    def test_cidr_ipv6_subnet_no_match_is_not_trusted(self) -> None:
        """Verify IPv6 outside CIDR range returns False."""
        middleware = CorrelationIDMiddleware(trusted_sources=["2001:db8::/32"])
        assert middleware._is_trusted_source("2001:db9::1") is False

    # Edge cases

    def test_none_remote_addr_is_not_trusted(self) -> None:
        """Verify None remote_addr returns False."""
        middleware = CorrelationIDMiddleware(trusted_sources=["10.0.0.1"])
        assert middleware._is_trusted_source(None) is False

    def test_empty_string_remote_addr_is_not_trusted(self) -> None:
        """Verify empty string remote_addr returns False."""
        middleware = CorrelationIDMiddleware(trusted_sources=["10.0.0.1"])
        assert middleware._is_trusted_source("") is False

    def test_empty_trusted_sources_never_trusts(self) -> None:
        """Verify empty trusted_sources always returns False."""
        middleware = CorrelationIDMiddleware(trusted_sources=[])
        assert middleware._is_trusted_source("10.0.0.1") is False

    def test_malformed_remote_addr_is_not_trusted(self) -> None:
        """Verify malformed remote_addr returns False without raising."""
        middleware = CorrelationIDMiddleware(trusted_sources=["10.0.0.1"])
        assert middleware._is_trusted_source("not-an-ip") is False

    # Multiple sources

    def test_multiple_sources_first_match_is_trusted(self) -> None:
        """Verify matching first of multiple sources returns True."""
        middleware = CorrelationIDMiddleware(
            trusted_sources=["10.0.0.0/24", "192.168.1.0/24", "172.16.0.1"],
        )
        assert middleware._is_trusted_source("10.0.0.50") is True

    def test_multiple_sources_middle_match_is_trusted(self) -> None:
        """Verify matching middle of multiple sources returns True."""
        middleware = CorrelationIDMiddleware(
            trusted_sources=["10.0.0.0/24", "192.168.1.0/24", "172.16.0.1"],
        )
        assert middleware._is_trusted_source("192.168.1.50") is True

    def test_multiple_sources_last_match_is_trusted(self) -> None:
        """Verify matching last of multiple sources returns True."""
        middleware = CorrelationIDMiddleware(
            trusted_sources=["10.0.0.0/24", "192.168.1.0/24", "172.16.0.1"],
        )
        assert middleware._is_trusted_source("172.16.0.1") is True

    def test_multiple_sources_no_match_is_not_trusted(self) -> None:
        """Verify not matching any source returns False."""
        middleware = CorrelationIDMiddleware(
            trusted_sources=["10.0.0.0/24", "192.168.1.0/24", "172.16.0.1"],
        )
        assert middleware._is_trusted_source("8.8.8.8") is False

    # Mixed IPv4/IPv6 sources

    def test_mixed_sources_ipv6_addr_not_in_ipv4_sources(self) -> None:
        """Verify IPv6 address does not match IPv4-only trusted sources."""
        middleware = CorrelationIDMiddleware(
            trusted_sources=["10.0.0.0/8", "192.168.1.0/24"],
        )
        assert middleware._is_trusted_source("::1") is False

    def test_mixed_sources_ipv4_addr_matches_ipv4_in_mixed_list(self) -> None:
        """Verify IPv4 address matches IPv4 source in mixed IPv4/IPv6 list."""
        middleware = CorrelationIDMiddleware(
            trusted_sources=["::1", "10.0.0.0/8"],
        )
        assert middleware._is_trusted_source("10.0.0.1") is True

    def test_mixed_sources_ipv6_addr_matches_ipv6_in_mixed_list(self) -> None:
        """Verify IPv6 address matches IPv6 source in mixed IPv4/IPv6 list."""
        middleware = CorrelationIDMiddleware(
            trusted_sources=["10.0.0.0/8", "2001:db8::/32"],
        )
        assert middleware._is_trusted_source("2001:db8::1") is True

    def test_mixed_sources_ipv4_addr_not_in_ipv6_sources(self) -> None:
        """Verify IPv4 address does not match IPv6-only trusted sources."""
        middleware = CorrelationIDMiddleware(
            trusted_sources=["::1", "2001:db8::/32"],
        )
        assert middleware._is_trusted_source("10.0.0.1") is False


class TestTrustedSourceConfigValidation:
    """Tests for IP/CIDR validation in CorrelationIDConfig."""

    # IPv4 validation tests

    def test_invalid_ip_raises_value_error(self) -> None:
        """Verify invalid IP address raises ValueError."""
        with pytest.raises(ValueError, match="Invalid IP address or CIDR"):
            CorrelationIDMiddleware(trusted_sources=["not-an-ip"])

    def test_invalid_cidr_prefix_raises_value_error(self) -> None:
        """Verify invalid IPv4 CIDR prefix raises ValueError."""
        with pytest.raises(ValueError, match="Invalid IP address or CIDR"):
            CorrelationIDMiddleware(trusted_sources=["10.0.0.0/33"])

    def test_cidr_with_host_bits_raises_value_error(self) -> None:
        """Verify IPv4 CIDR with host bits set raises ValueError."""
        with pytest.raises(ValueError, match="has host bits set"):
            CorrelationIDMiddleware(trusted_sources=["10.0.0.5/24"])

    # IPv6 validation tests

    def test_invalid_ipv6_raises_value_error(self) -> None:
        """Verify invalid IPv6 address raises ValueError."""
        with pytest.raises(ValueError, match="Invalid IP address or CIDR"):
            CorrelationIDMiddleware(trusted_sources=["not:a:valid:ipv6"])

    def test_invalid_ipv6_cidr_prefix_raises_value_error(self) -> None:
        """Verify invalid IPv6 CIDR prefix raises ValueError."""
        with pytest.raises(ValueError, match="Invalid IP address or CIDR"):
            CorrelationIDMiddleware(trusted_sources=["2001:db8::/129"])

    def test_ipv6_cidr_with_host_bits_raises_value_error(self) -> None:
        """Verify IPv6 CIDR with host bits set raises ValueError."""
        with pytest.raises(ValueError, match="has host bits set"):
            CorrelationIDMiddleware(trusted_sources=["2001:db8::1/32"])

    def test_valid_ipv4_address_accepted(self) -> None:
        """Verify valid IPv4 address is accepted."""
        middleware = CorrelationIDMiddleware(trusted_sources=["192.168.1.1"])
        assert "192.168.1.1" in middleware.trusted_sources

    def test_valid_ipv4_cidr_accepted(self) -> None:
        """Verify valid IPv4 CIDR is accepted."""
        middleware = CorrelationIDMiddleware(trusted_sources=["192.168.1.0/24"])
        assert "192.168.1.0/24" in middleware.trusted_sources

    def test_valid_ipv6_address_accepted(self) -> None:
        """Verify valid IPv6 address is accepted."""
        middleware = CorrelationIDMiddleware(trusted_sources=["::1"])
        assert "::1" in middleware.trusted_sources

    def test_valid_ipv6_cidr_accepted(self) -> None:
        """Verify valid IPv6 CIDR is accepted."""
        middleware = CorrelationIDMiddleware(trusted_sources=["2001:db8::/32"])
        assert "2001:db8::/32" in middleware.trusted_sources

    def test_mixed_valid_sources_accepted(self) -> None:
        """Verify mix of valid IPv4/IPv6 addresses and CIDRs accepted."""
        sources = ["10.0.0.1", "10.0.0.0/8", "::1", "2001:db8::/32"]
        middleware = CorrelationIDMiddleware(trusted_sources=sources)
        assert middleware.trusted_sources == frozenset(sources)


class TestTrustedSourceIntegration:
    """Tests for trusted source integration in process_request."""

    def _create_client(
        self,
        trusted_sources: list[str] | None = None,
        generator: typ.Callable[[], str] | None = None,
    ) -> falcon.testing.TestClient:
        """Create a test client with the configured middleware."""
        middleware = CorrelationIDMiddleware(
            trusted_sources=trusted_sources,
            generator=generator or (lambda: "generated-id"),
        )
        app = falcon.App(middleware=[middleware])
        app.add_route("/correlation", CorrelationEchoResource())
        return falcon.testing.TestClient(app)

    def _assert_no_correlation_id(self, response: falcon.testing.Result) -> None:
        """Assert that the response indicates no correlation ID was set.

        Parameters
        ----------
        response : falcon.testing.Result
            The response object from a simulated request.

        """
        assert response.json["has_correlation_id"] is False
        assert response.json["correlation_id"] is None

    def test_trusted_source_accepts_incoming_id(self) -> None:
        """Verify incoming ID is accepted from trusted source.

        Note: Falcon's TestClient uses 127.0.0.1 as remote_addr by default.
        """
        client = self._create_client(trusted_sources=["127.0.0.1"])
        response = client.simulate_get(
            "/correlation",
            headers={"X-Correlation-ID": "incoming-id"},
        )
        assert response.json["correlation_id"] == "incoming-id"

    @pytest.mark.parametrize(
        ("test_id", "trusted_sources", "headers"),
        [
            pytest.param(
                "untrusted_source",
                ["10.0.0.1"],
                {"X-Correlation-ID": "incoming-id"},
                id="untrusted_source",
            ),
            pytest.param(
                "no_trusted_sources",
                [],
                {"X-Correlation-ID": "incoming-id"},
                id="no_trusted_sources",
            ),
            pytest.param(
                "missing_header",
                ["127.0.0.1"],
                None,
                id="missing_header",
            ),
            pytest.param(
                "empty_header",
                ["127.0.0.1"],
                {"X-Correlation-ID": ""},
                id="empty_header",
            ),
        ],
    )
    def test_scenarios_with_no_correlation_id(
        self,
        test_id: str,
        trusted_sources: list[str],
        headers: dict[str, str] | None,
    ) -> None:
        """Verify scenarios where no correlation ID should be set.

        Tests various conditions that result in no correlation_id being set
        on the request context: untrusted sources, empty trusted sources,
        missing headers, and empty headers.

        Note: ID generation will be added in task 2.2. For now, these
        scenarios result in no correlation_id being set.
        """
        client = self._create_client(trusted_sources=trusted_sources)
        response = client.simulate_get("/correlation", headers=headers)
        self._assert_no_correlation_id(response)

    def test_cidr_trusted_source_accepts_incoming_id(self) -> None:
        """Verify CIDR matching accepts incoming ID."""
        client = self._create_client(trusted_sources=["127.0.0.0/8"])
        response = client.simulate_get(
            "/correlation",
            headers={"X-Correlation-ID": "cidr-matched-id"},
        )
        assert response.json["correlation_id"] == "cidr-matched-id"
