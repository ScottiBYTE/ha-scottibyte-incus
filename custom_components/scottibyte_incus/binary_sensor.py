"""Server connectivity entities."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .entity import server_device


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([IncusConnectivity(hass.data[DOMAIN]["coordinators"][entry.entry_id])])


class IncusConnectivity(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Connectivity"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_connectivity"
        self._attr_device_info = server_device(coordinator.entry)

    @property
    def is_on(self):
        return self.coordinator.snapshot["online"]

    @property
    def extra_state_attributes(self):
        return {"last_success": self.coordinator.snapshot["last_success"]}
