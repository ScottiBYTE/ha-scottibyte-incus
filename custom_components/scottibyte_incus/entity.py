"""Shared server device metadata."""

from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN


def server_device(entry):
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)}, name=entry.title, manufacturer="Linux Containers", model="Incus server"
    )
