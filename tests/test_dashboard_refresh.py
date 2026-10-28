"""Saved refresh changes actual polling and preserves card order."""
import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.scottibyte_incus.const import DOMAIN
from custom_components.scottibyte_incus.dashboard import set_refresh_interval


@pytest.mark.asyncio
async def test_refresh_is_persistent_and_updates_all_coordinators():
    coordinators = [SimpleNamespace(update_interval=timedelta(seconds=30), async_request_refresh=AsyncMock()) for _ in range(3)]
    data = {'dashboard': {'server_order': ['a', 'b'], 'refresh_seconds': 30}, 'dashboard_lock': asyncio.Lock(), 'dashboard_store': SimpleNamespace(async_save=AsyncMock()), 'coordinators': dict(enumerate(coordinators))}
    hass = SimpleNamespace(data={DOMAIN: data})
    saved = await set_refresh_interval(hass, 60)
    assert saved == {'server_order': ['a', 'b'], 'refresh_seconds': 60}
    data['dashboard_store'].async_save.assert_awaited_once_with(saved)
    for coordinator in coordinators:
        assert coordinator.update_interval == timedelta(seconds=60)
        coordinator.async_request_refresh.assert_awaited_once()
    with pytest.raises(ValueError):
        await set_refresh_interval(hass, 1)
    assert data['dashboard']['refresh_seconds'] == 60
