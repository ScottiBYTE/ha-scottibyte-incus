"""Metric denominator, member targeting, and interface-selection regressions."""
from unittest.mock import AsyncMock

import pytest

from custom_components.scottibyte_incus.api import IncusClient, IncusError
from custom_components.scottibyte_incus.models import normalize_instance


def raw_instance(location=''):
    return {'name': 'DockerGuest', 'location': location, 'status': 'Running',
            'expanded_devices': {'eth0': {'type': 'nic', 'name': 'eth0'}},
            'state': {'cpu': {'usage': 77_200_000_000}, 'network': {
                'docker0': {'type': 'bridge', 'addresses': [{'scope': 'global', 'address': '172.17.0.1'}]},
                'eth0': {'addresses': [{'scope': 'global', 'address': '192.168.50.20'},
                                      {'scope': 'global', 'address': '2001:db8::2'}]}}}}


def test_cpu_host_share_and_preferred_guest_ip():
    raw = raw_instance()
    item = normalize_instance(raw, 'default', {'cpu_ns': 1_000_000_000}, 10, 32)
    assert item['cpu_percent'] == 762
    assert item['cpu_host_percent'] == 23.8
    assert item['cpu_cores_used'] == 7.62
    assert item['primary_ip'] == '192.168.50.20'
    assert set(item['ips']) == {'172.17.0.1', '192.168.50.20', '2001:db8::2'}
    assert normalize_instance(raw, 'default', {'cpu_ns': 1_000_000_000}, 10)['cpu_host_percent'] is None
    assert normalize_instance(raw, 'default', None, 10, 32)['cpu_host_percent'] is None
    raw['location'] = 'new-member'
    assert normalize_instance(raw, 'default', {'cpu_ns': 1_000_000_000, 'location': 'old-member'}, 10, 32)['cpu_percent'] is None


@pytest.mark.asyncio
async def test_cluster_member_capacity_and_failure_isolation():
    client = IncusClient.__new__(IncusClient)
    client._cpu_cache = {}
    client.url = client.primary_url = "https://member-a:8443"
    client.endpoints = [client.url]

    async def metadata(path, **kwargs):
        if path == '/1.0':
            return {'auth': 'trusted', 'environment': {'server_clustered': True}}
        if path == '/1.0/cluster/members':
            return []
        if path == '/1.0/instances':
            return [raw_instance('member-a'), {**raw_instance('member-b'), 'name': 'SecondGuest'}]
        if path == '/1.0/resources':
            if kwargs['params']['target'] == 'member-b':
                raise IncusError('offline')
            return {'cpu': {'total': 32}}
        raise AssertionError(path)

    client.metadata = AsyncMock(side_effect=metadata)
    info, rows = await client.inventory(['default'])
    assert info['host_cpu_counts'] == {'member-a': 32, 'member-b': None}
    assert len(rows) == 2
    count = client.metadata.await_count
    await client.inventory(['default'])
    assert client.metadata.await_count == count + 3  # resources are cached, including failures
