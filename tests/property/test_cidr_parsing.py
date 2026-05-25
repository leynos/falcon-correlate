"""Property tests for trusted-source CIDR parsing."""

from __future__ import annotations

import ipaddress

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from falcon_correlate import CorrelationIDConfig

type _IpNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network
type _IpAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


@st.composite
def valid_cidr_blocks(draw: st.DrawFn) -> _IpNetwork:
    """Generate valid CIDR blocks with no host bits set."""
    address = draw(st.ip_addresses())
    max_prefix = address.max_prefixlen
    prefix = draw(st.integers(min_value=0, max_value=max_prefix))
    return ipaddress.ip_network((address, prefix), strict=False)


@st.composite
def host_bit_violations(draw: st.DrawFn) -> str:
    """Generate CIDR strings where the address has host bits set."""
    address = draw(st.ip_addresses())
    prefix = draw(st.integers(min_value=0, max_value=address.max_prefixlen - 1))
    network = ipaddress.ip_network((address, prefix), strict=False)
    host_address = _first_host_with_bits_set(network)
    return f"{host_address}/{prefix}"


def _first_host_with_bits_set(network: _IpNetwork) -> _IpAddress:
    """Return an address inside *network* that is not the network address."""
    address_type = type(network.network_address)
    return address_type(int(network.network_address) + 1)


def is_parseable_network(value: str) -> bool:
    """Return whether *value* parses as any IP network shape."""
    try:
        ipaddress.ip_network(value, strict=False)
    except ValueError:
        return False
    return True


@given(cidr=valid_cidr_blocks())
@settings(max_examples=50)
def test_accepts_valid_cidr_blocks(cidr: _IpNetwork) -> None:
    """Valid CIDR blocks are accepted and stored as parsed networks."""
    config = CorrelationIDConfig(trusted_sources=[str(cidr)])

    # CorrelationIDConfig exposes parsed CIDRs only through middleware internals.
    assert config._parsed_networks == (cidr,)


@given(cidr=host_bit_violations())
@settings(max_examples=50)
def test_rejects_cidr_host_bit_violations(cidr: str) -> None:
    """CIDR blocks with host bits set are rejected with a specific message."""
    with pytest.raises(ValueError, match="host bits set"):
        CorrelationIDConfig(trusted_sources=[cidr])


@given(
    value=st.text().filter(lambda text: text.strip() and not is_parseable_network(text))
)
@settings(max_examples=50)
def test_rejects_malformed_cidr_strings(value: str) -> None:
    """Malformed trusted-source strings are rejected."""
    with pytest.raises(ValueError, match="Invalid IP address or CIDR notation"):
        CorrelationIDConfig(trusted_sources=[value])
