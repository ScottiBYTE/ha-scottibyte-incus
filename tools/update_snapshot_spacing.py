"""Improve snapshot dialog spacing without changing snapshot behavior."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = '''
/* Snapshot dialog spacing, v0.1.7. */
#snapshots-dialog{padding:28px;line-height:1.5}
#snapshots-dialog .terminal-heading{align-items:flex-start;margin-bottom:18px;gap:24px}
#snapshots-title{min-width:0;overflow-wrap:anywhere;line-height:1.35}
#snapshots-close{flex-shrink:0}
#snapshots-dialog>.terminal-heading+p{margin:0 0 24px}
.snapshot-create{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:end;gap:12px}
.snapshot-create label{display:flex;flex-direction:column;gap:8px;min-width:0}
.snapshot-create input{margin:0;padding:10px 12px;min-height:44px}
.snapshot-create>button{min-height:44px;white-space:nowrap}
#snapshots-status{margin:22px 0 8px;line-height:1.5;min-height:21px}
.snapshot-item{padding:20px 0}
.snapshot-item strong{display:block;overflow-wrap:anywhere}
.snapshot-item small{margin:8px 0 14px;line-height:1.6;overflow-wrap:anywhere}
.snapshot-item>div{display:flex;flex-wrap:wrap;gap:8px}
.snapshot-item button{margin:0;min-height:40px}
#snapshot-confirm{width:560px;padding:28px;line-height:1.6}
#snapshot-confirm h2{line-height:1.35}
#snapshot-confirm p{margin:18px 0}
#snapshot-rename-label{display:block;margin-top:18px}
#snapshot-rename{display:block;margin-top:8px;padding:10px 12px}
#snapshot-confirm .dialog-actions{margin-top:26px;gap:12px}
@media(max-width:600px){
 #snapshots-dialog,#snapshot-confirm{padding:20px;width:calc(100vw - 24px);max-width:calc(100vw - 24px)}
 #snapshots-dialog .terminal-heading{gap:12px}
 #snapshots-title{font-size:17px}
 .snapshot-create{grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px}
 .snapshot-create label{grid-column:1/-1}
 .snapshot-create>button{white-space:normal;padding:9px}
}
'''
manifest = ROOT / 'custom_components/scottibyte_incus/manifest.json'
data = json.loads(manifest.read_text())
if data['version'] not in ('0.1.6', '0.1.7'):
    raise SystemExit('Expected version 0.1.6 or 0.1.7; no files modified.')
panel = ROOT / 'custom_components/scottibyte_incus/frontend/panel.js'
source = panel.read_text()
if 'const SNAPSHOT_SPACING_STYLE =' not in source:
    anchor = '${STYLE}${TABLE_STYLE}${SERVER_STYLE}'
    if anchor not in source:
        raise SystemExit('Expected dashboard styles not found; no files modified.')
    source = source.replace(anchor, anchor + '${SNAPSHOT_SPACING_STYLE}', 1)
    registration = "if(!customElements.get('scottibyte-incus-panel'))"
    if registration not in source:
        raise SystemExit('Expected component registration not found; no files modified.')
    source = source.replace(registration, 'const SNAPSHOT_SPACING_STYLE = ' + json.dumps(CSS) + ';\n' + registration, 1)
const = ROOT / 'custom_components/scottibyte_incus/const.py'
constant = const.read_text().replace('"0.1.6"', '"0.1.7"')
panel.write_text(source)
const.write_text(constant)
data['version'] = '0.1.7'
manifest.write_text(json.dumps(data, indent=2) + '\n')
notes = ROOT / 'RELEASE_NOTES_0.1.7.md'
notes.write_text('''# ScottiBYTE Incus v0.1.7 — snapshot dialog spacing

- Add clear spacing between the introduction, name label/input, create controls, status, and snapshot list.
- Space snapshot metadata and action buttons consistently.
- Improve long-title wrapping and the layout on narrow screens.
- Improve restore/delete/rename confirmation spacing.

Snapshot behavior is unchanged. This remains a testing prerelease.
''')
publish = ROOT / 'tools/publish_prerelease.sh'
publish.write_text(publish.read_text().replace('v0.1.6', 'v0.1.7').replace('"0.1.6"', '"0.1.7"').replace('RELEASE_NOTES_0.1.6.md', 'RELEASE_NOTES_0.1.7.md').replace('snapshot restore correction', 'snapshot dialog spacing'))
print('Snapshot dialog spacing improved; version 0.1.7.')
