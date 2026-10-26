"""Remove the redundant API line and prepare release 1.1.2."""
import json
from pathlib import Path

root = Path.cwd()
panel = root / "custom_components/scottibyte_incus/frontend/panel.js"
manifest = root / "custom_components/scottibyte_incus/manifest.json"
if not manifest.exists():
    raise SystemExit("Run from your ha-scottibyte-incus checkout.")
data = json.loads(manifest.read_text())
if data["version"] not in ("1.1.1", "1.1.2"):
    raise SystemExit(f"Expected 1.1.1 or 1.1.2; found {data['version']}. No files modified.")
source = panel.read_text()
api_line = '${s.clustered&&s.active_endpoint?`<p class="server-address">API: ${escapeHTML(s.active_endpoint)}</p>`:\'\'}'
if api_line not in source and 'API: ${escapeHTML(s.active_endpoint)}' in source:
    raise SystemExit("Unexpected API markup; no files modified.")
updates = {panel: source.replace(api_line, "")}
data["version"] = "1.1.2"
updates[manifest] = json.dumps(data, indent=2) + "\n"
const = root / "custom_components/scottibyte_incus/const.py"
updates[const] = const.read_text().replace('VERSION = "1.1.1"', 'VERSION = "1.1.2"')
publisher = root / "tools/publish_release.sh"
updates[publisher] = publisher.read_text().replace("1.1.1", "1.1.2")
readme = root / "README.md"
updates[readme] = readme.read_text().replace("**Version 1.1.1 — Linux VM guest terminals.**", "**Version 1.1.2 — cleaner cluster cards.**").replace("numbered **v1.1.1**", "numbered **v1.1.2**").replace("Cluster cards show member name, cluster size and active API endpoint.", "Cluster cards show the server IP, member name and cluster size. The redundant API address line is omitted.")
checks = root / "tools/browser_smoke.py"
s = checks.read_text()
anchor = '                    assert "vmscloud-incus" in label.inner_text()\n'
if 'assert "API:" not in' not in s:
    s = s.replace(anchor, anchor + '                    assert "API:" not in page.locator(\'[data-server="storm"]\').inner_text()\n')
updates[checks] = s
updates[root / "RELEASE_NOTES_1.1.2.md"] = """# ScottiBYTE Incus v1.1.2

Remove the redundant API endpoint line from cluster server cards on desktop and mobile. Keep the configured server IP, member name, cluster size and status.

This is a presentation change. Cluster endpoint selection, certificate trust and Linux VM terminals retain their existing behavior.

Validation: browser regression checks include cluster cards at 360, 390, 480 and desktop widths, verifying that no API line is shown. Run Ruff, pytest, JavaScript syntax validation and GitHub tests/hassfest for the release commit before publishing.
"""
for path, text in updates.items():
    path.write_text(text)
print("Removed API lines from cluster cards; prepared version 1.1.2.")
