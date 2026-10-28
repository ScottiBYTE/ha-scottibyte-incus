"""Align server card sections and prepare v1.2.0-beta.2."""
import json
from pathlib import Path

root = Path.cwd()
version = '1.2.0-beta.2'
manifest = root / 'custom_components/scottibyte_incus/manifest.json'
data = json.loads(manifest.read_text())
if data['version'] not in ('1.2.0-beta.1', version):
    raise SystemExit(f"Expected 1.2.0-beta.1 or {version}; found {data['version']}. No files modified.")
panel = root / 'custom_components/scottibyte_incus/frontend/panel.js'
source = panel.read_text()
old = '''<h3>${escapeHTML(s.name)}</h3>${s.clustered?`<p class="cluster-member">Member: ${escapeHTML(s.cluster_member||s.server_name||s.name)} · ${s.cluster_members?.length||'?'} members</p>`:''}<p class="server-address">${escapeHTML(s.host||'Address unavailable')}</p><p>Incus ${escapeHTML(s.version||'—')}${s.clustered?' · Cluster member':''}</p>${hostMetrics(s.host_metrics)}'''
new = '''<div class="card-identity"><h3 title="${escapeHTML(s.name)}">${escapeHTML(s.name)}</h3><p class="server-address" title="${escapeHTML(s.host||'Address unavailable')}">${escapeHTML(s.host||'Address unavailable')}</p><p class="card-version">Incus ${escapeHTML(s.version||'—')}${s.clustered?' · Cluster member':''}</p><p class="cluster-member ${s.clustered?'':'membership-placeholder'}" ${s.clustered?'':'aria-hidden="true"'} title="${s.clustered?escapeHTML(s.cluster_member||s.server_name||s.name):''}">${s.clustered?`Member: ${escapeHTML(s.cluster_member||s.server_name||s.name)} · ${s.cluster_members?.length||'?'} members`:'&nbsp;'}</p></div>${hostMetrics(s.host_metrics)}'''
if new not in source:
    if source.count(old) != 1:
        raise SystemExit('Unexpected card identity markup; no files modified.')
    source = source.replace(old, new, 1)
style = '''
/* Consistent card sections, v1.2.0-beta.2. */
.server-wrap{display:flex;flex-direction:column;min-width:0}
.server-wrap>.server-card{display:flex;flex-direction:column;align-items:stretch;justify-content:flex-start;flex:1 1 auto;height:auto;min-width:0}
.server-card .card-top,.card-identity{flex:0 0 auto}
.card-identity h3{line-height:1.4;margin:14px 0 4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card-identity .server-address{margin:4px 0!important;line-height:1.5;height:1.5em;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.card-identity .card-version{margin:4px 0;line-height:1.5;height:1.5em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card-identity .cluster-member{margin:4px 0!important;line-height:1.5;height:1.5em;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.server-card .host-metrics{flex:1 0 auto;margin:12px 0 0}
.server-card .host-metrics>.host-metrics-hint{height:1.5em;line-height:1.5;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.server-card .host-metrics dl{grid-template-columns:minmax(0,1fr);gap:7px;margin:8px 0 12px}
.host-metrics dd,.host-disk strong,.card-counts strong{font-variant-numeric:tabular-nums}
.server-card .host-disks{height:132px;max-height:132px;overflow:auto;scrollbar-gutter:stable}
.server-card .host-disk{display:grid;grid-template-columns:minmax(0,1fr) max-content;align-items:baseline;gap:8px;margin:6px 0;line-height:1.5}
.server-card .host-disk>span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;overflow-wrap:normal}
.server-card .host-disk strong{text-align:right;white-space:nowrap}
.server-card .card-counts{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:auto;padding:18px 0;flex:0 0 auto}
.card-counts>span{display:flex;align-items:baseline;gap:5px;white-space:nowrap}
.card-counts strong{margin-right:0;min-width:3ch;text-align:right}
.server-card .card-bottom{margin-top:0;flex:0 0 auto}
.server-wrap>.drag-handle,.server-wrap>.move-controls{flex:0 0 auto}
@media(max-width:600px){
 .card-identity .server-address{height:auto;min-height:1.5em;display:block;white-space:normal;overflow-wrap:anywhere}
 .card-identity .membership-placeholder{display:none}
 .server-card .host-metrics>.host-metrics-hint{height:auto}.server-card .host-disks{height:auto;max-height:132px}
 .server-card .host-disk{grid-template-columns:minmax(0,1fr);gap:2px}
 .server-card .host-disk>span{white-space:normal;overflow-wrap:anywhere}
}
'''
if 'const CARD_ALIGNMENT_STYLE =' not in source:
    if source.count('${MOBILE_SERVER_NAME_STYLE}</style>') != 1 or source.count("if(!customElements.get('scottibyte-incus-panel'))") != 1:
        raise SystemExit('Unexpected style registration; no files modified.')
    source = source.replace('${MOBILE_SERVER_NAME_STYLE}</style>', '${MOBILE_SERVER_NAME_STYLE}${CARD_ALIGNMENT_STYLE}</style>', 1)
    source = source.replace("if(!customElements.get('scottibyte-incus-panel'))", 'const CARD_ALIGNMENT_STYLE = ' + json.dumps(style) + ';\n' + "if(!customElements.get('scottibyte-incus-panel'))", 1)
source = source.replace('title="${escapeHTML(d.filesystem)}"', 'title="${escapeHTML(d.mount)} · ${escapeHTML(d.filesystem)}"')
source = source.replace("' · unavailable / last known'", "' · last known'")
updates = {panel: source}
data['version'] = version
updates[manifest] = json.dumps(data, indent=2) + '\n'
const = root / 'custom_components/scottibyte_incus/const.py'
updates[const] = const.read_text().replace('VERSION = "1.2.0-beta.1"', f'VERSION = "{version}"')
publisher = root / 'tools/publish_host_metrics_prerelease.sh'
publisher_text = publisher.read_text()
if '--prerelease' not in publisher_text or not any(v in publisher_text for v in ('1.2.0-beta.1', version)):
    raise SystemExit('Unexpected beta publisher; no files modified.')
updates[publisher] = publisher_text.replace('1.2.0-beta.1', version)
readme = root / 'README.md'
updates[readme] = readme.read_text().replace('1.2.0-beta.1', version)
updates[root / f'RELEASE_NOTES_{version}.md'] = '''# ScottiBYTE Incus v1.2.0-beta.2

- Top-align server card contents instead of vertically centering them.
- Use consistent positions for server names, addresses, Incus versions and cluster membership.
- Stack CPU and memory into separate rows with right-aligned percentages.
- Reserve a consistent filesystem area on desktop, align used/total values and show full paths in hover titles.
- Align instance counts and footers; use compact, wrapping filesystem rows on mobile.

Existing host-metrics enrollment carries over. Measurement collection and polling behavior are unchanged. This remains a testing release.
'''
BROWSER_CHECKS = '                page.evaluate("""async()=>{\n                    const base=structuredClone(servers[0]);\n                    window.servers=Array.from({length:10},(_,i)=>({...structuredClone(base),\n                      id:\'align-\'+i,name:[\'VMSStorm\',\'VMSMist\',\'VMSRain\',\'Mondo-2\',\'VMSCloud-Incus\',\'VMSFog-Incus\',\'Incus-Member\',\'VMSDroplet\',\'Demo-1\',\'Mondo (Dell XPS 8930)\'][i],\n                      online:i!==1,clustered:i>=4&&i<=6,cluster_member:\'member-\'+i,\n                      host_metrics:{...structuredClone(base.host_metrics),online:i!==1,\n                        filesystems:Array.from({length:i%7+1},(_,n)=>({mount:n?\'/mnt/storage-with-a-long-name-\'+n:\'/\',filesystem:\'ext4\',used:123456789000,total:987654321000}))}}));\n                    await document.querySelector(\'scottibyte-incus-panel\').refresh();\n                }""")\n                page.set_viewport_size({"width":1680,"height":1100})\n                assert page.locator(".server-card").count() == 10\n                for selector in (".card-top", ".card-identity h3", ".server-address", ".card-version", ".host-metrics dl>div", ".host-disks", ".card-counts", ".card-bottom"):\n                    positions = page.locator(".server-card").evaluate_all("(cards,selector)=>cards.slice(0,6).map(c=>c.querySelector(selector).getBoundingClientRect().top)", selector)\n                    assert max(positions)-min(positions)<1, (selector,positions)\n                heights=page.locator(".server-card").evaluate_all("cards=>cards.map(c=>c.getBoundingClientRect().height)")\n                assert max(heights)-min(heights)<1, heights\n                page.screenshot(path=str(screenshots / "card-alignment-desktop.png"),full_page=True)\n                for width in (360,390,480):\n                    page.set_viewport_size({"width":width,"height":844})\n                    assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth")\n                    assert page.locator(".host-metrics").first.evaluate("el=>el.scrollWidth<=el.clientWidth")\n                    page.locator(".server-card").first.screenshot(path=str(screenshots / f"card-alignment-{width}.png"))\n'
checks = root / 'tools/browser_smoke.py'
check_source = checks.read_text()
if "id:'align-'+i" not in check_source:
    anchor = '                assert not errors, errors\n'
    if anchor not in check_source:
        raise SystemExit('Unexpected browser check structure; no files modified.')
    check_source = check_source.replace(anchor, BROWSER_CHECKS + anchor, 1)
check_source = check_source.replace('page.locator(".cluster-member")', 'page.locator(".cluster-member:not(.membership-placeholder)")')
updates[checks] = check_source
for path, text in updates.items():
    path.write_text(text)
print(f'Server card alignment applied; version {version}.')
