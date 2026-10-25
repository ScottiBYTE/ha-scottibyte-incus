"""Per-server totals and dynamic per-instance state/metric entities."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .entity import server_device

METRICS = {
    "status": ("Status", None, None),
    "cpu_percent": ("CPU per core", "%", None),
    "cpu_host_percent": ("CPU host share", "%", None),
    "memory_bytes": ("Memory used", "B", SensorDeviceClass.DATA_SIZE),
    "disk_bytes": ("Disk used", "B", SensorDeviceClass.DATA_SIZE),
}


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN]["coordinators"][entry.entry_id]
    async_add_entities([IncusCount(coordinator, key) for key in ("total", "running", "stopped", "containers", "vms")])
    known = set()

    @callback
    def discover():
        entities = []
        for item in coordinator.snapshot["instances"]:
            identity = (item["project"], item["name"])
            if identity not in known:
                known.add(identity)
                entities.extend(IncusInstance(coordinator, *identity, metric) for metric in METRICS)
        if entities:
            async_add_entities(entities)

    entry.async_on_unload(coordinator.async_add_listener(discover))
    discover()


class IncusCount(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:server"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, key):
        super().__init__(coordinator)
        self.key = key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_name = {
            "total": "Total instances",
            "running": "Running",
            "stopped": "Stopped",
            "containers": "Containers",
            "vms": "Virtual machines",
        }[key]
        self._attr_device_info = server_device(coordinator.entry)

    @property
    def available(self):
        return self.coordinator.snapshot["online"]

    @property
    def native_value(self):
        return self.coordinator.snapshot["counts"][self.key]


class IncusInstance(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, project, name, metric):
        super().__init__(coordinator)
        self.project, self.instance_name, self.metric = project, name, metric
        identity = f"{coordinator.entry.entry_id}:{project}:{name}"
        self._attr_unique_id = f"{identity}:{metric}"
        label, unit, device_class = METRICS[metric]
        self._attr_name = label
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        self._attr_entity_registry_enabled_default = metric == "status"
        if metric != "status":
            self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identity)},
            name=f"{name} ({coordinator.entry.title}/{project})",
            manufacturer="Linux Containers",
            model="Incus instance",
            via_device=(DOMAIN, coordinator.entry.entry_id),
        )

    @property
    def item(self):
        return next(
            (
                i
                for i in self.coordinator.snapshot["instances"]
                if i["name"] == self.instance_name and i["project"] == self.project
            ),
            None,
        )

    @property
    def available(self):
        return self.coordinator.snapshot["online"] and self.item is not None

    @property
    def native_value(self):
        return self.item.get(self.metric) if self.item else None

    @property
    def extra_state_attributes(self):
        if self.metric != "status" or not self.item:
            return None
        return {k: self.item[k] for k in ("project", "type", "location", "ips", "macs")}
