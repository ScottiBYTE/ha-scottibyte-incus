"""Browser regression checks with simulated HA data; no Incus server is contacted.

Requires Playwright and its Chromium browser. Screenshots go to a temporary
folder by default, or to the directory specified by --screenshots.
"""

import argparse
import shutil
import tempfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
HTML = r"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{margin:0;--primary-background-color:#0d121c;--card-background-color:#131c2b;--primary-text-color:#e5eaf3;--secondary-text-color:#94a3b8;--divider-color:#293446}
</style></head><body><script type="module">
import '/scottibyte_incus_static/panel.js?v=9.8.7';
const make=(name,status,type='container',ip='172.16.1.243')=>({name,status,type,project:'default',location:'',ips:status==='Running'?[ip]:[],macs:['00:16:3e:ab:01:02'],dns:name==='Assist'?'assist':'',cpu_percent:status==='Running'?762:null,cpu_host_percent:status==='Running'?23.8:null,cpu_cores_used:status==='Running'?7.62:null,host_cpu_count:32,primary_ip:status==='Running'?ip:null,memory_bytes:status==='Running'?1048576000:null,memory_limit:2147483648,disk_bytes:2147483648,disk_limit:21474836480});
window.servers=[
{id:'storm',name:'vmsstorm',host:'172.16.1.186',version:'7.5.1',online:true,instances:[make('Assist','Running'),make('Frigate','Stopped'),make('win11','Running','virtual-machine','172.16.1.132')]},
{id:'mist',name:'vmsmist',host:'172.16.1.10',version:'7.5.1',online:true,instances:[make('Authentik','Running','container','172.16.1.228'),make('Assist','Running','container','172.16.1.44')]},
{id:'rain',name:'vmsrain',host:'2001:db8:1234:5678:1234:5678:1234:5678',version:'7.5.1',online:false,instances:[make('Paperless','Running','container','172.16.1.50')]}
];
function recalc(){for(const s of servers){s.last_success=new Date().toISOString();s.counts={total:s.instances.length,running:s.instances.filter(i=>i.status==='Running').length,stopped:s.instances.filter(i=>i.status==='Stopped').length,containers:s.instances.filter(i=>i.type==='container').length,vms:s.instances.filter(i=>i.type==='virtual-machine').length};}}
recalc();window.inputs=[];window.unsubscribed=false;
let snapshots = [];
let terminalCallback;
let serverOrder = JSON.parse(localStorage.getItem('mock-order') || '[]');
const panel=document.createElement('scottibyte-incus-panel');
panel.hass={callWS:async message=>{
if(message.type.endsWith('/dashboard'))return {server_order:serverOrder};
if(message.type.endsWith('/server_order')){serverOrder=message.order;localStorage.setItem('mock-order',JSON.stringify(serverOrder));return {server_order:serverOrder};}
if(message.type.endsWith('/snapshots'))return structuredClone(snapshots);
if(message.type.endsWith('/snapshot_action')){
 if(message.action==='create')snapshots.push({name:message.snapshot||'ha-auto',created_at:'2026-10-25T12:00:00Z',stateful:false});
 if(message.action==='rename')snapshots.find(s=>s.name===message.snapshot).name=message.new_name;
 if(message.action==='delete')snapshots=snapshots.filter(s=>s.name!==message.snapshot);
 return {};
}
if(message.type.endsWith('/inventory'))return structuredClone(servers);
if(message.type.endsWith('/action')){const i=servers.find(s=>s.id===message.server).instances.find(i=>i.name===message.name);i.status=message.action==='start'?'Running':'Stopped';recalc();}
if(message.type.endsWith('/terminal_input')){inputs.push(message);if(message.data&&terminalCallback)terminalCallback({data:btoa('root\r\nroot@container:/# ')});}
},connection:{subscribeMessage:async(cb,msg)=>{terminalCallback=cb;setTimeout(()=>{cb({session:'fake-session'});cb({data:btoa('root@container:/# ')});},20);return async()=>{window.unsubscribed=true;};}}};
document.body.append(panel);
</script></body></html>"""


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshots", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="incus-ui-") as directory:
        webroot = Path(directory)
        screenshots = args.screenshots or webroot / "screenshots"
        screenshots.mkdir(parents=True, exist_ok=True)
        shutil.copytree(ROOT / "custom_components/scottibyte_incus/frontend", webroot / "scottibyte_incus_static")
        (webroot / "index.html").write_text(HTML)
        server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=directory))
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(args=["--no-sandbox"])
                page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}")
                page.wait_for_selector("scottibyte-incus-panel .server-card")
                assert page.locator(".server-card").count() == 3
                assert page.locator(".stat").count() == 6
                assert page.locator(".app-version").inner_text() == "v9.8.7"
                assert page.locator(".donate-link").get_attribute("href") == "https://www.paypal.com/paypalme/ScottiBYTE"
                assert page.locator(".donate-link").get_attribute("target") == "_blank"
                page.locator("#reorder").click()
                handle = page.locator('[data-card="storm"] .drag-handle')
                target = page.locator('[data-card="rain"]')
                start, end = handle.bounding_box(), target.bounding_box()
                page.mouse.move(start["x"] + start["width"]/2, start["y"] + start["height"]/2)
                page.mouse.down()
                page.evaluate("document.querySelector('scottibyte-incus-panel').refresh()")
                page.mouse.move(end["x"] + end["width"]/2, end["y"] + end["height"]/2, steps=12)
                page.mouse.up()
                assert page.locator(".server-card").last.get_attribute("data-server") == "storm"
                page.locator("#cancel-order").click()
                page.locator("#reorder").click()
                page.locator('[data-move="mist"][data-step="-1"]').click()
                assert page.locator(".server-card").first.get_attribute("data-server") == "mist"
                page.locator("#cancel-order").click()
                assert page.locator(".server-card").first.get_attribute("data-server") == "storm"
                page.locator("#reorder").click()
                page.locator('[data-move="mist"][data-step="-1"]').click()
                page.locator("#save-order").click()
                page.reload()
                page.wait_for_selector("scottibyte-incus-panel .server-card")
                assert page.locator(".server-card").first.get_attribute("data-server") == "mist"
                assert (
                    page.locator("a.add-server").get_attribute("href")
                    == "/config/integrations/dashboard/add?domain=scottibyte_incus"
                )
                assert "2 / 3" in page.locator("#summary").inner_text()
                page.screenshot(path=str(screenshots / "overview.png"), full_page=True)
                page.locator("#search").fill("assist")
                assert page.locator("tbody tr").count() == 2
                page.locator('[data-drill="0"]').click()
                assert page.locator("tbody tr").count() == 3
                assert "CPU % of host" in page.locator("thead").inner_text()
                assert "23.8%" in page.locator("tbody").inner_text()
                page.locator('[data-snapshot="0"][data-create="yes"]').click()
                page.locator("#snapshot-name").fill("before-update")
                page.locator("#snapshot-create").click()
                page.wait_for_function("document.querySelector('scottibyte-incus-panel').shadowRoot.querySelector('#snapshot-list').textContent.includes('before-update')")
                page.locator('[data-snap-action="rename"]').click()
                page.locator("#snapshot-rename").fill("renamed")
                page.locator("#snapshot-confirm-submit").click()
                page.wait_for_function("document.querySelector('scottibyte-incus-panel').shadowRoot.querySelector('#snapshot-list').textContent.includes('renamed')")
                page.locator('[data-snap-action="delete"]').click()
                page.locator('#snapshot-confirm button[value="cancel"]').click()
                assert page.locator(".snapshot-item").count() == 1
                page.locator('[data-snap-action="restore"]').click()
                assert "Current instance disk and configuration will be replaced" in page.locator("#snapshot-confirm-text").inner_text()
                assert "Incus will restart the instance if it is currently running" in page.locator("#snapshot-confirm-text").inner_text()
                assert "must be stopped" not in page.locator("#snapshots-dialog").inner_text()
                page.locator('#snapshot-confirm button[value="cancel"]').click()
                page.locator('[data-snap-action="delete"]').click()
                page.locator("#snapshot-confirm-submit").click()
                page.wait_for_function("document.querySelector('scottibyte-incus-panel').shadowRoot.querySelector('#snapshot-list').textContent.includes('No snapshots')")
                page.locator("#snapshots-close").click()
                # Reproduce narrow HA content with long IPv6 and many virtual NICs.
                page.set_viewport_size({"width": 1220, "height": 1000})
                page.evaluate("""async () => {
                    servers[0].instances[0].ips.push('172.17.0.1', '172.18.0.1', '2601:2c4:4000:c70:1266:6aff:fe63:dfa5');
                    servers[0].instances[0].macs = Array.from({length:40}, (_,i) => '02:42:ac:11:00:' + i.toString(16).padStart(2,'0'));
                    await document.querySelector('scottibyte-incus-panel').refresh();
                }""")
                table = page.locator(".table-scroll")
                assert table.evaluate("(e) => e.scrollWidth <= e.clientWidth + 1")
                assert page.locator("tbody .instance-row").first.bounding_box()["height"] < 140
                action_box = page.locator("tbody .row-actions").first.bounding_box()
                assert action_box["x"] + action_box["width"] <= 1220
                page.locator('[data-details="0"]').click()
                assert page.locator(".instance-details").count() == 1
                assert "02:42:ac:11:00:27" in page.locator(".instance-details").inner_text()
                assert "2601:2c4:4000:c70:1266:6aff:fe63:dfa5" in page.locator(".instance-details").inner_text()
                page.evaluate("document.querySelector('scottibyte-incus-panel').render()")
                assert page.locator(".instance-details").count() == 1
                page.screenshot(path=str(screenshots / "network-details.png"), full_page=True)
                page.locator('[data-details="0"]').click()
                page.set_viewport_size({"width": 760, "height": 1000})
                action_box = page.locator("tbody .row-actions").first.bounding_box()
                assert action_box["x"] + action_box["width"] <= 760
                page.set_viewport_size({"width": 1220, "height": 1000})
                page.locator("tr").filter(has=page.locator("td strong", has_text="Frigate")).locator(
                    '[data-action="start"]'
                ).click()
                page.wait_for_function(
                    "document.querySelector('scottibyte-incus-panel').notice.includes('started successfully')"
                )
                page.locator("#refresh").click()
                page.wait_for_timeout(100)
                page.screenshot(path=str(screenshots / "instances.png"), full_page=True)
                row = page.locator("tr").filter(has=page.locator("td strong", has_text="Frigate"))
                row.locator('[data-action="stop"]').click()
                page.locator('#confirm button[value="cancel"]').click()
                assert page.evaluate("servers[0].instances[1].status") == "Running"
                row.locator('[data-action="stop"]').click()
                page.locator('#confirm button[value="stop"]').click()
                page.wait_for_function(
                    "document.querySelector('scottibyte-incus-panel').notice.includes('stopped successfully')"
                )
                assist = page.locator("tr").filter(has=page.locator("td strong", has_text="Assist"))
                assist.locator('[data-action="terminal"]').click()
                page.wait_for_function(
                    "document.querySelector('scottibyte-incus-panel').shadowRoot.querySelector('#terminalstatus').textContent==='Connected as root'"
                )
                page.keyboard.type("whoami")
                page.keyboard.press("Enter")
                page.wait_for_function("inputs.some(i=>i.data)")
                page.screenshot(path=str(screenshots / "terminal.png"), full_page=True)
                page.locator("#terminalclose").click()
                assert page.evaluate("window.unsubscribed")
                windows = page.locator("tr").filter(has=page.locator("td strong", has_text="win11"))
                assert windows.locator('[data-action="terminal"]').count() == 0
                page.evaluate("""async()=>{Object.assign(servers[0].instances[2],{name:'Desktop-2404',terminal_supported:true,guest_os:'ubuntu'});await document.querySelector('scottibyte-incus-panel').refresh();}""")
                for width in (360, 390, 480, 1220):
                    page.set_viewport_size({"width": width, "height": 844})
                    vm = page.locator("tr").filter(has=page.locator("td strong", has_text="Desktop-2404"))
                    vm.locator('[data-action="terminal"]').click()
                    page.wait_for_function("document.querySelector('scottibyte-incus-panel').shadowRoot.querySelector('#terminalstatus').textContent==='Connected as root'")
                    assert "VM guest shell via Incus agent" in page.locator("#terminalhint").inner_text()
                    bounds = page.locator("#terminaldialog").bounding_box()
                    assert bounds["x"] >= 0 and bounds["x"] + bounds["width"] <= width
                    assert bounds["y"] >= 0 and bounds["y"] + bounds["height"] <= 844
                    assert page.locator("#terminalclose").is_visible()
                    page.screenshot(path=str(screenshots / f"vm-terminal-{width}.png"), full_page=False)
                    page.locator("#terminalclose").click()
                page.locator("#back").click()
                assert page.locator('[data-server="rain"]').is_disabled()
                assert "172.16.1.186" in page.locator('[data-server="storm"]').inner_text()
                page.locator("#search").fill("Paperless")
                assert page.locator("tbody tr").count() == 0
                page.locator("#search").fill("")
                page.locator('[data-server="storm"]').click()
                page.evaluate("async()=>{servers[0].online=false;await document.querySelector('scottibyte-incus-panel').refresh();}")
                assert page.locator("#inventory").is_hidden()
                assert "is offline" in page.locator("#message").inner_text()
                page.evaluate("async()=>{servers[0].online=true;await document.querySelector('scottibyte-incus-panel').refresh();}")
                assert page.locator('[data-server="storm"]').is_enabled()
                page.locator("#search").fill("<img src=x onerror=alert(1)>")
                assert page.locator("tbody tr").count() == 0
                page.locator("#search").fill("")
                page.set_viewport_size({"width": 390, "height": 844})
                page.screenshot(path=str(screenshots / "mobile.png"), full_page=True)
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                assert page.locator("a.add-server").is_visible()
                assert page.locator(".app-version").is_visible()
                assert page.locator(".donate-link").is_visible()
                page.locator("#back").click() if page.locator("#back").is_visible() else None
                page.evaluate("""async()=>{Object.assign(servers[0],{name:'VMSCloud-Incus',clustered:true,cluster_id:'abc12345abcdef',cluster_member:'vmscloud-incus',cluster_members:[{name:'vmscloud-incus'},{name:'vmsfog-incus'},{name:'incus-member'}],active_endpoint:'https://vmsfog-incus.very-long-local-domain.example:8443'});await document.querySelector('scottibyte-incus-panel').refresh();}""")
                for width in (360, 390, 480, 1600):
                    page.set_viewport_size({"width": width, "height": 900})
                    label = page.locator(".cluster-member")
                    assert label.is_visible()
                    assert "vmscloud-incus" in label.inner_text()
                    assert "API:" not in page.locator('[data-server="storm"]').inner_text()
                    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                    assert label.evaluate("el => el.scrollWidth <= el.clientWidth")
                    page.screenshot(path=str(screenshots / f"cluster-{width}.png"), full_page=True)
                assert not errors, errors
                browser.close()
                print(
                    "Browser smoke checks passed: summary, global search, drill-down, start/stop confirmation, terminal input/cleanup, stale controls, mobile width, JavaScript errors."
                )
                print(f"Screenshots: {screenshots}")
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    main()
