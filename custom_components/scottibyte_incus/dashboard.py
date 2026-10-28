"""Saved dashboard settings, including actual coordinator polling cadence."""
import asyncio
from datetime import timedelta

from .const import DOMAIN

REFRESH_INTERVALS = (10, 30, 60, 300)


async def set_refresh_interval(hass, seconds):
    if type(seconds) is not int or seconds not in REFRESH_INTERVALS:
        raise ValueError('Unsupported refresh interval')
    data = hass.data[DOMAIN]
    async with data['dashboard_lock']:
        updated = {**data['dashboard'], 'refresh_seconds': seconds}
        await data['dashboard_store'].async_save(updated)
        data['dashboard'] = updated
        coordinators = list(data['coordinators'].values())
        for coordinator in coordinators:
            coordinator.update_interval = timedelta(seconds=seconds)
    # Reschedule now, rather than waiting out the old (possibly longer) interval.
    await asyncio.gather(*(c.async_request_refresh() for c in coordinators))
    return updated
