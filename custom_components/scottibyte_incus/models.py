"""Pure inventory normalization; no Home Assistant dependencies."""

import ipaddress
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


def preferred_ip(state, devices):
    """Prefer the configured guest NIC over nested Docker/bridge interfaces."""
    configured = {device.get("name") or key for key, device in devices.items() if device.get("type") == "nic"}
    candidates = []
    for nic, data in (state.get("network") or {}).items():
        if nic == "lo" or data.get("type") == "loopback":
            continue
        nested = nic.startswith(("docker", "br-", "veth", "virbr", "cni", "flannel", "kube", "podman"))
        rank = 0 if nic in configured else 2 if nested or data.get("type") == "bridge" else 1
        for item in data.get("addresses") or []:
            try:
                address = ipaddress.ip_address(item.get("address", ""))
            except ValueError:
                continue
            if item.get("scope") not in ("global", "site") or address.is_loopback or address.is_link_local or address.is_unspecified or address.is_multicast:
                continue
            candidates.append((rank, address.version, nic, str(address)))
    return min(candidates)[-1] if candidates else None


def normalize_instance(raw, project, previous=None, elapsed=0, host_cpus=None):
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
        if old is not None and cpu_ns >= old and previous.get("location", "") == raw.get("location", ""):
            cpu = round((cpu_ns - old) / (elapsed * 1e9) * 100, 1)
    root = next((d for d in devices.values() if d.get("type") == "disk" and d.get("path") == "/"), {})
    disks = state.get("disk") or {}
    root_state = disks.get("root") or next(iter(disks.values()), {})
    guest_os = str(config.get("image.os") or config.get("os") or "").strip().lower()
    terminal_supported = raw.get("type", "container") == "container" or (
        raw.get("type") == "virtual-machine" and not any(os in guest_os for os in ("windows", "freebsd", "openbsd", "netbsd", "darwin", "macos"))
    )
    return {
        "guest_os": guest_os,
        "terminal_supported": terminal_supported,
        "name": raw["name"],
        "project": project,
        "type": raw.get("type", "container"),
        "location": raw.get("location", ""),
        "status": status,
        "status_code": raw.get("status_code", state.get("status_code")),
        "ips": sorted(set(ips)),
        "primary_ip": preferred_ip(state, devices),
        "macs": sorted(set(macs)),
        "dns": config.get("user.dns_name", ""),
        "cpu_ns": cpu_ns,
        "cpu_percent": cpu,
        "cpu_cores_used": round(cpu / 100, 3) if cpu is not None else None,
        "host_cpu_count": host_cpus,
        "cpu_host_percent": round(cpu / host_cpus, 1) if cpu is not None and host_cpus else None,
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
