"""Snapshot mutation payloads, operation completion, and path validation."""
from unittest.mock import AsyncMock

import pytest

from custom_components.scottibyte_incus.api import IncusClient, IncusError


@pytest.mark.asyncio
@pytest.mark.parametrize("action,method,suffix,payload", [
    ("create", "POST", "/snapshots", {"name": "before", "stateful": False}),
    ("rename", "POST", "/snapshots/before", {"name": "after"}),
    ("delete", "DELETE", "/snapshots/before", None),
    ("restore", "PUT", "", {"restore": "before", "stateful": False}),
])
async def test_snapshot_mutations_wait_for_completion(action, method, suffix, payload):
    client = IncusClient.__new__(IncusClient)
    client.request = AsyncMock(return_value={"operation": "/1.0/operations/test"})
    client.metadata = AsyncMock(return_value={"status_code": 200})
    await client.snapshot_action("lab", "Guest", action, "before", "after")
    client.request.assert_awaited_once_with(method, "/1.0/instances/Guest" + suffix, params={"project": "lab"}, payload=payload)
    client.metadata.assert_awaited_once_with("/1.0/operations/test/wait", params={"project": "lab", "timeout": 300}, timeout=310)
    client.metadata.return_value = {"status_code": 400, "err": "storage failure"}
    with pytest.raises(IncusError, match="storage failure"):
        await client.snapshot_action("lab", "Guest", action, "before", "after")


@pytest.mark.asyncio
async def test_snapshot_paths_rejected_before_request():
    client = IncusClient.__new__(IncusClient)
    client.request = AsyncMock()
    for name in ("../other", "bad/name", "", "bad..name"):
        with pytest.raises(IncusError):
            await client.snapshot_action("lab", "Guest", "delete", name)
    client.request.assert_not_awaited()
