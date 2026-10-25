"""Pure inventory normalization; no Home Assistant dependencies."""

import re
from datetime import datetime, timezone


def size_bytes(value):
    """Parse Incus byte limits; percentages are deliberately unknown."""
    if value is None or value == "":
        return None
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([KMGTPE]?)(i?B)?\s*", str(value), re.I)
    if not match:
        return None
    number, unit, suffix = match.groups()
    power = "KMGTPE".find(unit.upper()) + 1 if unit else 0
    base = 1024 if suffix and suffix.lower() == "ib" else 1000
    return int(float(number) * base**power)


def normalize_instance(raw, project, previous=None, elapsed=0):
    """Normalize recursion=2 records, leaving unreported values unset."""
    state = raw.get("state") or {}
    config = raw.get("expanded_config") or raw.get("config") or {}
    devices = raw.get("expanded_devices") or raw.get("devices") or {}
    networks = state.get("network") or {}
    ips, macs = [], []
    for nic, data in networks.items():
        if nic == "lo" or data.get("type") == "loopback":
            continue
        if data.get("hwaddr"):
            macs.append(data["hwaddr"])
        for address in data.get("addresses") or []:
            if address.get("scope") in ("global", "site") and address.get("address"):
                ips.append(address["address"])
    status = raw.get("status") or state.get("status") or "Unknown"
    cpu_ns = (state.get("cpu") or {}).get("usage")
    cpu = None
    if status == "Running" and previous and elapsed > 0 and cpu_ns is not None:
        old = previous.get("cpu_ns")
        if old is not None and cpu_ns >= old:
            cpu = round((cpu_ns - old) / (elapsed * 1e9) * 100, 1)
    root = next((d for d in devices.values() if d.get("type") == "disk" and d.get("path") == "/"), {})
    disks = state.get("disk") or {}
    root_state = disks.get("root") or next(iter(disks.values()), {})
    return {
        "name": raw["name"],
        "project": project,
        "type": raw.get("type", "container"),
        "location": raw.get("location", ""),
        "status": status,
        "status_code": raw.get("status_code", state.get("status_code")),
        "ips": sorted(set(ips)),
        "macs": sorted(set(macs)),
        "dns": config.get("user.dns_name", ""),
        "cpu_ns": cpu_ns,
        "cpu_percent": cpu,
        "memory_bytes": (state.get("memory") or {}).get("usage"),
        "memory_limit": size_bytes(config.get("limits.memory")),
        "disk_bytes": root_state.get("usage"),
        "disk_limit": size_bytes(root.get("size")),
    }


def counts(instances):
    return {
        "total": len(instances),
        "running": sum(i["status"] == "Running" for i in instances),
        "stopped": sum(i["status"] == "Stopped" for i in instances),
        "containers": sum(i["type"] == "container" for i in instances),
        "vms": sum(i["type"] == "virtual-machine" for i in instances),
    }


def utc_now():
    return datetime.now(timezone.utc).isoformat()
