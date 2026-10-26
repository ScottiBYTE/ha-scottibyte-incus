"""Keep server names readable in narrow instance tables."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = '''
/* Mobile server names, v0.1.10. */
@media(max-width:700px){
 th:nth-child(1),td:nth-child(1):not([colspan]){width:128px;min-width:128px;max-width:128px}
 td:nth-child(1) .host-link{
   display:block;max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
   overflow-wrap:normal;word-break:normal
 }
}
'''
manifest = ROOT / 'custom_components/scottibyte_incus/manifest.json'
data = json.loads(manifest.read_text())
if data['version'] not in ('0.1.9', '0.1.10'):
    raise SystemExit('Expected version 0.1.9 or 0.1.10; no files modified.')
panel = ROOT / 'custom_components/scottibyte_incus/frontend/panel.js'
source = panel.read_text()
if 'const MOBILE_SERVER_NAME_STYLE =' not in source:
    anchor = '${MOBILE_ACTION_STYLE}'
    registration = "if(!customElements.get('scottibyte-incus-panel'))"
    if anchor not in source or registration not in source:
        raise SystemExit('Expected frontend anchors not found; no files modified.')
    source = source.replace(anchor, anchor + '${MOBILE_SERVER_NAME_STYLE}', 1)
    source = source.replace(registration, 'const MOBILE_SERVER_NAME_STYLE = ' + json.dumps(CSS) + ';\n' + registration, 1)
    source = source.replace('<button class="host-link" data-drill=', '<button class="host-link" title="${escapeHTML(i.server)}" data-drill=', 1)
panel.write_text(source)
const = ROOT / 'custom_components/scottibyte_incus/const.py'
const.write_text(const.read_text().replace('"0.1.9"', '"0.1.10"'))
data['version'] = '0.1.10'
manifest.write_text(json.dumps(data, indent=2) + '\n')
(ROOT / 'RELEASE_NOTES_0.1.10.md').write_text('''# ScottiBYTE Incus v0.1.10 — mobile server names

- Widen the Server column on narrow screens so short names such as VMSMist fit on one line.
- Truncate longer server labels with an ellipsis instead of wrapping into adjacent content.
- Preserve the full name in the link title and in the server view opened by tapping it.
- Keep Actions fixed and the other columns horizontally scrollable. Desktop column sizing is unchanged.

Testing prerelease; no lifecycle or snapshot behavior changes.
''')
publish = ROOT / 'tools/publish_prerelease.sh'
publish.write_text(publish.read_text().replace('v0.1.9', 'v0.1.10').replace('"0.1.9"', '"0.1.10"').replace('RELEASE_NOTES_0.1.9.md', 'RELEASE_NOTES_0.1.10.md').replace('readable mobile instance actions', 'mobile server names'))
print('Mobile server name layout improved; version 0.1.10.')
