"""Reverse DNS caching and explicit-name precedence."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.scottibyte_incus.dns import ReverseDNS


@pytest.mark.asyncio
async def test_reverse_dns_cache_and_missing_records():
    lookup = AsyncMock(side_effect=[('Webcore.', [], []), OSError('no PTR')])
    hass = SimpleNamespace(
        async_add_executor_job=lookup,
        async_create_background_task=lambda coro, name: asyncio.create_task(coro),
    )
    dns = ReverseDNS(hass)
    items = [{'dns': '', 'ips': ['172.16.1.235']}, {'dns': 'custom.example', 'ips': ['172.16.1.236']}]
    dns.apply(items)
    await dns.task
    dns.apply(items)
    assert items[0]['dns'] == 'Webcore'
    assert items[1]['dns'] == 'custom.example'
    assert lookup.await_count == 1
    missing = [{'dns': '', 'ips': ['172.16.1.237']}]
    dns.apply(missing)
    await dns.task
    dns.apply(missing)
    assert missing[0]['dns'] == ''
    assert lookup.await_count == 2
    await dns.close()
