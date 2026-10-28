"""One coordinator per configured server/cluster, retaining stale inventory."""

import logging
import time
from datetime import timedelta

from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import IncusError
from .const import DOMAIN
from .dns import ReverseDNS
from .host_metrics import HostMonitor
from .models import counts, normalize_instance, utc_now

_LOGGER = logging.getLogger(__name__)


class IncusCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client):
        super().__init__(
            hass,
            _LOGGER,
            name=entry.title,
            config_entry=entry,
            update_interval=timedelta(seconds=hass.data[DOMAIN]["dashboard"].get("refresh_seconds", 30)),
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
        self.host_monitor = HostMonitor(hass, entry.data.get("host_metrics"))
        self.dns = ReverseDNS(hass)
        self._sample_at = None
        self._last_saved = 0

    async def load_snapshot(self):
        saved = await self.store.async_load()
        if saved:
            self.snapshot = {**saved, "online": False}
            if saved.get("clustered"):
                member = self.entry.data.get("cluster_member") or self.entry.data.get("server_name")
                self.snapshot["instances"] = [i for i in saved.get("instances", []) if i.get("location") == member]
                self.snapshot["counts"] = counts(self.snapshot["instances"])

    async def _async_update_data(self):
        if hasattr(self, "host_monitor"):
            self.snapshot["host_metrics"] = await self.host_monitor.collect()
        try:
            if hasattr(self.client, "set_endpoints"):
                self.client.set_endpoints(self.snapshot.get("cluster_members", []))
            info, raw = await self.client.inventory(self.entry.data["projects"])
            env = info.get("environment", {})
            member = self.entry.data.get("cluster_member") or self.entry.data.get("server_name") or env.get("server_name")
            clustered = env.get("server_clustered", False)
            if clustered:
                if not member:
                    raise IncusError("Cluster member identity is unavailable")
                member_info = next((m for m in info.get("cluster_members", []) if m.get("server_name") == member), None)
                if member_info and str(member_info.get("status", "")).lower() != "online":
                    raise IncusError("Cluster member is offline")
                raw = [(project, item) for project, item in raw if item.get("location") == member]
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
                "host_metrics": self.snapshot.get("host_metrics", {"configured": False, "online": False}),
                "instances": instances,
                "counts": counts(instances),
                "last_success": utc_now(),
                "version": env.get("server_version", ""),
                "clustered": env.get("server_clustered", False),
                "server_name": member if clustered else env.get("server_name", self.entry.title),
                "active_endpoint": getattr(self.client, "url", ""),
                "cluster_id": self.entry.data.get("fingerprint", "") if clustered else "",
                "cluster_member": member if clustered else "",
                "cluster_members": [{"name": m.get("server_name", ""), "url": m.get("url", ""), "status": m.get("status", "Unknown"), "roles": m.get("roles", [])} for m in info.get("cluster_members", [])],
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
        return {
            **self.snapshot,
            "id": self.entry.entry_id,
            "name": self.entry.title,
            "host": self.entry.data["host"],
            "instances": self.snapshot["instances"] if self.snapshot["online"] else [],
        }
