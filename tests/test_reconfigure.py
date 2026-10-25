"""Reconfiguration preserves config-entry/entity identity and validates first."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.scottibyte_incus.api import certificate_fingerprint
from custom_components.scottibyte_incus.bootstrap import generate_certificate, write_credentials
from custom_components.scottibyte_incus.const import DOMAIN

pytestmark = pytest.mark.usefixtures('enable_custom_integrations')


async def make_entry(hass, tmp_path):
    hass.config.config_dir = str(tmp_path)
    assert await async_setup_component(hass, DOMAIN, {})
    cert, key = generate_certificate()
    directory = Path(hass.config.path('.storage', DOMAIN, 'original'))
    directory.mkdir(parents=True)
    write_credentials(directory/'client.crt', directory/'client.key', cert, key)
    (directory/'server.crt').write_text(cert)
    entry = MockConfigEntry(domain=DOMAIN, title='Lab', unique_id=certificate_fingerprint(cert), data={
        'host': '192.168.1.10', 'api_port': 8443, 'projects': ['default'], 'credential_id': 'original',
        'fingerprint': certificate_fingerprint(cert), 'server_name': 'Lab'})
    entry.add_to_hass(hass)
    return entry, directory, cert


@pytest.mark.asyncio
async def test_address_projects_validated_before_update(hass, tmp_path):
    entry, directory, cert = await make_entry(hass, tmp_path)
    original_id = entry.entry_id
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={'source':'reconfigure', 'entry_id':entry.entry_id})
    assert flow['step_id'] == 'reconfigure'
    flow = await hass.config_entries.flow.async_configure(flow['flow_id'], {'next_step_id':'connection'})
    client = SimpleNamespace(inventory=AsyncMock(side_effect=OSError('offline')), close=AsyncMock())
    with patch('custom_components.scottibyte_incus.config_flow.IncusClient', return_value=client), patch.object(
        hass.config_entries, 'async_reload', new=AsyncMock(return_value=True)) as reload:
        flow = await hass.config_entries.flow.async_configure(flow['flow_id'], {'host':'192.168.1.20', 'api_port':8443, 'projects':'lab'})
        assert flow['errors']['base'] == 'connection_failed'
        assert entry.data['host'] == '192.168.1.10'
        reload.assert_not_awaited()
        client.inventory.side_effect = None
        flow = await hass.config_entries.flow.async_configure(flow['flow_id'], {'host':'192.168.1.20', 'api_port':8443, 'projects':'lab'})
        await hass.async_block_till_done()
        assert flow['type'] == 'abort' and flow['reason'] == 'reconfigure_successful'
        assert entry.entry_id == original_id and entry.unique_id == certificate_fingerprint(cert)
        assert entry.data['projects'] == ['lab'] and entry.data['credential_id'] == 'original'
        reload.assert_awaited_once_with(entry.entry_id)


@pytest.mark.asyncio
async def test_trust_renewal_keeps_entry_and_retires_previous_identity(hass, tmp_path):
    entry, old_directory, old_cert = await make_entry(hass, tmp_path)
    original_id = entry.entry_id
    new_server_cert, _ = generate_certificate()
    client = SimpleNamespace(metadata=AsyncMock(return_value=[{'fingerprint':certificate_fingerprint(old_cert)}]),
                             request=AsyncMock(), close=AsyncMock())
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={'source':'reconfigure', 'entry_id':entry.entry_id})
    flow = await hass.config_entries.flow.async_configure(flow['flow_id'], {'next_step_id':'renew_trust'})
    flow = await hass.config_entries.flow.async_configure(flow['flow_id'], {'next_step_id':'token'})
    with patch('custom_components.scottibyte_incus.config_flow.enroll_token', new=AsyncMock(return_value=(new_server_cert, {'environment':{'server_name':'Lab'}}))), patch(
        'custom_components.scottibyte_incus.config_flow.IncusClient', return_value=client), patch.object(
        hass.config_entries, 'async_reload', new=AsyncMock(return_value=True)):
        flow = await hass.config_entries.flow.async_configure(flow['flow_id'], {'name':'Lab', 'host':'192.168.1.20', 'api_port':8443, 'projects':'default', 'token':'temporary'})
        await hass.async_block_till_done()
    assert flow['type'] == 'abort' and flow['reason'] == 'reconfigure_successful'
    assert entry.entry_id == original_id and entry.unique_id == certificate_fingerprint(new_server_cert)
    assert entry.data['credential_id'] != 'original'
    assert 'token' not in entry.data
    assert not old_directory.exists()
    client.request.assert_awaited_once_with('DELETE', f'/1.0/certificates/{certificate_fingerprint(old_cert)}', timeout=10)
