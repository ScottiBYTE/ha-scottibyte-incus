/* ScottiBYTE Incus dashboard. All privileged requests use HA's authenticated WS. */
const BASE = '/scottibyte_incus_static';
const API = 'scottibyte_incus/';
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const bytes = n => {
  if (n == null) return '—';
  if (n < 1024) return `${n} B`;
  const p = Math.min(Math.floor(Math.log(n) / Math.log(1024)), 4);
  return `${(n / 1024 ** p).toFixed(1)} ${['B','KiB','MiB','GiB','TiB'][p]}`;
};
let terminalLibraries;
function loadScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement('script'); s.src = src; s.onload = resolve;
    s.onerror = () => { s.remove(); reject(new Error('Could not load bundled terminal library')); };
    document.head.append(s);
  });
}
function loadTerminal() {
  if (!terminalLibraries) terminalLibraries = (async () => {
    await loadScript(`${BASE}/vendor/xterm.js`);
    await loadScript(`${BASE}/vendor/fit.js`);
  })().catch(err => { terminalLibraries = undefined; throw err; });
  return terminalLibraries;
}
class ScottiBYTEIncusPanel extends HTMLElement {
  constructor() {
    super(); this.attachShadow({mode:'open'});
    this.servers = []; this.selected = ''; this.query = ''; this.sort = 'name'; this.direction = 1;
    this.busy = new Map(); this.error = ''; this.notice = ''; this._active = false;
  }
  set hass(value) { this._hass = value; if (this.isConnected && !this._active) this.start(); }
  get hass() { return this._hass; }
  connectedCallback() { this.build(); if (this.hass) this.start(); }
  disconnectedCallback() { this._active = false; clearInterval(this.timer); this.closeTerminal(); }
  build() {
    this.shadowRoot.innerHTML = `<style>${STYLE}</style>
      <header><div class="brand"><button id="menu" aria-label="Open sidebar">☰</button><div><h1>ScottiBYTE <span>Incus</span></h1><p>Your servers. One view.</p></div></div>
      <div class="header-actions"><span id="updated"></span><button id="refresh">Refresh</button><a href="/config/integrations/integration/scottibyte_incus">Manage servers ↗</a></div></header>
      <main><div id="message" role="status" aria-live="polite"></div><section aria-label="Instance summary" id="summary"></section>
      <div class="toolbar"><div><h2 id="viewtitle">Servers</h2><p id="subtitle">Select a server to explore its instances.</p></div><label class="search"><span>⌕</span><input id="search" type="search" placeholder="Search instances, servers, IP, MAC…" aria-label="Search all servers and instances"></label></div>
      <section id="servers" aria-label="Incus servers"></section>
      <section id="inventory" hidden><div class="table-heading"><button id="back">← All servers</button><span id="tablecount"></span></div><div class="table-scroll"><table><thead><tr>
        ${[['server','Server'],['name','Instance'],['project','Project'],['type','Type'],['status','Status'],['ips','IP address'],['dns','DNS name'],['macs','MAC'],['cpu_percent','CPU %'],['memory_bytes','Memory'],['disk_bytes','Disk used / limit']].map(([key,label]) => `<th><button data-sort="${key}">${label} ↕</button></th>`).join('')}<th>Actions</th>
      </tr></thead><tbody></tbody></table></div><p class="footnote">CPU: 100% equals one CPU core. Limits and guest metrics show — when Incus does not report them. Offline inventory is last known data.</p></section>
      <div id="empty" hidden></div></main>
      <dialog id="confirm"><form method="dialog"><h2>Stop instance?</h2><p id="confirmtext"></p><p>An orderly shutdown will be requested.</p><div class="dialog-actions"><button value="cancel">Cancel</button><button class="danger" value="stop">Stop instance</button></div></form></dialog>
      <dialog id="terminaldialog"><div class="terminal-heading"><div><h2 id="terminaltitle">Container terminal</h2><span>Root shell · closes after 15 minutes without input</span></div><button id="terminalclose">Close terminal</button></div><div id="terminalstatus" role="status"></div><div id="terminal"></div></dialog>`;
    const $ = s => this.shadowRoot.querySelector(s);
    $('#menu').onclick = () => this.dispatchEvent(new CustomEvent('hass-toggle-menu', {bubbles:true, composed:true}));
    $('#refresh').onclick = () => this.refresh(true);
    $('#search').oninput = e => { this.query = e.target.value; this.render(); };
    $('#back').onclick = () => { this.selected = ''; this.query = ''; $('#search').value = ''; this.render(); };
    this.shadowRoot.querySelectorAll('[data-sort]').forEach(el => el.onclick = () => {
      const key = el.dataset.sort; this.direction = this.sort === key ? -this.direction : 1; this.sort = key; this.render();
    });
    $('#terminalclose').onclick = () => this.closeTerminal();
    $('#terminaldialog').addEventListener('cancel', () => this.closeTerminal());
    this.render();
  }
  async start() { this._active = true; await this.refresh(); if (!this._active) return; this.timer = setInterval(() => this.refresh(), 5000); }
  async refresh(force = false) {
    if (this.fetching || !this.hass) return;
    this.fetching = true;
    try {
      if (force) await this.hass.callWS({type:API+'refresh'});
      this.servers = await this.hass.callWS({type:API+'inventory'});
      this.error = ''; this.render();
      this.shadowRoot.querySelector('#updated').textContent = `View updated ${new Date().toLocaleTimeString()}`;
    } catch (err) { this.error = err.message || String(err); this.render(); }
    finally { this.fetching = false; }
  }
  render() {
    if (!this.shadowRoot.querySelector('#summary')) return;
    const $ = s => this.shadowRoot.querySelector(s);
    const reachable = this.servers.filter(s => s.online).length;
    const stale = this.servers.some(s => !s.online);
    const totals = this.servers.reduce((a,s) => { for (const k of ['total','running','stopped','containers','vms']) a[k] = (a[k]||0) + s.counts[k]; return a; }, {});
    $('#summary').innerHTML = [
      ['Total instances',totals.total||0,'blue'],['Running',totals.running||0,'green'],['Stopped',totals.stopped||0,'amber'],
      ['Containers',totals.containers||0,'blue'],['Virtual machines',totals.vms||0,'purple'],['Servers reachable',`${reachable} / ${this.servers.length}`,'green']
    ].map(([label,value,color])=>`<article class="stat ${color}"><span>${label}</span><strong>${value}</strong>${stale && label !== 'Servers reachable' ? '<small>Includes last known inventory</small>':''}</article>`).join('');
    $('#message').textContent = this.error || this.notice;
    $('#message').className = this.error ? 'error' : this.notice ? 'notice' : '';
    const searching = !!this.query.trim(); const query = this.query.trim().toLowerCase();
    const matches = (server, instance) => [server.name, server.server_name, instance.name, instance.project, instance.location, instance.status, instance.dns, ...(instance.ips||[]), ...(instance.macs||[])].join(' ').toLowerCase().includes(query);
    const selectedServer = this.servers.find(s => s.id === this.selected);
    $('#viewtitle').textContent = searching ? 'Search results' : selectedServer ? selectedServer.name : 'Servers';
    $('#subtitle').textContent = searching ? 'Matching instances across every configured server.' : selectedServer ? `${selectedServer.clustered ? 'Cluster' : 'Server'} inventory · Last successful update: ${selectedServer.last_success ? new Date(selectedServer.last_success).toLocaleString() : 'Never'}` : 'Select a server to explore its instances.';
    $('#servers').hidden = searching || !!selectedServer;
    $('#servers').innerHTML = this.servers.map(s => `<button class="server-card ${s.online ? '' : 'offline'}" data-server="${escapeHTML(s.id)}">
      <div class="card-top"><span class="server-icon">▤</span><span class="badge ${s.online?'running':'unknown'}">${s.online?'Online':'Offline · stale'}</span></div>
      <h3>${escapeHTML(s.name)}</h3><p>Incus ${escapeHTML(s.version||'—')}${s.clustered?' · Cluster':''}</p>
      <div class="card-counts"><span><strong>${s.counts.containers}</strong> containers</span><span><strong>${s.counts.vms}</strong> VMs</span></div>
      <div class="card-bottom"><span>${s.counts.running} running · ${s.counts.stopped} stopped</span><span>View →</span></div></button>`).join('');
    this.shadowRoot.querySelectorAll('[data-server]').forEach(b => b.onclick = () => { this.selected=b.dataset.server; this.render(); });
    let rows = this.servers.flatMap(s => s.instances.map(i => ({...i, server:s.name, serverId:s.id, online:s.online, last_success:s.last_success})));
    rows = rows.filter(i => searching ? matches(this.servers.find(s=>s.id===i.serverId),i) : i.serverId === this.selected);
    rows.sort((a,b)=> {
      const av=a[this.sort], bv=b[this.sort];
      return this.direction * (typeof av === 'number' && typeof bv === 'number' ? av-bv : String(av??'').localeCompare(String(bv??''),undefined,{numeric:true}));
    });
    this.displayRows = rows;
    $('#inventory').hidden = !searching && !selectedServer;
    $('#tablecount').textContent = `${rows.length} instance${rows.length===1?'':'s'}`;
    $('tbody').innerHTML = rows.map((i,index)=> {
      const busy=this.busy.get(this.key(i)); const status=busy ? busy : i.status;
      const statusClass = !i.online?'unknown':status==='Running'?'running':status==='Stopped'?'stopped':'unknown';
      const mem=bytes(i.memory_bytes)+(i.memory_limit!=null?` / ${bytes(i.memory_limit)}`:'');
      return `<tr class="${!i.online?'stale':''}"><td><button class="host-link" data-drill="${index}">${escapeHTML(i.server)}</button>${i.location?`<small>${escapeHTML(i.location)}</small>`:''}</td>
      <td><strong>${escapeHTML(i.name)}</strong></td><td>${escapeHTML(i.project)}</td><td>${i.type==='container'?'Container':'VM'}</td>
      <td><span class="badge ${statusClass}">${escapeHTML(status)}${!i.online?' · stale':''}</span></td>
      <td class="mono">${(i.ips||[]).map(escapeHTML).join('<br>')||'—'}</td><td>${escapeHTML(i.dns)||'—'}</td>
      <td class="mono">${(i.macs||[]).map(escapeHTML).join('<br>')||'—'}</td>
      <td title="100% equals one CPU core">${i.cpu_percent==null?'—':i.cpu_percent.toFixed(1)}</td><td class="nowrap">${mem}</td><td class="nowrap">${bytes(i.disk_bytes)} / ${bytes(i.disk_limit)}</td>
      <td><div class="row-actions">${i.status==='Stopped'?`<button data-action="start" data-index="${index}" ${!i.online||busy?'disabled':''}>Start</button>`:i.status==='Running'?`<button class="stop" data-action="stop" data-index="${index}" ${!i.online||busy?'disabled':''}>Stop</button>`:''}
      ${i.type==='container'?`<button data-action="terminal" data-index="${index}" ${!i.online||busy||i.status!=='Running'?'disabled':''}>Terminal</button>`:''}</div></td></tr>`;
    }).join('');
    this.shadowRoot.querySelectorAll('[data-action]').forEach(b=>b.onclick=()=>this.runAction(b.dataset.action,this.displayRows[+b.dataset.index]));
    this.shadowRoot.querySelectorAll('[data-drill]').forEach(b=>b.onclick=()=>{this.selected=this.displayRows[+b.dataset.drill].serverId;this.query='';$('#search').value='';this.render();});
    $('#empty').hidden = this.servers.length > 0 && (!searching || rows.length > 0);
    $('#empty').textContent = this.servers.length ? 'No matching instances.' : 'Add your first Incus server in Settings → Devices & services → Add integration → ScottiBYTE Incus.';
  }
  key(i) { return JSON.stringify([i.serverId,i.project,i.name]); }
  target(i) { return {server:i.serverId,project:i.project,name:i.name}; }
  async runAction(action,i) {
    if(action==='terminal') return this.openTerminal(i);
    if(action==='stop') {
      const dialog=this.shadowRoot.querySelector('#confirm');
      this.shadowRoot.querySelector('#confirmtext').textContent=`${i.server} / ${i.project} / ${i.name}`;
      const result=await new Promise(resolve=>{dialog.addEventListener('close',()=>resolve(dialog.returnValue),{once:true});dialog.showModal();});
      if(result!=='stop')return;
    }
    this.busy.set(this.key(i),action==='start'?'Starting…':'Stopping…'); this.notice='';this.render();
    try {
      await this.hass.callWS({type:API+'action',...this.target(i),action});
      this.notice=`${i.name}: ${action==='start'?'started':'stopped'} successfully.`;
    } catch(err) { this.error=err.message||String(err); }
    finally {this.busy.delete(this.key(i));this.render();setTimeout(()=>this.refresh(),1500);}
  }
  async openTerminal(i) {
    await this.closeTerminal();
    const dialog=this.shadowRoot.querySelector('#terminaldialog');
    const status=this.shadowRoot.querySelector('#terminalstatus');
    const generation = this.terminalGeneration = (this.terminalGeneration||0)+1;
    this.shadowRoot.querySelector('#terminaltitle').textContent=`${i.name} · ${i.server} / ${i.project}`;
    status.textContent='Connecting…';dialog.showModal();
    try {
      await loadTerminal();
      if(generation!==this.terminalGeneration)return;
      const terminal=new window.Terminal({cursorBlink:true,fontSize:14,fontFamily:'ui-monospace, monospace',scrollback:5000,theme:{background:'#0c1018',foreground:'#e1e8f2'}});
      this.term=terminal;
      const fit=new window.FitAddon.FitAddon();terminal.loadAddon(fit);
      terminal.open(this.shadowRoot.querySelector('#terminal'));fit.fit();
      const send=payload=>this.hass.callWS({type:API+'terminal_input',session:this.session,...payload}).catch(err=>{status.textContent=err.message||String(err);});
      terminal.onData(data=>{if(this.session){const b=new TextEncoder().encode(data);send({data:btoa(String.fromCharCode(...b))});}});
      terminal.onResize(({cols,rows})=>{if(this.session)send({cols,rows});});
      const unsub=await this.hass.connection.subscribeMessage(event=>{
        if(generation!==this.terminalGeneration)return;
        if(event.session){this.session=event.session;status.textContent='Connected as root';send({cols:terminal.cols,rows:terminal.rows});terminal.focus();}
        if(event.data)terminal.write(Uint8Array.from(atob(event.data),c=>c.charCodeAt(0)));
        if(event.closed){this.session=null;status.textContent='Session closed';}
      },{type:API+'terminal_open',...this.target(i),cols:terminal.cols,rows:terminal.rows}, {resubscribe:false});
      if(generation!==this.terminalGeneration){await unsub();return;}
      this.terminalUnsub=unsub;
      this.resizeObserver=new ResizeObserver(()=>fit.fit());this.resizeObserver.observe(this.shadowRoot.querySelector('#terminal'));
    }catch(err){status.textContent=err.message||String(err);}
  }
  async closeTerminal() {
    this.terminalGeneration=(this.terminalGeneration||0)+1;this.session=null;
    this.resizeObserver?.disconnect();this.resizeObserver=null;
    const unsub=this.terminalUnsub;this.terminalUnsub=null;
    if(unsub)try{await unsub();}catch{/* disconnected */}
    this.term?.dispose();this.term=null;
    const container=this.shadowRoot.querySelector('#terminal');if(container)container.replaceChildren();
    this.shadowRoot.querySelector('#terminaldialog')?.close();
  }
}
const STYLE = `
:host{display:block;background:var(--primary-background-color,#0d121c);color:var(--primary-text-color,#e5eaf3);min-height:100vh;font:14px system-ui,sans-serif;--line:var(--divider-color,#293446);--muted:var(--secondary-text-color,#94a3b8);--card:var(--card-background-color,#131c2b);--blue:#38bdf8;--green:#22c55e;--amber:#fbbf24;--purple:#b78afa}*{box-sizing:border-box}header{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:24px 28px;border-bottom:1px solid var(--line);background:var(--card)}.brand{display:flex;align-items:center;gap:15px}h1{margin:0;font-size:25px;letter-spacing:-.8px}h1 span{color:var(--blue)}p{color:var(--muted);margin:6px 0}h2{font-size:19px;margin:0}button,input,a{font:inherit}button,a{border:1px solid var(--line);border-radius:9px;padding:9px 13px;background:transparent;color:inherit;cursor:pointer;text-decoration:none}button:hover,a:hover{border-color:var(--blue);background:#38bdf80b}button:focus-visible,a:focus-visible,input:focus-visible{outline:2px solid var(--blue);outline-offset:3px}button:disabled{opacity:.35;cursor:default}button:disabled:hover{border-color:var(--line)}.header-actions{display:flex;align-items:center;gap:12px}.header-actions span{font-size:12px;color:var(--muted)}main{padding:26px 28px;max-width:2100px;margin:auto}#summary{display:grid;grid-template-columns:repeat(6,minmax(120px,1fr));gap:14px}.stat{position:relative;overflow:hidden;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:19px 20px;min-height:112px}.stat:before{position:absolute;content:'';left:0;top:0;bottom:0;width:4px;background:currentColor}.stat span{display:block;color:var(--muted);font-size:12px}.stat strong{display:block;font-size:29px;font-weight:650;margin-top:8px}.stat small{display:block;font-size:10px;color:var(--muted);margin-top:5px}.blue{color:var(--blue)}.green{color:var(--green)}.amber{color:var(--amber)}.purple{color:var(--purple)}.toolbar{display:flex;justify-content:space-between;align-items:center;gap:18px;margin:30px 0 20px}.search{display:flex;align-items:center;gap:10px;border:1px solid var(--line);border-radius:10px;background:var(--card);padding:0 14px;width:min(100%,440px)}.search span{font-size:25px;color:var(--muted)}input{width:100%;background:transparent;border:0;color:inherit;padding:14px 0;outline:none}#servers{display:grid;grid-template-columns:repeat(auto-fill,minmax(245px,1fr));gap:16px}#servers[hidden],section[hidden],[hidden]{display:none!important}.server-card{text-align:left;background:var(--card);padding:20px;border-radius:13px;transition:border-color .15s,transform .15s}.server-card:hover{transform:translateY(-2px)}.card-top,.card-counts,.card-bottom{display:flex;align-items:center;justify-content:space-between;gap:10px}.server-icon{font-size:28px;color:var(--blue)}.server-card h3{font-size:19px;margin:18px 0 4px}.server-card p{font-size:12px}.card-counts{justify-content:flex-start;gap:24px;padding:19px 0}.card-counts span{font-size:12px;color:var(--muted)}.card-counts strong{font-size:18px;color:var(--primary-text-color,#e5eaf3);margin-right:4px}.card-bottom{border-top:1px solid var(--line);padding-top:14px;font-size:12px;color:var(--muted)}.card-bottom span:last-child{color:var(--blue)}.offline{border-style:dashed}.badge{display:inline-block;font-size:12px;padding:5px 9px;border-radius:20px;white-space:nowrap;border:1px solid transparent}.running{color:#22c55e;background:#22c55e12;border-color:#22c55e40}.stopped{color:#e8ac25;background:#e8ac2512;border-color:#e8ac2540}.unknown{color:var(--muted);background:#94a3b812;border-color:#94a3b840}.table-heading{display:flex;justify-content:space-between;align-items:center;margin:0 0 16px;color:var(--muted)}.table-scroll{border:1px solid var(--line);border-radius:12px;overflow:auto}table{width:100%;border-collapse:collapse;background:var(--card);font-size:13px}th,td{text-align:left;padding:15px 12px;border-bottom:1px solid var(--line)}th{white-space:nowrap;background:var(--primary-background-color,#0d121c);font-size:11px;color:var(--muted)}th button{padding:0;border:0;font-size:inherit}tr:last-child td{border-bottom:0}tr:hover td{background:#94a3b809}td small{display:block;color:var(--muted);font-size:10px;margin-top:5px}.mono{font:12px ui-monospace,monospace;white-space:nowrap}.nowrap{white-space:nowrap}.host-link{border:0;padding:0;color:var(--blue);white-space:nowrap}.row-actions{display:flex;gap:6px}.row-actions button{font-size:12px;padding:6px 10px}.row-actions .stop{color:#fca5a5}.stale td{opacity:.65}.footnote{font-size:11px;margin:14px 0}.error,.notice{padding:12px 16px;margin-bottom:18px;border-radius:9px}.error{background:#ef444418;color:#f87171;border:1px solid #ef444440}.notice{background:#22c55e15;color:#22c55e}#empty{padding:60px 20px;text-align:center;color:var(--muted)}dialog{color:var(--primary-text-color,#e5eaf3);background:var(--card);border:1px solid var(--line);border-radius:14px;max-width:95vw;padding:24px}dialog::backdrop{background:#0009}.dialog-actions{display:flex;justify-content:flex-end;gap:12px;margin-top:25px}.danger{background:#b91c1c;color:white;border-color:#b91c1c}#terminaldialog{width:1100px;padding:18px}#terminal{height:min(65vh,620px);background:#0c1018;padding:10px}.terminal-heading{display:flex;justify-content:space-between;align-items:center;gap:20px;margin-bottom:12px}.terminal-heading span,#terminalstatus{font-size:12px;color:var(--muted)}#terminalstatus{margin:8px 0}#menu{font-size:19px;border:0;padding:5px}@media(max-width:1000px){#summary{grid-template-columns:repeat(3,1fr)}header{align-items:flex-start}.header-actions{flex-wrap:wrap;justify-content:flex-end}.header-actions span{display:none}}@media(max-width:600px){header,main{padding:16px}h1{font-size:20px}.brand p,.header-actions a{display:none}.toolbar{align-items:stretch;flex-direction:column}.search{width:100%}#summary{grid-template-columns:repeat(2,1fr);gap:8px}.stat{padding:15px;min-height:94px}.stat strong{font-size:24px}.terminal-heading{align-items:flex-start}.terminal-heading h2{font-size:15px}}`;
// xterm's CSS must live in the same shadow root as its terminal DOM.
const originalBuild=ScottiBYTEIncusPanel.prototype.build;
ScottiBYTEIncusPanel.prototype.build=function(){originalBuild.call(this);const css=document.createElement('link');css.rel='stylesheet';css.href=BASE+'/vendor/xterm.css';this.shadowRoot.append(css);};
if(!customElements.get('scottibyte-incus-panel'))customElements.define('scottibyte-incus-panel',ScottiBYTEIncusPanel);
