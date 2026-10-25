from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from custom_components.scottibyte_incus.coordinator import IncusCoordinator


@pytest.mark.asyncio
async def test_failure_retains_inventory_but_marks_it_stale():
    # Test the actual update routine with a minimal coordinator container.
    client = SimpleNamespace(inventory=AsyncMock(side_effect=OSError("offline")))
    item = {"name": "Assist", "project": "default", "status": "Running"}
    snapshot = {"online": True, "instances": [item], "last_success": "2026-10-25T12:00:00Z", "counts": {"running": 1}}
    obj = SimpleNamespace(
        client=client,
        entry=SimpleNamespace(data={"projects": ["*"]}, title="vmsstorm"),
        snapshot=snapshot,
        _sample_at=10,
    )
    result = await IncusCoordinator._async_update_data(obj)
    assert result["online"] is False
    assert result["instances"] == [item] and result["instances"][0]["status"] == "Running"
    assert result["last_success"] == snapshot["last_success"]
    assert obj._sample_at is None
