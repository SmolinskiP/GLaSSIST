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
    assert server._zeroconf is None and server._zeroconf_info is None


class RoutingSocket(FakeSocket):
    """Routes only to the given targets, like a PC with a LAN address but no default gateway."""
    routes = {}

    def connect(self, target):
        if target[0] not in self.routes:
            raise OSError('network unreachable')
        self.address = self.routes[target[0]]


@pytest.mark.parametrize("host, expected", [
    ("192.168.1.10:8123", "192.168.1.10"), ("http://192.168.1.10:8123", "192.168.1.10"),
    ("192.168.1.10", "192.168.1.10"), ("homeassistant.local:8123", None), ("", None),
    ("[fe80::1]:8123", None),
])
def test_ha_host_ip_literal_is_used_for_routing(host, expected):
    with patch.dict('os.environ', {'HA_HOST': host}), patch('utils._read_from_env_file', return_value=None):
        assert satellite_protocol._ha_host_ipv4() == expected


def test_route_to_home_assistant_works_without_a_default_gateway():
    RoutingSocket.routes = {'192.168.1.10': '192.168.1.20'}
    with patch.dict('os.environ', {'HA_HOST': '192.168.1.10:8123'}), \
         patch('utils._read_from_env_file', return_value=None), \
         patch('socket.socket', side_effect=lambda *a: RoutingSocket()), \
         patch('ifaddr.get_adapters', side_effect=AssertionError('adapters must not be guessed')):
        assert find_local_ipv4() == '192.168.1.20'


def test_several_adapters_are_not_guessed():
    """Hyper-V/WSL or VirtualBox adapters must not be advertised instead of the real LAN one."""
    with patch('socket.socket', return_value=FakeSocket(error=OSError())), \
         patch('ifaddr.get_adapters', return_value=adapters('172.30.32.1', '192.168.56.1', '192.168.1.20')):
        assert find_local_ipv4() is None


def test_ipv6_adapter_entries_are_ignored():
    ips = [types.SimpleNamespace(ip=('fe80::1', 0, 3), is_IPv4=False),
           types.SimpleNamespace(ip='192.168.1.20', is_IPv4=True)]
    with patch('socket.socket', return_value=FakeSocket(error=OSError())), \
         patch('ifaddr.get_adapters', return_value=[types.SimpleNamespace(ips=ips)]):
        assert find_local_ipv4() == '192.168.1.20'


def test_unspecified_address_from_the_os_is_not_accepted():
    with patch('socket.socket', return_value=FakeSocket('0.0.0.0')), \
         patch('ifaddr.get_adapters', return_value=adapters()):
        assert find_local_ipv4() is None


def _zeroconf_modules():
    module = MagicMock()
    module.AsyncZeroconf.return_value.async_register_service = AsyncMock()
    module.AsyncZeroconf.return_value.async_unregister_service = AsyncMock()
    module.AsyncZeroconf.return_value.async_close = AsyncMock()
    return module


def test_found_address_is_advertised():
    server = SatelliteServer('GLaSSIST Test', MagicMock(), lambda *a, **k: None, lambda: None, port=6055)
    zeroconf = _zeroconf_modules()
    with patch.object(satellite_protocol, 'find_local_ipv4', return_value='192.168.1.20'), \
         patch.dict('sys.modules', {'zeroconf': zeroconf, 'zeroconf.asyncio': zeroconf}):
        asyncio.run(server._register_mdns())
    info = zeroconf.ServiceInfo.call_args.kwargs
    assert info['addresses'] == [bytes([192, 168, 1, 20])] and info['port'] == 6055
    zeroconf.AsyncZeroconf.return_value.async_register_service.assert_awaited_once()


def test_registration_is_retried_until_the_network_is_up():
    server = SatelliteServer('GLaSSIST-Test', MagicMock(), lambda *a, **k: None, lambda: None)
    zeroconf = _zeroconf_modules()
    answers = iter([None, None, None, '192.168.1.20', '192.168.1.20'])

    async def run():
        await server._register_mdns()
        assert server._mdns_retry is not None
        await server._mdns_retry

    with patch.object(satellite_protocol, 'find_local_ipv4', side_effect=lambda: next(answers)), \
         patch.object(satellite_protocol, 'MDNS_RETRY_SECONDS', 0), \
         patch.dict('sys.modules', {'zeroconf': zeroconf, 'zeroconf.asyncio': zeroconf}):
        asyncio.run(run())
    zeroconf.AsyncZeroconf.return_value.async_register_service.assert_awaited_once()
    assert server._mdns_retry is None


def test_stop_cancels_a_pending_retry():
    server = SatelliteServer('GLaSSIST-Test', MagicMock(), lambda *a, **k: None, lambda: None)
    zeroconf = _zeroconf_modules()

    async def run():
        await server._register_mdns()
        retry = server._mdns_retry
        await server.stop()
        await asyncio.sleep(0)
        return retry

    with patch.object(satellite_protocol, 'find_local_ipv4', return_value=None), \
         patch.dict('sys.modules', {'zeroconf': zeroconf, 'zeroconf.asyncio': zeroconf}):
        retry = asyncio.run(run())
    assert retry.cancelled() and server._mdns_retry is None
    zeroconf.AsyncZeroconf.assert_not_called()
