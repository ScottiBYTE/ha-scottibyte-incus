"""Cluster member identities, member-only inventory, and safe endpoint selection."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.scottibyte_incus.api import IncusClient, IncusError, certificate_fingerprint
from custom_components.scottibyte_incus.bootstrap import generate_certificate
from custom_components.scottibyte_incus.config_flow import IncusConfigFlow
from custom_components.scottibyte_incus.coordinator import IncusCoordinator


@pytest.mark.asyncio
async def test_three_members_can_share_certificate_and_legacy_entry_is_preserved(tmp_path):
    pem, key = generate_certificate()
    fingerprint = certificate_fingerprint(pem)
    legacy = SimpleNamespace(data={'fingerprint': fingerprint, 'server_name': 'cloud'}, unique_id=fingerprint)
    entries = [legacy]
    for member in ('fog', 'incus-member'):
        flow = IncusConfigFlow()
        flow.hass = SimpleNamespace(config=SimpleNamespace(path=lambda *parts: str(tmp_path.joinpath(*parts))), async_add_executor_job=AsyncMock(side_effect=lambda fn, *args: fn(*args)))
        with patch.object(flow, '_async_current_entries', return_value=entries), patch.object(flow, 'async_set_unique_id', new=AsyncMock()) as identity, patch.object(flow, '_abort_if_unique_id_configured'), patch.object(flow, 'async_create_entry', side_effect=lambda **kwargs: kwargs):
            result = await flow._finish({'host': member, 'api_port': 8443, 'projects': '*'}, pem, {'environment': {'server_clustered': True, 'server_name': member}}, pem, key)
            identity.assert_awaited_once_with(f'{fingerprint}:{member}')
            assert result['data']['cluster_member'] == member
            assert result['data']['fingerprint'] == fingerprint
            assert result['data']['credential_id'] not in [e.data.get('credential_id') for e in entries]
            entries.append(SimpleNamespace(data=result['data']))
    assert legacy.unique_id == fingerprint
    # An alias for an existing legacy member must still be rejected and its new trust retired.
    with patch.object(flow, '_async_current_entries', return_value=entries), patch.object(flow, '_discard_enrollment', new=AsyncMock()) as cleanup, patch.object(flow, 'async_abort', return_value={'reason': 'already_configured'}):
        result = await flow._finish({'host': 'cloud-alias', 'api_port': 8443, 'projects': '*'}, pem, {'environment': {'server_clustered': True, 'server_name': 'cloud'}}, pem, key)
        assert result['reason'] == 'already_configured'
        cleanup.assert_awaited_once()


@pytest.mark.asyncio
async def test_member_inventory_does_not_duplicate_other_members():
    from custom_components.scottibyte_incus.models import counts

    info = {'environment': {'server_clustered': True, 'server_name': 'fog'}, 'cluster_members': [{'server_name': 'cloud', 'status': 'Online', 'url': 'https://cloud:8443'}, {'server_name': 'fog', 'status': 'Online', 'url': 'https://fog:8443'}]}
    raw = [('default', {'name': 'one', 'location': 'cloud', 'status': 'Running'}), ('default', {'name': 'two', 'location': 'fog', 'status': 'Running'})]
    totals = []
    for member in ('cloud', 'fog'):
        obj = SimpleNamespace(client=SimpleNamespace(inventory=AsyncMock(return_value=(info, raw)), url='https://fog:8443'), entry=SimpleNamespace(data={'projects': ['*'], 'server_name': member, 'fingerprint': 'cluster'}, title=member), snapshot={'online': False, 'instances': [], 'counts': counts([])}, _sample_at=None, _last_saved=0, store=SimpleNamespace(async_save=AsyncMock()), dns=SimpleNamespace(apply=lambda _: None))
        result = await IncusCoordinator._async_update_data(obj)
        assert result['online']
        assert len(result['instances']) == 1
        assert result['instances'][0]['location'] == member
        assert result['cluster_member'] == member
        totals.append(result['counts']['total'])
    assert sum(totals) == 2


@pytest.mark.asyncio
async def test_endpoint_failover_only_probes_reads_and_retains_pin():
    client = IncusClient.__new__(IncusClient)
    client.url = client.primary_url = 'https://cloud:8443'
    client.set_endpoints([{'url': 'https://fog:8443'}, {'url': 'http://unsafe:8443'}, {'url': 'https://user:pass@bad:8443'}, {'url': 'https://bad:8443/path'}])
    assert client.endpoints == ['https://cloud:8443', 'https://fog:8443']
    observed = []

    async def metadata(path, **kwargs):
        observed.append((client.url, path))
        if client.url == client.primary_url:
            raise OSError('node down')
        return {'auth': 'trusted'}

    client.metadata = AsyncMock(side_effect=metadata)
    assert await client.select_endpoint() == {'auth': 'trusted'}
    assert client.url == 'https://fog:8443'
    assert observed == [('https://cloud:8443', '/1.0'), ('https://fog:8443', '/1.0')]
    client.metadata = AsyncMock(return_value={'auth': 'untrusted'})
    with pytest.raises(IncusError, match='not trusted'):
        await client.select_endpoint()


@pytest.mark.asyncio
async def test_old_cluster_snapshot_is_filtered_before_first_refresh():
    saved = {'clustered': True, 'online': True, 'instances': [{'name': 'a', 'location': 'cloud', 'type': 'container', 'status': 'Running'}, {'name': 'b', 'location': 'fog', 'type': 'container', 'status': 'Running'}]}
    obj = SimpleNamespace(entry=SimpleNamespace(data={'server_name': 'cloud'}), store=SimpleNamespace(async_load=AsyncMock(return_value=saved)))
    await IncusCoordinator.load_snapshot(obj)
    assert obj.snapshot['online'] is False
    assert obj.snapshot['counts']['total'] == 1
    assert obj.snapshot['instances'][0]['name'] == 'a'


@pytest.mark.asyncio
async def test_offline_member_does_not_become_available_through_healthy_endpoint():
    info = {'environment': {'server_clustered': True, 'server_name': 'fog'}, 'cluster_members': [{'server_name': 'cloud', 'status': 'Offline'}]}
    obj = SimpleNamespace(client=SimpleNamespace(inventory=AsyncMock(return_value=(info, []))), entry=SimpleNamespace(data={'projects': ['*'], 'server_name': 'cloud'}, title='Cloud'), snapshot={'online': True, 'instances': []}, _sample_at=1)
    result = await IncusCoordinator._async_update_data(obj)
    assert result['online'] is False
