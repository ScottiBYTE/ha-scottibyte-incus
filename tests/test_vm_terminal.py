"""VM guest terminals use the authenticated agent exec path and clean up failures."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import aiohttp
import pytest

from custom_components.scottibyte_incus import websocket as ws
from custom_components.scottibyte_incus.api import IncusError
from custom_components.scottibyte_incus.const import DOMAIN
from custom_components.scottibyte_incus.models import normalize_instance


@pytest.mark.parametrize(('os_name', 'supported'), [('Ubuntu', True), ('Debian', True), ('', True), ('Windows 11', False), ('FreeBSD', False)])
def test_vm_terminal_policy(os_name, supported):
    item = normalize_instance({'name': 'vm', 'type': 'virtual-machine', 'config': {'image.os': os_name}}, 'default')
    assert item['terminal_supported'] is supported


@pytest.mark.asyncio
@pytest.mark.parametrize('scenario', ['working', 'agent_down', 'stopped', 'windows'])
async def test_vm_terminal_open_and_cleanup(scenario):
    session = SimpleNamespace(data=SimpleNamespace(receive=AsyncMock(return_value=SimpleNamespace(type=aiohttp.WSMsgType.CLOSED))), close=AsyncMock())
    client = SimpleNamespace(state=AsyncMock(return_value={'status': 'Stopped' if scenario == 'stopped' else 'Running'}), terminal=AsyncMock(return_value=session))
    if scenario == 'agent_down':
        client.terminal.side_effect = IncusError("VM agent isn't currently running")
    item = {'name': 'Desktop-2404', 'project': 'default', 'type': 'virtual-machine', 'terminal_supported': scenario != 'windows'}
    coordinator = SimpleNamespace(snapshot={'online': True, 'instances': [item]}, client=client, entry=SimpleNamespace(title='Cloud'))
    tasks = []

    def background(coro, name):
        task = asyncio.create_task(coro)
        tasks.append(task)
        return task

    hass = SimpleNamespace(data={DOMAIN: {'coordinators': {'cloud': coordinator}, 'terminals': {}}}, async_create_background_task=background)
    connection = SimpleNamespace(user=SimpleNamespace(id='admin', is_admin=True, is_active=True), subscriptions={}, send_result=Mock(), send_event=Mock(), send_error=Mock())
    handler = ws.terminal_open
    while hasattr(handler, '__wrapped__'):
        handler = handler.__wrapped__
    await handler(hass, connection, {'id': 9, 'server': 'cloud', 'name': 'Desktop-2404', 'project': 'default', 'cols': 100, 'rows': 30})
    if tasks:
        await asyncio.gather(*tasks)
    assert not hass.data[DOMAIN]['terminals']
    assert not connection.subscriptions
    if scenario == 'working':
        client.terminal.assert_awaited_once_with('default', 'Desktop-2404', 100, 30)
        connection.send_error.assert_not_called()
        session.close.assert_awaited_once()
    else:
        message = connection.send_error.call_args.args[2]
        assert {'agent_down': 'Incus agent', 'stopped': 'Start the instance', 'windows': 'Linux VMs'}[scenario] in message
        if scenario in ('stopped', 'windows'):
            client.terminal.assert_not_awaited()
