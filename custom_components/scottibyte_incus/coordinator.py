"""One coordinator per configured server/cluster, retaining stale inventory."""

import logging
import time
from datetime import timedelta

from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .dns import ReverseDNS
from .models import counts, normalize_instance, utc_now

_LOGGER = logging.getLogger(__name__)


class IncusCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client):
        super().__init__(
            hass,
            _LOGGER,
            name=entry.title,
            config_entry=entry,
            update_interval=timedelta(seconds=entry.options.get("poll_seconds", 30)),
        )
        self.entry, self.client = entry, client
        self.store = Store(hass, 1, f"{DOMAIN}.inventory.{entry.entry_id}")
        self.snapshot = {
            "online": False,
            "instances": [],
            "counts": counts([]),
            "last_success": None,
            "version": "",
            "clustered": False,
        }
        self.dns = ReverseDNS(hass)
        self._sample_at = None
        self._last_saved = 0

    async def load_snapshot(self):
        saved = await self.store.async_load()
        if saved:
            self.snapshot = {**saved, "online": False}

    async def _async_update_data(self):
        try:
            info, raw = await self.client.inventory(self.entry.data["projects"])
            now = time.monotonic()
            elapsed = now - self._sample_at if self._sample_at is not None else 0
            previous = {(i["project"], i["name"]): i for i in self.snapshot["instances"]} if self._sample_at else {}
            instances = [
                normalize_instance(item, project, previous.get((project, item["name"])), elapsed,
                    info.get("host_cpu_counts", {}).get(str(item.get("location") or "") if info.get("environment", {}).get("server_clustered") else ""))
                for project, item in raw
            ]
            self.dns.apply(instances)
            env = info.get("environment", {})
            self.snapshot = {
                "online": True,
                "instances": instances,
                "counts": counts(instances),
                "last_success": utc_now(),
                "version": env.get("server_version", ""),
                "clustered": env.get("server_clustered", False),
                "server_name": env.get("server_name", self.entry.title),
            }
            self._sample_at = now
            # Checkpoint at most every two minutes, including during steady polling.
            if now - self._last_saved >= 120:
                await self.store.async_save(self.snapshot)
                self._last_saved = now
        except Exception as err:
            if self.snapshot["online"]:
                _LOGGER.warning("Incus server %s became unavailable (%s)", self.entry.title, type(err).__name__)
            self.snapshot = {**self.snapshot, "online": False}
            self._sample_at = None
        return self.snapshot

    def public_data(self):
        return {"id": self.entry.entry_id, "name": self.entry.title, **self.snapshot}
