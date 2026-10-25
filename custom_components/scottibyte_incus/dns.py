"""Cached reverse lookups using Home Assistant's system resolver."""

import asyncio
import ipaddress
import socket
import time


class ReverseDNS:
    """Resolve in background with at most four outstanding blocking calls."""

    def __init__(self, hass):
        self.hass = hass
        self.cache = {}
        self.task = None

    def apply(self, instances):
        addresses = set()
        now = time.monotonic()
        self.cache = {ip: value for ip, value in self.cache.items() if value[1] > now}
        for item in instances:
            if item.get("dns"):
                continue
            ips = []
            for value in item.get("ips", []):
                try:
                    address = ipaddress.ip_address(value)
                except ValueError:
                    continue
                if address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified:
                    continue
                ips.append(str(address))
            ips.sort(key=lambda ip: ipaddress.ip_address(ip).version)
            for ip in ips:
                cached = self.cache.get(ip)
                if cached and cached[0]:
                    item["dns"] = cached[0]
                    break
            addresses.update(ip for ip in ips if ip not in self.cache)
        if addresses and (self.task is None or self.task.done()):
            self.task = self.hass.async_create_background_task(self.resolve(sorted(addresses)[:2048]), "Incus reverse DNS")

    async def resolve(self, addresses):
        pending = iter(addresses)

        async def worker():
            for ip in pending:
                try:
                    result = await self.hass.async_add_executor_job(socket.gethostbyaddr, ip)
                    name = result[0].rstrip(".")
                except OSError:
                    name = ""
                self.cache[ip] = (name, time.monotonic() + (600 if name else 60))

        await asyncio.gather(*(worker() for _ in range(4)))

    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
