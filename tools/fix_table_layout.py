"""Apply the compact inventory-table update to version 0.1.0 source."""

import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
component = root / "custom_components/scottibyte_incus"
path = component / "frontend/panel.js"
source = path.read_text()
if 'class="instance-details"' in source:
    raise SystemExit("Compact table update is already applied.")

source = source.replace("this.busy = new Map();", "this.expanded = new Set(); this.busy = new Map();", 1)
old = "[['server','Server'],['name','Instance'],['project','Project'],['type','Type'],['status','Status'],['ips','IP address'],['dns','DNS name'],['macs','MAC'],['cpu_percent','CPU %'],['memory_bytes','Memory'],['disk_bytes','Disk used / limit']]"
new = "[['server','Server'],['name','Instance'],['status','Status'],['ips','IP address'],['cpu_percent','CPU %'],['memory_bytes','Memory'],['disk_bytes','Disk used / limit']]"
assert old in source, "Unexpected table header; stopped without writing."
source = source.replace(old, new, 1)
start = source.index("      const mem=bytes(i.memory_bytes)")
end = source.index("    }).join('');", start)
source = (
    source[:start]
    + r"""      const opened=this.expanded.has(this.key(i));
      const ips=i.ips||[];
      const primaryIP=ips.find(ip=>!ip.includes(':'))||ips[0]||'—';
      const location=i.location && i.location!=='none' ? i.location : '';
      return `<tr class="instance-row ${!i.online?'stale':''}"><td><button class="host-link" data-drill="${index}">${escapeHTML(i.server)}</button>${location?`<small>${escapeHTML(location)}</small>`:''}</td>
      <td><strong>${escapeHTML(i.name)}</strong><small>${i.type==='container'?'Container':'VM'} · ${escapeHTML(i.project)}</small><button class="details-toggle" data-details="${index}" aria-expanded="${opened}">${opened?'Hide details ▴':'Details ▾'}</button></td>
      <td><span class="badge ${statusClass}">${escapeHTML(status)}${!i.online?' · stale':''}</span></td>
      <td class="primary-ip mono">${escapeHTML(primaryIP)}${ips.length>1?`<small>+${ips.length-1} more in Details</small>`:''}</td>
      <td title="100% equals one CPU core">${i.cpu_percent==null?'—':i.cpu_percent.toFixed(1)}</td>
      <td>${bytes(i.memory_bytes)}${i.memory_limit!=null?`<small>of ${bytes(i.memory_limit)}</small>`:''}</td>
      <td>${bytes(i.disk_bytes)}<small>of ${bytes(i.disk_limit)}</small></td>
      <td><div class="row-actions">${i.status==='Stopped'?`<button data-action="start" data-index="${index}" ${!i.online||busy?'disabled':''}>Start</button>`:i.status==='Running'?`<button class="stop" data-action="stop" data-index="${index}" ${!i.online||busy?'disabled':''}>Stop</button>`:''}
      ${i.type==='container'?`<button data-action="terminal" data-index="${index}" ${!i.online||busy||i.status!=='Running'?'disabled':''}>Terminal</button>`:''}</div></td></tr>
      ${opened?`<tr class="detail-row"><td colspan="8"><div class="instance-details">
      <section><h3>IP addresses</h3><div class="address-list mono">${ips.map(escapeHTML).join('<br>')||'—'}</div></section>
      <section><h3>MAC addresses</h3><div class="address-list mono">${(i.macs||[]).map(escapeHTML).join('<br>')||'—'}</div></section>
      <section><h3>Instance details</h3><dl><dt>Server</dt><dd>${escapeHTML(i.server)}</dd><dt>Location</dt><dd>${escapeHTML(location)||'—'}</dd><dt>Project</dt><dd>${escapeHTML(i.project)}</dd><dt>DNS name</dt><dd>${escapeHTML(i.dns)||'—'}</dd></dl></section>
      </div></td></tr>`:''}`;
"""
    + source[end:]
)
anchor = "    this.shadowRoot.querySelectorAll('[data-action]').forEach"
assert anchor in source
source = source.replace(
    anchor,
    "    this.shadowRoot.querySelectorAll('[data-details]').forEach(b=>b.onclick=()=>{const key=this.key(this.displayRows[+b.dataset.details]);if(this.expanded.has(key))this.expanded.delete(key);else this.expanded.add(key);this.render();});\n"
    + anchor,
    1,
)
css = """
:host{min-width:0;max-width:100%;overflow-x:hidden}main,#inventory{min-width:0;max-width:100%}
.table-scroll{max-width:100%;max-height:65vh;overflow:auto;scrollbar-gutter:stable;scrollbar-width:auto}
table{table-layout:fixed;min-width:900px;border-collapse:separate;border-spacing:0}
th,td{padding:12px 10px;vertical-align:middle;overflow-wrap:anywhere}
th{position:sticky;top:0;z-index:2;white-space:normal}th button{text-align:left;line-height:1.5}
th:nth-child(1){width:10%}th:nth-child(2){width:19%}th:nth-child(3){width:12%}th:nth-child(4){width:16%}
th:nth-child(5){width:7%}th:nth-child(6){width:11%}th:nth-child(7){width:11%}th:nth-child(8){width:14%}
th:last-child,td:last-child:not([colspan]){position:sticky;right:0;background:var(--card);box-shadow:-5px 0 8px #0002;z-index:1}
th:last-child{top:0;z-index:3;background:var(--primary-background-color,#0d121c)}
.row-actions{flex-direction:column;align-items:stretch;gap:5px}.row-actions button{white-space:nowrap}
.primary-ip{white-space:normal;overflow-wrap:anywhere}.host-link{white-space:normal;text-align:left}
.details-toggle{display:block;border:0;padding:4px 0 0;font-size:11px;color:var(--blue)}
.instance-details{display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px;padding:4px 6px}
.instance-details h3{font-size:12px;color:var(--muted);margin:0 0 10px}
.address-list{max-height:160px;overflow:auto;white-space:normal;overflow-wrap:anywhere;line-height:1.6}
.instance-details dl{display:grid;grid-template-columns:auto 1fr;gap:6px 12px;margin:0;font-size:12px}
.instance-details dt{color:var(--muted)}.instance-details dd{margin:0;overflow-wrap:anywhere}
.detail-row td{background:var(--primary-background-color,#0d121c)}
@media(max-width:600px){.instance-details{grid-template-columns:1fr}.table-scroll{max-height:70vh}}
"""
anchor = "// xterm's CSS must live"
assert anchor in source
source = source.replace(anchor, "const TABLE_STYLE = " + json.dumps(css) + ";\n" + anchor, 1)
source = source.replace("${STYLE}</style>", "${STYLE}${TABLE_STYLE}</style>", 1)
path.write_text(source)
manifest = component / "manifest.json"
data = json.loads(manifest.read_text())
data["version"] = "0.1.1"
manifest.write_text(json.dumps(data, indent=2) + "\n")
constants = component / "const.py"
constants.write_text(constants.read_text().replace('VERSION = "0.1.0"', 'VERSION = "0.1.1"'))
print("Compact table update applied; version 0.1.1.")

# Add the regression to the existing browser check.
browser_test = root / "tools/browser_smoke.py"
test_source = browser_test.read_text()
test_anchor = '                assert page.locator("tbody tr").count() == 3\n'
regression = "                # Reproduce narrow HA content with long IPv6 and many virtual NICs.\n                page.set_viewport_size({\"width\": 1220, \"height\": 1000})\n                page.evaluate(\"\"\"async () => {\n                    servers[0].instances[0].ips.push('172.17.0.1', '172.18.0.1', '2601:2c4:4000:c70:1266:6aff:fe63:dfa5');\n                    servers[0].instances[0].macs = Array.from({length:40}, (_,i) => '02:42:ac:11:00:' + i.toString(16).padStart(2,'0'));\n                    await document.querySelector('scottibyte-incus-panel').refresh();\n                }\"\"\")\n                table = page.locator('.table-scroll')\n                assert table.evaluate('(e) => e.scrollWidth <= e.clientWidth + 1')\n                assert page.locator('tbody .instance-row').first.bounding_box()['height'] < 140\n                action_box = page.locator('tbody .row-actions').first.bounding_box()\n                assert action_box['x'] + action_box['width'] <= 1220\n                page.locator('[data-details=\"0\"]').click()\n                assert page.locator('.instance-details').count() == 1\n                assert '02:42:ac:11:00:27' in page.locator('.instance-details').inner_text()\n                assert '2601:2c4:4000:c70:1266:6aff:fe63:dfa5' in page.locator('.instance-details').inner_text()\n                page.evaluate(\"document.querySelector('scottibyte-incus-panel').render()\")\n                assert page.locator('.instance-details').count() == 1\n                page.screenshot(path=str(screenshots / 'network-details.png'), full_page=True)\n                page.locator('[data-details=\"0\"]').click()\n                page.set_viewport_size({\"width\": 760, \"height\": 1000})\n                action_box = page.locator('tbody .row-actions').first.bounding_box()\n                assert action_box['x'] + action_box['width'] <= 760\n                page.set_viewport_size({\"width\": 1220, \"height\": 1000})\n"
if "Reproduce narrow HA content" not in test_source:
    assert test_anchor in test_source, "Unexpected browser test layout"
    browser_test.write_text(test_source.replace(test_anchor, test_anchor + regression, 1))
