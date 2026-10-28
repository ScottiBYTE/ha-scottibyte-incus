"""Promote the tested beta.3 code to stable v1.2.0 without functional changes."""
import json
import re
from pathlib import Path

root = Path.cwd()
manifest = root / 'custom_components/scottibyte_incus/manifest.json'
data = json.loads(manifest.read_text())
if data['version'] not in ('1.2.0-beta.3', '1.2.0'):
    raise SystemExit('Expected 1.2.0-beta.3 or 1.2.0; no files modified.')
const = root / 'custom_components/scottibyte_incus/const.py'
const_text = const.read_text()
if not any(f'VERSION = "{v}"' in const_text for v in ('1.2.0-beta.3', '1.2.0')):
    raise SystemExit('Unexpected version constant; no files modified.')
publisher = (root / 'tools/publish_host_metrics_prerelease.sh').read_text()
if '--prerelease' not in publisher or '1.2.0-beta.3' not in publisher:
    raise SystemExit('Unexpected beta publisher; no files modified.')
publisher = publisher.replace('1.2.0-beta.3', '1.2.0').replace('--prerelease', '--latest')
readme = root / 'README.md'
text = readme.read_text()
text = re.sub(r'\*\*Version [^\n]+', '**Version 1.2.0 — whole-server monitoring.** Stable release with host CPU, memory and filesystem usage, a saved refresh interval, and compact desktop and mobile server cards.', text, count=1)
text = re.sub(r'For testing, enable beta releases and select \*\*v1\.2\.0-beta\.[123]\*\* in HACS; \*\*v1\.1\.3\*\* remains stable\.', 'Select the numbered **v1.2.0** stable release in HACS.', text)
text = text.replace('## Whole-server monitoring and refresh (v1.2 testing)', '## Whole-server monitoring and refresh')
notes = '''# ScottiBYTE Incus v1.2.0

Stable release of whole-server monitoring and dashboard improvements.

- Measure Linux host CPU and memory utilization across all applications, independently of instance metrics.
- Display local filesystem used/total capacity on each server card.
- Enable host monitoring during new-server setup or through reconfiguration of an existing server.
- Use a dedicated restricted SSH key for host monitoring; supplied setup credentials are discarded.
- Configure a persistent global refresh interval of 10 seconds, 30 seconds, 1 minute or 5 minutes.
- Keep server cards aligned, with compact tinted resource panels and readable mobile filesystem lists.
- Retain last-known indicators when host measurements are unavailable.

Existing server registrations and beta host-monitoring enrollment carry over. Existing stable installations can enable host monitoring through server reconfiguration. Host monitoring requires Linux, Python 3 and ongoing SSH connectivity.

This release promotes the tested v1.2.0-beta.3 functionality without behavioral changes. Live testing confirmed enrollment for both existing and newly added servers. HACS catalog inclusion is separate from this release.
'''
data['version'] = '1.2.0'
updates = {
    manifest: json.dumps(data, indent=2) + '\n',
    const: const_text.replace('VERSION = "1.2.0-beta.3"', 'VERSION = "1.2.0"'),
    root / 'tools/publish_release.sh': publisher,
    readme: text,
    root / 'RELEASE_NOTES_1.2.0.md': notes,
}
for path, content in updates.items():
    path.write_text(content)
print('Stable v1.2.0 prepared. Run checks, commit and push, then tools/publish_release.sh.')
