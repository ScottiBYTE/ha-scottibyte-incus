from custom_components.scottibyte_incus.models import counts, normalize_instance, size_bytes


def test_units_and_unknown_limits():
    assert size_bytes("2GiB") == 2 * 1024**3
    assert size_bytes("2GB") == 2_000_000_000
    assert size_bytes("1024") == 1024
    assert size_bytes("50%") is None
    assert size_bytes(None) is None


def test_recursion_inventory_cpu_and_addresses():
    raw = {
        "name": "Assist",
        "type": "container",
        "status": "Running",
        "expanded_config": {"limits.memory": "2GiB"},
        "expanded_devices": {"root": {"type": "disk", "path": "/", "size": "20GiB"}},
        "state": {
            "cpu": {"usage": 3_000_000_000},
            "memory": {"usage": 1024},
            "disk": {"root": {"usage": 2048}},
            "network": {
                "lo": {"type": "loopback", "addresses": [{"scope": "local", "address": "127.0.0.1"}]},
                "eth0": {
                    "hwaddr": "00:16:3e:01:02:03",
                    "addresses": [
                        {"scope": "global", "address": "172.16.1.243"},
                        {"scope": "link", "address": "fe80::1"},
                    ],
                },
            },
        },
    }
    item = normalize_instance(raw, "default", {"cpu_ns": 1_000_000_000}, 10)
    assert item["cpu_percent"] == 20
    assert item["ips"] == ["172.16.1.243"]
    assert item["memory_limit"] == 2 * 1024**3
    assert item["disk_limit"] == 20 * 1024**3
    assert item["dns"] == ""  # Do not invent DNS records from instance names.
    assert normalize_instance(raw, "default", {"cpu_ns": 4_000_000_000}, 10)["cpu_percent"] is None
    stopped = normalize_instance({"name": "offline", "status": "Stopped"}, "other")
    assert stopped["memory_bytes"] is None
    assert counts([item, stopped]) == {"total": 2, "running": 1, "stopped": 1, "containers": 2, "vms": 0}
