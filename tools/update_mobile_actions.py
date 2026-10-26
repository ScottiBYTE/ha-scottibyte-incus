"""Keep mobile instance actions readable in the fixed Actions column."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = '''
/* Mobile action controls, v0.1.9. */
@media(max-width:700px){
 th:nth-child(8),td:nth-child(8):not([colspan]){width:144px;min-width:144px;max-width:144px}
 .row-actions{gap:6px}
 .row-actions .snapshot-row{display:flex;flex-direction:column;gap:6px}
 .row-actions button,.row-actions .snapshot-row button{
   display:block;box-sizing:border-box;width:100%;min-width:0;min-height:36px;
   padding:7px 8px!important;font-size:12px!important;line-height:1.3;
   white-space:normal;overflow-wrap:normal;word-break:normal
 }
}
'''
manifest = ROOT / 'custom_components/scottibyte_incus/manifest.json'
data = json.loads(manifest.read_text())
if data['version'] not in ('0.1.8', '0.1.9'):
    raise SystemExit('Expected version 0.1.8 or 0.1.9; no files modified.')
panel = ROOT / 'custom_components/scottibyte_incus/frontend/panel.js'
source = panel.read_text()
if 'const MOBILE_ACTION_STYLE =' not in source:
    anchor = '${SNAPSHOT_SPACING_STYLE}'
    registration = "if(!customElements.get('scottibyte-incus-panel'))"
    if anchor not in source or registration not in source:
        raise SystemExit('Expected frontend anchors not found; no files modified.')
    source = source.replace(anchor, anchor + '${MOBILE_ACTION_STYLE}', 1)
    source = source.replace(registration, 'const MOBILE_ACTION_STYLE = ' + json.dumps(CSS) + ';\n' + registration, 1)
panel.write_text(source)
const = ROOT / 'custom_components/scottibyte_incus/const.py'
const.write_text(const.read_text().replace('"0.1.8"', '"0.1.9"'))
data['version'] = '0.1.9'
manifest.write_text(json.dumps(data, indent=2) + '\n')
(ROOT / 'RELEASE_NOTES_0.1.9.md').write_text('''# ScottiBYTE Incus v0.1.9 — readable mobile instance actions

- Stack Snapshot and Manage buttons vertically on narrow screens so their labels cannot collide.
- Give the fixed Actions column a defined mobile width and readable full-width controls.
- Preserve sticky Actions and table headers while the other columns scroll horizontally.

No snapshot or lifecycle behavior changes. Testing prerelease.
''')
publish = ROOT / 'tools/publish_prerelease.sh'
publish.write_text(publish.read_text().replace('v0.1.8', 'v0.1.9').replace('"0.1.8"', '"0.1.9"').replace('RELEASE_NOTES_0.1.8.md', 'RELEASE_NOTES_0.1.9.md').replace('offline server cards and addresses', 'readable mobile instance actions'))
print('Mobile Actions layout improved; version 0.1.9.')
