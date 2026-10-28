"""Existing server monitoring is configured without replacing its Incus identity."""
from unittest.mock import AsyncMock, patch

import asyncssh
import pytest
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.scottibyte_incus.const import DOMAIN

pytestmark = pytest.mark.usefixtures('enable_custom_integrations')


@pytest.mark.asyncio
async def test_enable_and_disable_existing_host_metrics_preserves_entry(hass):
    assert await async_setup_component(hass, DOMAIN, {})
    entry = MockConfigEntry(domain=DOMAIN, title='Storm', unique_id='pinned-incus-identity', data={
        'host': '192.168.1.10', 'api_port': 8443, 'projects': ['default'], 'credential_id': 'original',
        'fingerprint': 'original-pin', 'server_name': 'Storm'})
    entry.add_to_hass(hass)
    original_id = entry.entry_id
    config = {'credential_id': 'metrics-new', 'host': '192.168.1.10', 'port': 22, 'username': 'scott', 'marker': 'ha-scottibyte-host-new'}
    host_key = asyncssh.generate_private_key('ssh-ed25519').convert_to_public()
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={'source': 'reconfigure', 'entry_id': entry.entry_id})
    flow = await hass.config_entries.flow.async_configure(flow['flow_id'], {'next_step_id': 'host_metrics'})
    assert flow['step_id'] == 'host_metrics'
    with patch('custom_components.scottibyte_incus.config_flow.discover_server', new=AsyncMock(return_value=host_key)):
        flow = await hass.config_entries.flow.async_configure(flow['flow_id'], {'enabled': True, 'ssh_port': 22, 'username': 'scott', 'password': 'setup-secret'})
    assert flow['step_id'] == 'confirm_host'
    assert flow['description_placeholders']['fingerprint'] == host_key.get_fingerprint()
    with patch('custom_components.scottibyte_incus.config_flow.install_host_metrics', new=AsyncMock(return_value=config)) as installer, patch.object(hass.config_entries, 'async_reload', new=AsyncMock(return_value=True)):
        flow = await hass.config_entries.flow.async_configure(flow['flow_id'], {})
        await hass.async_block_till_done()
        installer.assert_awaited_once()
    assert flow['type'] == 'abort' and flow['reason'] == 'reconfigure_successful'
    assert entry.entry_id == original_id and entry.unique_id == 'pinned-incus-identity'
    assert entry.data['credential_id'] == 'original'
    assert entry.data['host_metrics'] == config
    assert 'setup-secret' not in str(entry.data)
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={'source': 'reconfigure', 'entry_id': entry.entry_id})
    flow = await hass.config_entries.flow.async_configure(flow['flow_id'], {'next_step_id': 'host_metrics'})
    with patch('custom_components.scottibyte_incus.host_metrics.HostMonitor.remove', new=AsyncMock()) as remove, patch.object(hass.config_entries, 'async_reload', new=AsyncMock(return_value=True)):
        flow = await hass.config_entries.flow.async_configure(flow['flow_id'], {'enabled': False, 'ssh_port': 22})
        await hass.async_block_till_done()
        remove.assert_awaited_once()
    assert flow['reason'] == 'reconfigure_successful'
    assert entry.data['host_metrics'] is None
    assert entry.data['credential_id'] == 'original'
