"""The address advertised over mDNS must never be loopback (HA would store it and try to reach itself)."""
import asyncio
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import satellite_protocol
from satellite_protocol import SatelliteServer, find_local_ipv4


class FakeSocket:
    def __init__(self, address=None, error=None):
        self.address, self.error = address, error

    def connect(self, target):
        if self.error:
            raise self.error

    def getsockname(self):
        return (self.address, 12345)

    def close(self):
        pass


def adapters(*addresses):
    ips = [types.SimpleNamespace(ip=a, is_IPv4=True) for a in addresses]
    return [types.SimpleNamespace(ips=ips)]


def test_uses_the_address_the_os_would_route_with():
    with patch('socket.socket', return_value=FakeSocket('192.168.1.20')):
        assert find_local_ipv4() == '192.168.1.20'


def test_no_default_route_falls_back_to_an_adapter_address():
    with patch('socket.socket', return_value=FakeSocket(error=OSError('network unreachable'))), \
         patch('ifaddr.get_adapters', return_value=adapters('127.0.0.1', '169.254.3.4', '192.168.1.20')):
        assert find_local_ipv4() == '192.168.1.20'


def test_loopback_from_the_os_is_not_accepted():
    with patch('socket.socket', return_value=FakeSocket('127.0.0.1')), \
         patch('ifaddr.get_adapters', return_value=adapters('127.0.0.1', '10.0.0.7')):
        assert find_local_ipv4() == '10.0.0.7'


def test_prefers_private_over_public_adapter_addresses():
    with patch('socket.socket', return_value=FakeSocket(error=OSError())), \
         patch('ifaddr.get_adapters', return_value=adapters('93.184.216.34', '192.168.1.5')):
        assert find_local_ipv4() == '192.168.1.5'


def test_nothing_usable_returns_none():
    with patch('socket.socket', return_value=FakeSocket(error=OSError())), \
         patch('ifaddr.get_adapters', return_value=adapters('127.0.0.1', '169.254.1.1')):
        assert find_local_ipv4() is None


def test_mdns_is_not_registered_without_a_lan_address():
    server = SatelliteServer('GLaSSIST-Test', MagicMock(), lambda *a, **k: None, lambda: None)
    zeroconf = MagicMock()
    zeroconf.AsyncZeroconf.return_value.async_register_service = AsyncMock()
    with patch.object(satellite_protocol, 'find_local_ipv4', return_value=None), \
         patch.dict('sys.modules', {'zeroconf.asyncio': zeroconf}):
        asyncio.run(server._register_mdns())
    zeroconf.AsyncZeroconf.assert_not_called()
    assert server._zeroconf is None or server._zeroconf_info is None
