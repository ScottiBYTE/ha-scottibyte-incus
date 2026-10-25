"""Add a server setup shortcut and detect default server display names."""

import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
component = root / "custom_components/scottibyte_incus"
flow = component / "config_flow.py"
source = flow.read_text()
source = source.replace('vol.Required("name", default="Incus"): str,', 'vol.Optional("name", default=""): str,')
source = source.replace(
    '        projects = parse_projects(settings["projects"])\n',
    '        projects = parse_projects(settings["projects"])\n'
    '        detected_name = str(info.get("environment", {}).get("server_name") or "").strip()\n'
    '        requested_name = str(settings.get("name") or "").strip()\n'
    '        display_name = requested_name if requested_name and requested_name.casefold() != "incus" else detected_name or settings["host"]\n',
    1,
)
source = source.replace('title=settings["name"],', "title=display_name,")
source = source.replace(
    'info.get("environment", {}).get("server_name", settings["name"])', 'detected_name or settings["host"]'
)
flow.write_text(source)

setup = component / "__init__.py"
source = setup.read_text()
anchor = "        await coordinator.async_config_entry_first_refresh()\n"
replacement = (
    anchor
    + """        # Upgrade only the old generic label; preserve deliberately chosen names.
        if entry.title.strip().casefold() == "incus":
            detected_name = str(coordinator.snapshot.get("server_name") or entry.data.get("server_name") or "").strip()
            if detected_name and detected_name.casefold() != "incus":
                hass.config_entries.async_update_entry(entry, title=detected_name)
"""
)
if "# Upgrade only the old generic label" not in source:
    assert anchor in source
    source = source.replace(anchor, replacement, 1)
setup.write_text(source)

panel = component / "frontend/panel.js"
source = panel.read_text()
anchor = '<a href="/config/integrations/integration/scottibyte_incus">Manage servers ↗</a>'
if ">Add server</a>" not in source:
    assert anchor in source
    source = source.replace(
        anchor,
        '<a class="add-server" href="/config/integrations/dashboard/add?domain=scottibyte_incus">Add server</a>'
        + anchor,
        1,
    )
# Keep Add server visible on phones, even when the secondary management link is hidden.
anchor = "// xterm's CSS must live"
if ".header-actions a.add-server" not in source:
    source = source.replace(
        anchor,
        "const SERVER_STYLE = '.header-actions a.add-server{display:inline-block;background:#0284c7;color:white;border-color:#0284c7}';\n"
        + anchor,
        1,
    )
    source = source.replace("${STYLE}${TABLE_STYLE}</style>", "${STYLE}${TABLE_STYLE}${SERVER_STYLE}</style>", 1)
panel.write_text(source)

for path in [component / "strings.json", component / "translations/en.json"]:
    data = json.loads(path.read_text())
    for step in ["ssh", "token"]:
        form = data["config"]["step"][step]
        form["data"]["name"] = "Display name (optional; detected from server)"
        description = "Leave the display name blank to use the server hostname automatically. "
        if not form["description"].startswith(description):
            form["description"] = description + form["description"]
    path.write_text(json.dumps(data, indent=2) + "\n")

manifest = component / "manifest.json"
data = json.loads(manifest.read_text())
data["version"] = "0.1.2"
manifest.write_text(json.dumps(data, indent=2) + "\n")
constants = component / "const.py"
constants.write_text(constants.read_text().replace('VERSION = "0.1.1"', 'VERSION = "0.1.2"'))
print("Server setup improvements applied; version 0.1.2.")

# Extend the setup and browser regression checks.
path = root / "tests/test_homeassistant.py"
source = path.read_text()
source = source.replace(
    "@pytest.mark.asyncio\nasync def test_setup_entities_panel_and_unload(hass):",
    '@pytest.mark.asyncio\n@pytest.mark.parametrize("entry_title", ["vmsstorm", "Incus"])\nasync def test_setup_entities_panel_and_unload(hass, entry_title):',
    1,
)
source = source.replace('        title="vmsstorm",', "        title=entry_title,", 1)
source = source.replace(
    '        assert entry.state.value == "loaded"',
    '        assert entry.title == "vmsstorm"\n        assert entry.state.value == "loaded"',
    1,
)
source = source.replace(
    "@pytest.mark.asyncio\nasync def test_finished_setup_does_not_persist_ssh_credentials(hass):",
    '@pytest.mark.asyncio\n@pytest.mark.parametrize(("requested_name", "expected_title"), [(None, "demo-1"), ("", "demo-1"), ("Incus", "demo-1"), (" Office lab ", "Office lab")])\nasync def test_finished_setup_does_not_persist_ssh_credentials(hass, requested_name, expected_title):',
    1,
)
source = source.replace(
    '                "name": "demo-1",',
    '                **({"name": requested_name} if requested_name is not None else {}),',
    1,
)
source = source.replace(
    '    assert flow["type"] == "create_entry"',
    '    assert flow["type"] == "create_entry"\n    assert flow["result"].title == expected_title',
    1,
)
path.write_text(source)
path = root / "tools/browser_smoke.py"
source = path.read_text()
anchor = '                assert page.locator(".stat").count() == 6\n'
source = source.replace(
    anchor,
    anchor
    + '                assert page.locator("a.add-server").get_attribute("href") == "/config/integrations/dashboard/add?domain=scottibyte_incus"\n',
    1,
)
anchor = '                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")\n'
source = source.replace(anchor, anchor + '                assert page.locator("a.add-server").is_visible()\n', 1)
path.write_text(source)
