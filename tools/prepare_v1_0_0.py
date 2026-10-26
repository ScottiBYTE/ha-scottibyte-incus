import json
import re
from pathlib import Path

root = Path.cwd()
manifest = root / "custom_components/scottibyte_incus/manifest.json"
data = json.loads(manifest.read_text())
old_version = data["version"]
if old_version not in ("0.1.10", "1.0.0"):
    raise SystemExit(f"Expected 0.1.10; found {old_version}. No files modified.")
const = root / "custom_components/scottibyte_incus/const.py"
constant, count = re.subn(r'^VERSION = "[^"]+"$', 'VERSION = "1.0.0"', const.read_text(), flags=re.MULTILINE)
if count != 1:
    raise SystemExit("Expected one VERSION constant; no files modified.")
publisher = (root / "tools/publish_prerelease.sh").read_text()
if "gh release create" not in publisher:
    raise SystemExit("Expected release helper not found; no files modified.")
publisher = re.sub(r"0\.1\.\d+", "1.0.0", publisher.split("gh release create", 1)[0])
publisher += 'gh release create v1.0.0 --target "$release_commit" --latest --title "ScottiBYTE Incus v1.0.0" --notes-file RELEASE_NOTES_1.0.0.md\n'
data["version"] = "1.0.0"
manifest.write_text(json.dumps(data, indent=2) + "\n")
const.write_text(constant)
(root / "tools/publish_release.sh").write_text(publisher)
readme = root / "README.md"
text = readme.read_text()
start = text.index("**Version ")
end = text.index("\n\n## Features", start)
text = text[:start] + "**Version 1.0.0 — first stable release.** Current features have been tested by Scott in his live Home Assistant/Incus environment, including the Pixel 7 Companion app. Install the numbered release through HACS as a custom repository. Default HACS catalog listing is a separate submission." + text[end:]
text = text.replace("The first tagged prerelease is **v0.1.5**. In HACS, enable **Show beta versions** when necessary to select a prerelease. Confirm the downloaded version after installation. Tracking `main` remains a testing workflow.", "Select the numbered **v1.0.0** release in HACS. A hexadecimal commit identifier means the development branch is selected. Restart HA after installation; refresh the browser or reset the Companion frontend cache if an older interface remains visible. Tracking `main` is reserved for development testing.")
text = text.replace("Version 7.5.1 is the initial live-test target; protocol compatibility with other versions is not yet certified.", "Live testing used Incus 7.5.1; compatibility with other Incus versions has not been separately certified.")
readme.write_text(text)
(root / "RELEASE_NOTES_1.0.0.md").write_text("""# ScottiBYTE Incus v1.0.0

First stable release of the HACS-installable Incus integration for Home Assistant.

## Features

- Add independent servers through Devices & services, with automatic SSH-based certificate enrollment and a token enrollment alternative.
- Combined summary, server addresses/status, persistent drag-and-drop card ordering, and global instance search.
- Per-server sortable instance tables, sticky headers/actions, expandable network details, and a mobile layout tested in the Pixel 7 Companion app.
- CPU usage normalized to host logical CPU capacity, memory/disk metrics, preferred guest IP selection, and cached local reverse DNS.
- Start and gracefully stop containers/VMs; embedded root terminals for running Linux system containers.
- Create, list, rename, delete, and restore instance snapshots. Incus restarts an instance that was running before restore.
- Offline server cards cannot open cached instance lists; their instances are excluded from search.
- Server connection reconfiguration and trust renewal preserve HA entry/entity identities and saved card order.
- Server removal attempts to revoke its own certificate; failed cleanup generates a notification with manual instructions.
- Administrator-only management endpoints and native HA devices/entities.

## Validation and installation

Scott reports all current features tested in the live deployment. Automated Python tests, lint, JavaScript syntax, and hassfest must pass on this exact release commit before publication.

In HACS, add https://github.com/ScottiBYTE/ha-scottibyte-incus as a custom repository of type Integration and select v1.0.0. Restart HA and refresh the frontend after updating. This is a regular release, not a prerelease.

## Documented limitations

- Removed-instance HA registry entries are retained and may require manual cleanup.
- No VM console, forced-stop action, stateful-memory snapshot management, snapshot export/scheduling/expiry editing, or lifecycle services for automations.
- Snapshots do not include attached custom storage volumes and are not external backups.
- A VM needs a functioning Incus agent for guest IPs and metrics. Missing metrics remain unknown.
- Default HACS catalog inclusion is a separate submission.
""")
(root / "VALIDATION.md").write_text("""# v1.0.0 validation

## Live acceptance

Scott confirmed that all current features have been tested in his live deployment. The latest mobile layout was visually confirmed in the Pixel 7 Home Assistant Companion app. Release selection was verified using numbered HACS releases rather than development commit hashes.

The observed environment uses Home Assistant Core 2026.10.4 and Incus 7.5.1, with multiple independent servers. This record does not claim separate live certification of every cluster topology, hardware architecture, or Incus version.

## Automated coverage

The regression suite covers integration setup/unload, certificate enrollment and pinning, secret handling, administrator enforcement, instance lifecycle and terminal requests, snapshot operations, CPU calculations and member targeting, DNS caching, offline data suppression/recovery, server reconfiguration, and trust cleanup. Browser checks cover summary/search, drill-down, management dialogs, terminal interaction, server reordering, and narrow layouts.

Before publication, run pytest, Ruff, JavaScript syntax validation, and the GitHub Checks workflow (tests and hassfest) for the exact release commit. The stable publishing helper stops if that workflow fails.

## Remaining limitations and follow-up

Removed-instance registry cleanup remains manual. Default HACS catalog acceptance is separate from this stable release. See README.md and RELEASE_NOTES_1.0.0.md for the supported feature scope and limitations.
""")
(root / "RELEASE_CHECKLIST.md").write_text("""# v1.0.0 release record

- Current feature acceptance: Scott reports all current features tested.
- Mobile display: confirmed in the Pixel 7 Companion app.
- Version metadata and release documentation: prepared for 1.0.0.
- Publication gate: local checks and GitHub tests/hassfest must pass for the exact tagged commit.
- Publish as a regular release marked Latest; use numbered releases in HACS.

## Follow-up work

- Automatic cleanup of removed-instance registry entries (currently manual).
- Default HACS catalog submission.
- Broader platform and version certification beyond the observed test environment.
""")
print("Prepared v1.0.0 metadata, documentation, and stable publishing helper.")

# Display the version of the frontend actually loaded, including on phones.
panel = root / "custom_components/scottibyte_incus/frontend/panel.js"
source = panel.read_text()
if "const FRONTEND_VERSION =" in source:
    source = re.sub(r"const FRONTEND_VERSION = '[^']*';", "const FRONTEND_VERSION = new URL(import.meta.url).searchParams.get('v');", source, count=1)
else:
    source = source.replace("const BASE =", "const FRONTEND_VERSION = new URL(import.meta.url).searchParams.get('v');\nconst BASE =", 1)
old_brand = '<h1>ScottiBYTE <span>Incus</span></h1><p>Your servers. One view.</p>'
new_brand = '<h1>ScottiBYTE <span>Incus</span></h1><div class="brand-meta"><span class="app-version" aria-label="Dashboard version">v${FRONTEND_VERSION}</span><a class="donate-link" href="https://www.paypal.com/paypalme/ScottiBYTE" target="_blank" rel="noopener noreferrer" aria-label="Donate to ScottiBYTE through PayPal">Donate ↗</a></div><p>Your servers. One view.</p>'
if 'class="brand-meta"' not in source:
    if old_brand not in source:
        raise SystemExit("Expected app title markup not found; frontend not modified.")
    source = source.replace(old_brand, new_brand, 1)
if '/* Release branding */' not in source:
    source = source.replace("const SERVER_STYLE = '", "const SERVER_STYLE = '/* Release branding */ .brand-meta{display:flex;align-items:center;gap:12px;margin-top:7px;flex-wrap:wrap}.app-version{font-size:12px;color:var(--muted);white-space:nowrap}.donate-link{display:inline-flex;align-items:center;padding:3px 9px;font-size:12px;line-height:1.5;border-color:var(--blue);color:var(--blue);white-space:nowrap} ", 1)
panel.write_text(source)
notes = root / "RELEASE_NOTES_1.0.0.md"
notes.write_text(notes.read_text().replace("## Features\n", "## Features\n\n- Visible dashboard version and a Donate button linking to ScottiBYTE's PayPal page.\n", 1))
if "## Support ScottiBYTE" not in readme.read_text():
    readme.write_text(readme.read_text() + "\n## Support ScottiBYTE\n\nIf you find this integration useful, you can [donate through PayPal](https://www.paypal.com/paypalme/ScottiBYTE). The dashboard header also includes a Donate button. Its visible version identifies the frontend currently loaded in your browser or Companion app.\n")
print("Added dashboard version display and PayPal Donate button.")

browser_checks = root / "tools/browser_smoke.py"
checks = browser_checks.read_text()
if 'page.locator(".app-version")' not in checks:
    checks = checks.replace('                assert page.locator(".stat").count() == 6\n', '''                assert page.locator(".stat").count() == 6
                assert page.locator(".app-version").inner_text() == "v1.0.0"
                assert page.locator(".donate-link").get_attribute("href") == "https://www.paypal.com/paypalme/ScottiBYTE"
                assert page.locator(".donate-link").get_attribute("target") == "_blank"
''', 1)
    checks = checks.replace('                assert page.locator("a.add-server").is_visible()\n', '''                assert page.locator("a.add-server").is_visible()
                assert page.locator(".app-version").is_visible()
                assert page.locator(".donate-link").is_visible()
''', 1)
browser_checks.write_text(checks)

# The installed manifest is the only source of the displayed release version.
setup_path = root / "custom_components/scottibyte_incus/__init__.py"
setup = setup_path.read_text()
if "from homeassistant.loader import async_get_integration" not in setup:
    setup = setup.replace("from homeassistant.helpers.storage import Store", "from homeassistant.helpers.storage import Store\nfrom homeassistant.loader import async_get_integration")
setup = setup.replace("STATIC_URL, VERSION", "STATIC_URL")
if 'integration = await async_get_integration(hass, DOMAIN)' not in setup:
    setup = setup.replace("    await panel_custom.async_register_panel(", "    integration = await async_get_integration(hass, DOMAIN)\n    await panel_custom.async_register_panel(", 1)
setup = setup.replace('panel.js?v={VERSION}', 'panel.js?v={integration.version}')
setup_path.write_text(setup)
source = panel.read_text()
source = re.sub(r"const FRONTEND_VERSION = .*?;", "const FRONTEND_VERSION = new URL(import.meta.url).searchParams.get('v');", source, count=1)
source = source.replace('v${FRONTEND_VERSION}</span>', "${FRONTEND_VERSION ? `v${escapeHTML(FRONTEND_VERSION)}` : 'Version unavailable'}</span>")
panel.write_text(source)
checks = browser_checks.read_text().replace("import '/scottibyte_incus_static/panel.js';", "import '/scottibyte_incus_static/panel.js?v=9.8.7';")
checks = checks.replace('inner_text() == "v1.0.0"', 'inner_text() == "v9.8.7"')
browser_checks.write_text(checks)
text = readme.read_text().replace("Its visible version identifies the frontend currently loaded in your browser or Companion app.", "Its visible version comes from the installed integration manifest and identifies the frontend loaded in your browser or Companion app.")
readme.write_text(text)
print("Dashboard version is read dynamically from the installed manifest via the module URL.")
