"""Exercise installation and setup using actual Home Assistant runtime fixtures."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.scottibyte_incus.bootstrap import generate_certificate, write_credentials
from custom_components.scottibyte_incus.const import DOMAIN

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


@pytest.fixture(autouse=True)
def isolated_config(hass, tmp_path):
    hass.config.config_dir = str(tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize("entry_title", ["vmsstorm", "Incus"])
async def test_setup_entities_panel_and_unload(hass, entry_title):
    directory = Path(hass.config.path(".storage", DOMAIN, "test"))
    directory.mkdir(parents=True)
    cert, key = generate_certificate()
    write_credentials(directory / "client.crt", directory / "client.key", cert, key)
    (directory / "server.crt").write_text(cert)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=entry_title,
        unique_id="test",
        data={
            "credential_id": "test",
            "host": "172.16.0.10",
            "api_port": 8443,
            "projects": ["*"],
            "server_name": "vmsstorm",
        },
    )
    entry.add_to_hass(hass)
    inventory = (
        {"auth": "trusted", "environment": {"server_version": "7.5.1", "server_name": "vmsstorm"}},
        [("default", {"name": "Assist", "type": "container", "status": "Running", "state": {}})],
    )
    with patch("custom_components.scottibyte_incus.api.IncusClient.inventory", new=AsyncMock(return_value=inventory)):
        assert await async_setup_component(hass, DOMAIN, {})
        await hass.async_block_till_done()
        assert entry.title == "vmsstorm"
        assert entry.state.value == "loaded"
        assert hass.states.get("sensor.vmsstorm_running").state == "1"
        assert hass.states.get("binary_sensor.vmsstorm_connectivity").state == "on"
        assert "scottibyte-incus" in hass.data["frontend_panels"]
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_config_flow_menu_and_host_confirmation(hass):
    assert await async_setup_component(hass, DOMAIN, {})
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert flow["type"] == "menu"
    flow = await hass.config_entries.flow.async_configure(flow["flow_id"], {"next_step_id": "ssh"})
    assert flow["step_id"] == "ssh"
    host_key = type("Key", (), {"get_fingerprint": lambda self: "SHA256:test"})()
    with patch("custom_components.scottibyte_incus.config_flow.discover_server", new=AsyncMock(return_value=host_key)):
        flow = await hass.config_entries.flow.async_configure(
            flow["flow_id"],
            {
                "name": "vmsstorm",
                "host": "172.16.0.10",
                "ssh_port": 22,
                "api_port": 8443,
                "username": "scott",
                "password": "temporary-secret",
                "projects": "*",
                "enable_https": True,
            },
        )
    assert flow["step_id"] == "confirm_host"
    assert flow["description_placeholders"]["fingerprint"] == "SHA256:test"
    hass.config_entries.flow.async_abort(flow["flow_id"])


@pytest.mark.asyncio
@pytest.mark.parametrize(("requested_name", "expected_title"), [(None, "demo-1"), ("", "demo-1"), ("Incus", "demo-1"), (" Office lab ", "Office lab")])
async def test_finished_setup_does_not_persist_ssh_credentials(hass, requested_name, expected_title):
    assert await async_setup_component(hass, DOMAIN, {})
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    flow = await hass.config_entries.flow.async_configure(flow["flow_id"], {"next_step_id": "ssh"})
    host_key = type("Key", (), {"get_fingerprint": lambda self: "SHA256:test"})()
    with patch("custom_components.scottibyte_incus.config_flow.discover_server", new=AsyncMock(return_value=host_key)):
        flow = await hass.config_entries.flow.async_configure(
            flow["flow_id"],
            {
                **({"name": requested_name} if requested_name is not None else {}),
                "host": "172.16.0.10",
                "ssh_port": 22,
                "api_port": 8443,
                "username": "novice",
                "password": "do-not-save",
                "sudo_password": "also-private",
                "projects": "*",
                "enable_https": True,
            },
        )
    server_cert, _ = generate_certificate()
    info = {"auth": "trusted", "environment": {"server_name": "demo-1"}}
    with (
        patch(
            "custom_components.scottibyte_incus.config_flow.enroll_ssh", new=AsyncMock(return_value=(server_cert, info))
        ),
        patch("custom_components.scottibyte_incus.api.IncusClient.inventory", new=AsyncMock(return_value=(info, []))),
    ):
        flow = await hass.config_entries.flow.async_configure(flow["flow_id"], {})
        await hass.async_block_till_done()
    assert flow["type"] == "create_entry"
    assert flow["result"].title == expected_title
    assert "do-not-save" not in str(flow["data"]) and "also-private" not in str(flow["data"])
    assert not {"password", "sudo_password", "ssh_key", "username", "token"} & flow["data"].keys()
    directory = Path(hass.config.path(".storage", DOMAIN, flow["data"]["credential_id"]))
    assert (directory / "client.key").stat().st_mode & 0o777 == 0o600
    await hass.config_entries.async_unload(flow["result"].entry_id)
