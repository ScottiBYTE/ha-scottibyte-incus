/* ScottiBYTE Incus dashboard. All privileged requests use HA's authenticated WS. */
const FRONTEND_VERSION = new URL(import.meta.url).searchParams.get('v');
const BASE = '/scottibyte_incus_static';
const API = 'scottibyte_incus/';
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const bytes = n => {
  if (n == null) return '—';
  if (n < 1024) return `${n} B`;
  const p = Math.min(Math.floor(Math.log(n) / Math.log(1024)), 4);
  return `${(n / 1024 ** p).toFixed(1)} ${['B','KiB','MiB','GiB','TiB'][p]}`;
};
const percent = value => Number.isFinite(value) ? `${value.toFixed(1)}%` : '—';
function hostMetrics(metrics) {
  if (!metrics?.configured) return '<p class="host-metrics-hint">Host metrics not configured</p>';
  const cpu = metrics.cpu_percent == null && metrics.online ? 'Sampling…' : percent(metrics.cpu_percent);
  return `<section class="host-metrics" aria-label="Whole-server utilization">
    <dl><div><dt>CPU${metrics.online?'':' <small class="metrics-stale">last known</small>'}</dt><dd>${cpu}</dd></div><div><dt>Memory</dt><dd>${percent(metrics.memory_percent)}</dd></div></dl>
    <div class="host-disks" aria-label="Local filesystem usage">${(metrics.filesystems||[]).map(d=>`<div class="host-disk"><span title="${escapeHTML(d.mount)} · ${escapeHTML(d.filesystem)}">${escapeHTML(d.mount)}</span><strong>${bytes(d.used)} / ${bytes(d.total)}</strong></div>`).join('')||'<p class="host-metrics-hint">Storage unavailable</p>'}</div></section>`;
}
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
    this.serverOrder = []; this.draftOrder = null; this.savingOrder = false; this.servers = []; this.selected = ''; this.query = ''; this.sort = 'name'; this.direction = 1;
    this.expanded = new Set(); this.busy = new Map(); this.error = ''; this.notice = ''; this._active = false;
  }
  set hass(value) { this._hass = value; if (this.isConnected && !this._active) this.start(); }
  get hass() { return this._hass; }
  connectedCallback() { this.build(); if (this.hass) this.start(); }
  disconnectedCallback() { this._active = false; clearInterval(this.timer); this.closeTerminal(); }
  build() {
    this.shadowRoot.innerHTML = `<style>${STYLE}${TABLE_STYLE}${SERVER_STYLE}${SNAPSHOT_SPACING_STYLE}${MOBILE_ACTION_STYLE}${MOBILE_SERVER_NAME_STYLE}${CARD_ALIGNMENT_STYLE}${COMPACT_METRICS_STYLE}</style>
      <header><div class="brand"><button id="menu" aria-label="Open sidebar">☰</button><div><h1>ScottiBYTE <span>Incus</span></h1><div class="brand-meta"><span class="app-version" aria-label="Dashboard version">${FRONTEND_VERSION ? `v${escapeHTML(FRONTEND_VERSION)}` : 'Version unavailable'}</span><a class="donate-link" href="https://www.paypal.com/paypalme/ScottiBYTE" target="_blank" rel="noopener noreferrer" aria-label="Donate to ScottiBYTE through PayPal">Donate ↗</a></div><p>Your servers. One view.</p></div></div>
      <div class="header-actions"><span id="updated"></span><button id="refresh">Refresh</button><label class="refresh-setting">Refresh every<select id="refresh-interval" aria-label="Server polling interval"><option value="10">10 sec</option><option value="30" selected>30 sec</option><option value="60">1 min</option><option value="300">5 min</option></select></label><a class="add-server" href="/config/integrations/dashboard/add?domain=scottibyte_incus">Add server</a><a href="/config/integrations/integration/scottibyte_incus">Manage servers ↗</a></div></header>
      <main><div id="message" role="status" aria-live="polite"></div><section aria-label="Instance summary" id="summary"></section>
      <div class="toolbar"><div><h2 id="viewtitle">Servers</h2><p id="subtitle">Select a server to explore its instances.</p></div><label class="search"><span>⌕</span><input id="search" type="search" placeholder="Search instances, servers, IP, MAC…" aria-label="Search all servers and instances"></label></div>
      <div id="order-controls"></div><section id="servers" aria-label="Incus servers"></section>
      <section id="inventory" hidden><div class="table-heading"><button id="back">← All servers</button><span id="tablecount"></span></div><div class="table-scroll"><table><thead><tr>
        ${[['server','Server'],['name','Instance'],['status','Status'],['ips','IP address'],['cpu_host_percent','CPU % of host'],['memory_bytes','Memory'],['disk_bytes','Disk used / limit']].map(([key,label]) => `<th><button data-sort="${key}">${label} ↕</button></th>`).join('')}<th>Actions</th>
      </tr></thead><tbody></tbody></table></div><p class="footnote">CPU: share of the instance’s host logical CPU capacity; not its configured CPU limit. Two samples are required. See Details for core usage. Limits and guest metrics show — when Incus does not report them. Offline inventory is last known data.</p></section>
      <div id="empty" hidden></div></main>
      <dialog id="snapshots-dialog"><div class="terminal-heading"><h2 id="snapshots-title">Snapshots</h2><button id="snapshots-close">Close</button></div><p>Snapshots include the instance disk and configuration, without running memory. Attached custom volumes require separate backups.</p><div class="snapshot-create"><label>Snapshot name (optional)<input id="snapshot-name" maxlength="63" placeholder="Automatic name"></label><button id="snapshot-create">Create snapshot</button><button id="snapshots-refresh">Refresh list</button></div><p id="snapshots-status" role="status" aria-live="polite"></p><div id="snapshot-list"></div></dialog>
      <dialog id="snapshot-confirm"><form method="dialog"><h2 id="snapshot-confirm-title"></h2><p id="snapshot-confirm-text"></p><label id="snapshot-rename-label" hidden>New name<input id="snapshot-rename" maxlength="63"></label><div class="dialog-actions"><button value="cancel">Cancel</button><button id="snapshot-confirm-submit" value="confirm">Confirm</button></div></form></dialog>
      <dialog id="confirm"><form method="dialog"><h2>Stop instance?</h2><p id="confirmtext"></p><p>An orderly shutdown will be requested.</p><div class="dialog-actions"><button value="cancel">Cancel</button><button class="danger" value="stop">Stop instance</button></div></form></dialog>
      <dialog id="terminaldialog"><div class="terminal-heading"><div><h2 id="terminaltitle">Guest terminal</h2><span id="terminalhint">Root shell · closes after 15 minutes without input</span></div><button id="terminalclose">Close terminal</button></div><div id="terminalstatus" role="status"></div><div id="terminal"></div></dialog>`;
    const $ = s => this.shadowRoot.querySelector(s);
    $('#menu').onclick = () => this.dispatchEvent(new CustomEvent('hass-toggle-menu', {bubbles:true, composed:true}));
    $('#refresh').onclick = () => this.refresh(true);
    $('#refresh-interval').onchange = async event => {
      const control = event.target;
      control.disabled = true;
      try {
        const prefs = await this.hass.callWS({type:API+'refresh_interval',seconds:Number(control.value)});
        control.value = String(prefs.refresh_seconds);
        this.notice = 'Refresh interval saved for all servers.';
        this.error = '';this.render();
      } catch(err) {this.error=err.message||String(err);this.render();await this.refresh();}
      finally {control.disabled=false;}
    };
    $('#search').oninput = e => { this.query = e.target.value; this.render(); };
    $('#back').onclick = () => { this.selected = ''; this.query = ''; $('#search').value = ''; this.render(); };
    this.shadowRoot.querySelectorAll('[data-sort]').forEach(el => el.onclick = () => {
      const key = el.dataset.sort; this.direction = this.sort === key ? -this.direction : 1; this.sort = key; this.render();
    });
    $('#snapshots-close').onclick = () => {if(!this.snapshotBusy){$('#snapshots-dialog').close();this.snapshotTarget=null;}};
    $('#snapshots-dialog').addEventListener('cancel', event => {if(this.snapshotBusy)event.preventDefault();else this.snapshotTarget=null;});
    $('#snapshot-create').onclick = () => this.mutateSnapshot('create', $('#snapshot-name').value.trim());
    $('#snapshots-refresh').onclick = () => this.loadSnapshots();
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
      const preferences = await this.hass.callWS({type:API+'dashboard'});
      this.serverOrder = preferences?.server_order || [];
      if(!this.shadowRoot.querySelector('#refresh-interval').disabled)this.shadowRoot.querySelector('#refresh-interval').value=String(preferences?.refresh_seconds||30);
      this.error = ''; if (!this.draftOrder) this.render();
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
    const selectedOffline = this.servers.find(s => s.id === this.selected && !s.online);
    if(selectedOffline){this.selected='';this.offlineNoticeServer=selectedOffline.id;this.offlineNoticeText=`${selectedOffline.name} is offline. Instance listings are unavailable until it reconnects.`;this.notice=this.offlineNoticeText;}
    if(this.offlineNoticeServer && this.servers.some(s=>s.id===this.offlineNoticeServer && s.online)){if(this.notice===this.offlineNoticeText)this.notice='';this.offlineNoticeServer=null;}
    if(this.snapshotTarget && !this.servers.some(s=>s.id===this.snapshotTarget.serverId && s.online)){
      $('#snapshot-list').textContent='Server is offline. Snapshot listings are unavailable.';
      $('#snapshots-status').textContent='Waiting for the server to reconnect.';
    }
    $('#message').textContent = this.error || this.notice;
    $('#message').className = this.error ? 'error' : this.notice ? 'notice' : '';
    const searching = !!this.query.trim(); const query = this.query.trim().toLowerCase();
    const matches = (server, instance) => [server.name, server.server_name, server.host, instance.name, instance.project, instance.location, instance.status, instance.dns, ...(instance.ips||[]), ...(instance.macs||[])].join(' ').toLowerCase().includes(query);
    const selectedServer = this.servers.find(s => s.id === this.selected);
    $('#viewtitle').textContent = searching ? 'Search results' : selectedServer ? selectedServer.name : 'Servers';
    $('#subtitle').textContent = searching ? 'Matching instances across reachable servers.' : selectedServer ? `${selectedServer.clustered ? 'Cluster' : 'Server'} inventory · Last successful update: ${selectedServer.last_success ? new Date(selectedServer.last_success).toLocaleString() : 'Never'}` : 'Select a server to explore its instances.';
    $('#servers').hidden = searching || !!selectedServer;
    const ids = this.draftOrder || this.serverOrder;
    const ordered = [...this.servers].sort((a,b) => {
      const ai=ids.indexOf(a.id), bi=ids.indexOf(b.id);
      return (ai<0?ids.length:ai)-(bi<0?ids.length:bi);
    });
    $('#order-controls').hidden = searching || !!selectedServer;
    $('#order-controls').innerHTML = this.draftOrder ? `<button id="save-order" ${this.savingOrder?'disabled':''}>Save order</button> <button id="cancel-order" ${this.savingOrder?'disabled':''}>Cancel</button><p>Drag a card using its handle, or use the arrow buttons. Saved order applies to all devices.</p>` : this.servers.length>1 ? '<button id="reorder">Reorder servers</button>' : '';
    if ($('#reorder')) $('#reorder').onclick = () => {this.draftOrder=ordered.map(s=>s.id);this.render();};
    if ($('#cancel-order')) $('#cancel-order').onclick = () => {this.draftOrder=null;this.render();};
    if ($('#save-order')) $('#save-order').onclick = async () => {
      this.savingOrder=true;this.render();
      try {const result=await this.hass.callWS({type:API+'server_order',order:ordered.map(s=>s.id)});this.serverOrder=result.server_order;this.draftOrder=null;this.error='';}
      catch(err){this.error=err.message||String(err);}
      finally{this.savingOrder=false;this.render();}
    };
    $('#servers').innerHTML = ordered.map((s,index) => `<div class="server-wrap" data-card="${escapeHTML(s.id)}">${this.draftOrder?`<button class="drag-handle" aria-label="Drag ${escapeHTML(s.name)} to reorder" ${this.savingOrder?'disabled':''}>⠿ Drag to reorder</button>`:''}<button class="server-card ${s.online ? '' : 'offline'}" data-server="${escapeHTML(s.id)}" ${!s.online?'disabled aria-label="'+escapeHTML(s.name)+' is offline; instance listing unavailable"':''}>
      <div class="card-top"><span class="server-icon">▤</span><span class="badge ${s.online?'running':'unknown'}">${s.online?'Online':'Offline · stale'}</span></div>
      <div class="card-identity"><h3 title="${escapeHTML(s.name)}">${escapeHTML(s.name)}</h3><p class="server-address" title="${escapeHTML(s.host||'Address unavailable')}">${escapeHTML(s.host||'Address unavailable')}</p><p class="card-version">Incus ${escapeHTML(s.version||'—')}${s.clustered?' · Cluster member':''}</p><p class="cluster-member ${s.clustered?'':'membership-placeholder'}" ${s.clustered?'':'aria-hidden="true"'} title="${s.clustered?escapeHTML(s.cluster_member||s.server_name||s.name):''}">${s.clustered?`Member: ${escapeHTML(s.cluster_member||s.server_name||s.name)} · ${s.cluster_members?.length||'?'} members`:'&nbsp;'}</p></div>${hostMetrics(s.host_metrics)}
      <div class="card-counts"><span><strong>${s.counts.containers}</strong> containers</span><span><strong>${s.counts.vms}</strong> VMs</span></div>
      <div class="card-bottom"><span>${s.online?`${s.counts.running} running · ${s.counts.stopped} stopped`:'Last known counts'}</span><span>${s.online?'View →':'Unavailable'}</span></div></button>${this.draftOrder?`<div class="move-controls"><button data-move="${escapeHTML(s.id)}" data-step="-1" aria-label="Move ${escapeHTML(s.name)} earlier" ${index===0||this.savingOrder?'disabled':''}>← Move earlier</button><button data-move="${escapeHTML(s.id)}" data-step="1" aria-label="Move ${escapeHTML(s.name)} later" ${index===ordered.length-1||this.savingOrder?'disabled':''}>Move later →</button></div>`:''}</div>`).join('');
    this.shadowRoot.querySelectorAll('.drag-handle').forEach(handle => {
      handle.onpointerdown = event => {
        if (event.button !== 0 || this.savingOrder) return;
        event.preventDefault();
        const source=handle.closest('[data-card]');
        const sourceId=source.dataset.card;
        let targetId=sourceId;
        handle.setPointerCapture(event.pointerId);
        source.classList.add('dragging');
        handle.onpointermove = move => {
          const target=this.shadowRoot.elementFromPoint(move.clientX,move.clientY)?.closest('[data-card]');
          this.shadowRoot.querySelectorAll('.drop-target').forEach(el=>el.classList.remove('drop-target'));
          targetId=target?.dataset.card || sourceId;
          if(target && targetId!==sourceId)target.classList.add('drop-target');
        };
        const finish = cancelled => {
          handle.onpointermove=null;handle.onpointerup=null;handle.onpointercancel=null;
          if(handle.hasPointerCapture(event.pointerId))handle.releasePointerCapture(event.pointerId);
          if(!cancelled && targetId!==sourceId){
            const order=ordered.map(s=>s.id), from=order.indexOf(sourceId), to=order.indexOf(targetId);
            order.splice(from,1);order.splice(to,0,sourceId);this.draftOrder=order;
          }
          this.render();
        };
        handle.onpointerup=()=>finish(false);
        handle.onpointercancel=()=>finish(true);
      };
    });
    this.shadowRoot.querySelectorAll('[data-move]').forEach(b => b.onclick = () => {
      const order=ordered.map(s=>s.id), index=order.indexOf(b.dataset.move), next=index+Number(b.dataset.step);
      [order[index],order[next]]=[order[next],order[index]];this.draftOrder=order;this.render();
      this.shadowRoot.querySelectorAll('[data-move]').forEach(el=>{if(el.dataset.move===b.dataset.move&&el.dataset.step===b.dataset.step&&!el.disabled)el.focus();});
    });
    this.shadowRoot.querySelectorAll('[data-server]').forEach(b => b.onclick = () => { if (!this.draftOrder && this.servers.some(s=>s.id===b.dataset.server && s.online)) {this.selected=b.dataset.server; this.render();} });
    let rows = this.servers.filter(s=>s.online).flatMap(s => s.instances.map(i => ({...i, server:s.name, serverId:s.id, online:s.online, last_success:s.last_success})));
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
      const opened=this.expanded.has(this.key(i));
      const ips=i.ips||[];
      const primaryIP=i.primary_ip||ips.find(ip=>!ip.includes(':'))||ips[0]||'—';
      const location=i.location && i.location!=='none' ? i.location : '';
      return `<tr class="instance-row ${!i.online?'stale':''}"><td><button class="host-link" title="${escapeHTML(i.server)}" data-drill="${index}">${escapeHTML(i.server)}</button>${location?`<small>${escapeHTML(location)}</small>`:''}</td>
      <td><strong>${escapeHTML(i.name)}</strong><small>${i.type==='container'?'Container':'VM'} · ${escapeHTML(i.project)}</small><button class="details-toggle" data-details="${index}" aria-expanded="${opened}">${opened?'Hide details ▴':'Details ▾'}</button></td>
      <td><span class="badge ${statusClass}">${escapeHTML(status)}${!i.online?' · stale':''}</span></td>
      <td class="primary-ip mono">${escapeHTML(primaryIP)}${ips.length>1?`<small>+${ips.length-1} more in Details</small>`:''}</td>
      <td title="Share of this host’s logical CPU capacity">${i.cpu_host_percent==null?'—':i.cpu_host_percent.toFixed(1)+'%'}</td>
      <td>${bytes(i.memory_bytes)}${i.memory_limit!=null?`<small>of ${bytes(i.memory_limit)}</small>`:''}</td>
      <td>${bytes(i.disk_bytes)}<small>of ${bytes(i.disk_limit)}</small></td>
      <td><div class="row-actions">${i.status==='Stopped'?`<button data-action="start" data-index="${index}" ${!i.online||busy?'disabled':''}>Start</button>`:i.status==='Running'?`<button class="stop" data-action="stop" data-index="${index}" ${!i.online||busy?'disabled':''}>Stop</button>`:''}
      <div class="snapshot-row"><button data-snapshot="${index}" data-create="yes" ${!i.online||busy?'disabled':''}>Snapshot</button><button data-snapshot="${index}" title="Manage snapshots" ${!i.online||busy?'disabled':''}>Manage</button></div>${(i.terminal_supported??(i.type==='container'))?`<button data-action="terminal" data-index="${index}" ${!i.online||busy||i.status!=='Running'?'disabled':''}>Terminal</button>`:''}</div></td></tr>
      ${opened?`<tr class="detail-row"><td colspan="8"><div class="instance-details">
      <section><h3>IP addresses</h3><div class="address-list mono">${ips.map(escapeHTML).join('<br>')||'—'}</div></section>
      <section><h3>MAC addresses</h3><div class="address-list mono">${(i.macs||[]).map(escapeHTML).join('<br>')||'—'}</div></section>
      <section><h3>Instance details</h3><dl><dt>Server</dt><dd>${escapeHTML(i.server)}</dd><dt>Location</dt><dd>${escapeHTML(location)||'—'}</dd><dt>Project</dt><dd>${escapeHTML(i.project)}</dd><dt>DNS name</dt><dd>${escapeHTML(i.dns)||'—'}</dd><dt>CPU cores used</dt><dd>${i.cpu_cores_used==null?'—':i.cpu_cores_used.toFixed(2)}</dd><dt>Host logical CPUs</dt><dd>${i.host_cpu_count??'—'}</dd></dl></section>
      </div></td></tr>`:''}`;
    }).join('');
    this.shadowRoot.querySelectorAll('[data-details]').forEach(b=>b.onclick=()=>{const key=this.key(this.displayRows[+b.dataset.details]);if(this.expanded.has(key))this.expanded.delete(key);else this.expanded.add(key);this.render();});
    this.shadowRoot.querySelectorAll('[data-snapshot]').forEach(b=>b.onclick=()=>this.openSnapshots(this.displayRows[+b.dataset.snapshot],b.dataset.create==='yes'));
    this.shadowRoot.querySelectorAll('[data-action]').forEach(b=>b.onclick=()=>this.runAction(b.dataset.action,this.displayRows[+b.dataset.index]));
    this.shadowRoot.querySelectorAll('[data-drill]').forEach(b=>b.onclick=()=>{this.selected=this.displayRows[+b.dataset.drill].serverId;this.query='';$('#search').value='';this.render();});
    $('#empty').hidden = this.servers.length > 0 && (!searching || rows.length > 0);
    $('#empty').textContent = this.servers.length ? 'No matching instances.' : 'Add your first Incus server in Settings → Devices & services → Add integration → ScottiBYTE Incus.';
  }
  async openSnapshots(item, create) {
    this.snapshotTarget={...item};
    const $=s=>this.shadowRoot.querySelector(s);
    $('#snapshots-title').textContent=`Snapshots · ${item.name} · ${item.server} / ${item.project}`;
    $('#snapshot-name').value='';$('#snapshot-list').replaceChildren();
    $('#snapshots-dialog').showModal();
    await this.loadSnapshots();
    if(create)$('#snapshot-name').focus();
  }
  async loadSnapshots() {
    if(!this.snapshotTarget || this.snapshotBusy)return;
    const target=this.snapshotTarget, $=s=>this.shadowRoot.querySelector(s);
    $('#snapshots-status').textContent='Loading…';
    try {
      const items=await this.hass.callWS({type:API+'snapshots',...this.target(target)});
      if(this.snapshotTarget!==target || !this.servers.some(s=>s.id===target.serverId && s.online))return;
      $('#snapshot-list').innerHTML=items.length?items.map((item,index)=>`<article class="snapshot-item"><strong>${escapeHTML(item.name)}</strong><small>Created: ${escapeHTML(item.created_at?new Date(item.created_at).toLocaleString():'—')} · Expires: ${escapeHTML(item.expires_at&&!item.expires_at.startsWith('0001-')?new Date(item.expires_at).toLocaleString():'Never')} · ${item.stateful?'Contains saved memory':'No saved memory'}</small><div><button data-snap-action="rename" data-snap-index="${index}">Rename</button><button data-snap-action="restore" data-snap-index="${index}">Restore</button><button data-snap-action="delete" data-snap-index="${index}">Delete</button></div></article>`).join(''):'<p>No snapshots yet.</p>';
      $('#snapshots-status').textContent=`${items.length} snapshot${items.length===1?'':'s'}.`;
      this.shadowRoot.querySelectorAll('[data-snap-action]').forEach(button=>button.onclick=()=>this.confirmSnapshot(button.dataset.snapAction,items[+button.dataset.snapIndex].name));
    }catch(err){if(this.snapshotTarget===target)$('#snapshots-status').textContent=err.message||String(err);}
  }
  async confirmSnapshot(action, name) {
    if(this.snapshotBusy)return;
    const $=s=>this.shadowRoot.querySelector(s), dialog=$('#snapshot-confirm');
    $('#snapshot-confirm-title').textContent=`${action[0].toUpperCase()+action.slice(1)} snapshot?`;
    $('#snapshot-confirm-text').textContent=action==='restore'?`Restore ${name} to ${this.snapshotTarget.name} on ${this.snapshotTarget.server}? Current instance disk and configuration will be replaced. Incus will restart the instance if it is currently running; a stopped instance will remain stopped. Saved running memory is not restored.`:action==='delete'?`Permanently delete snapshot ${name} from ${this.snapshotTarget.name} on ${this.snapshotTarget.server}?`:`Rename snapshot ${name}`;
    $('#snapshot-rename-label').hidden=action!=='rename';$('#snapshot-rename').value=name;
    dialog.returnValue='';dialog.showModal();
    await new Promise(resolve=>dialog.addEventListener('close',resolve,{once:true}));
    if(dialog.returnValue==='confirm')await this.mutateSnapshot(action,name,$('#snapshot-rename').value.trim());
  }
  async mutateSnapshot(action, snapshot, newName='') {
    if(this.snapshotBusy || !this.snapshotTarget)return;
    const $=s=>this.shadowRoot.querySelector(s);
    this.snapshotBusy=true;
    const disable=state=>this.shadowRoot.querySelectorAll('#snapshots-dialog button,#snapshots-dialog input').forEach(el=>el.disabled=state);
    disable(true);$('#snapshots-status').textContent=`${action} in progress…`;
    try {
      await this.hass.callWS({type:API+'snapshot_action',...this.target(this.snapshotTarget),action,snapshot,new_name:newName});
      this.snapshotBusy=false;await this.loadSnapshots();$('#snapshot-name').value='';
      $('#snapshots-status').textContent=`Snapshot ${action} completed.`;
    }catch(err){$('#snapshots-status').textContent=err.message||String(err);}
    finally{this.snapshotBusy=false;disable(false);}
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
    this.shadowRoot.querySelector('#terminalhint').textContent=`${i.type==='virtual-machine'?'VM guest shell via Incus agent':'Container root shell'} · closes after 15 minutes without input`;
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
const TABLE_STYLE = "\n:host{min-width:0;max-width:100%;overflow-x:hidden}main,#inventory{min-width:0;max-width:100%}\n.table-scroll{max-width:100%;max-height:65vh;overflow:auto;scrollbar-gutter:stable;scrollbar-width:auto}\ntable{table-layout:fixed;min-width:900px;border-collapse:separate;border-spacing:0}\nth,td{padding:12px 10px;vertical-align:middle;overflow-wrap:anywhere}\nth{position:sticky;top:0;z-index:2;white-space:normal}th button{text-align:left;line-height:1.5}\nth:nth-child(1){width:10%}th:nth-child(2){width:19%}th:nth-child(3){width:12%}th:nth-child(4){width:16%}\nth:nth-child(5){width:7%}th:nth-child(6){width:11%}th:nth-child(7){width:11%}th:nth-child(8){width:14%}\nth:last-child,td:last-child:not([colspan]){position:sticky;right:0;background:var(--card);box-shadow:-5px 0 8px #0002;z-index:1}\nth:last-child{top:0;z-index:3;background:var(--primary-background-color,#0d121c)}\n.row-actions{flex-direction:column;align-items:stretch;gap:5px}.row-actions button{white-space:nowrap}\n.primary-ip{white-space:normal;overflow-wrap:anywhere}.host-link{white-space:normal;text-align:left}\n.details-toggle{display:block;border:0;padding:4px 0 0;font-size:11px;color:var(--blue)}\n.instance-details{display:grid;grid-template-columns:1fr 1fr 1fr;gap:20px;padding:4px 6px}\n.instance-details h3{font-size:12px;color:var(--muted);margin:0 0 10px}\n.address-list{max-height:160px;overflow:auto;white-space:normal;overflow-wrap:anywhere;line-height:1.6}\n.instance-details dl{display:grid;grid-template-columns:auto 1fr;gap:6px 12px;margin:0;font-size:12px}\n.instance-details dt{color:var(--muted)}.instance-details dd{margin:0;overflow-wrap:anywhere}\n.detail-row td{background:var(--primary-background-color,#0d121c)}\n@media(max-width:600px){.instance-details{grid-template-columns:1fr}.table-scroll{max-height:70vh}}\n";
const SERVER_STYLE = '.host-metrics{margin:14px 0;min-width:0}.host-metrics-hint{font-size:11px!important;line-height:1.5;white-space:normal!important}.host-metrics dl{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:8px 0 12px}.host-metrics dl>div{display:flex;justify-content:space-between;gap:8px;min-width:0}.host-metrics dt{color:var(--muted);font-size:12px}.host-metrics dd{margin:0;font-size:12px;white-space:nowrap}.host-disks{max-height:144px;overflow:auto}.host-disk{display:flex;flex-wrap:wrap;justify-content:space-between;gap:4px 10px;font-size:11px;line-height:1.7;margin:5px 0}.host-disk>span{overflow-wrap:anywhere;min-width:0}.host-disk strong{font-weight:500;white-space:nowrap}.refresh-setting{display:flex;align-items:center;gap:7px;font-size:12px;white-space:nowrap}.refresh-setting select{font:inherit;background:var(--card);color:inherit;border:1px solid var(--line);padding:8px;border-radius:8px}@media(max-width:600px){.header-actions{flex-wrap:wrap}.refresh-setting{justify-content:flex-end;width:100%}.host-disk{font-size:12px}} #terminaldialog{width:min(1100px,calc(100vw - 24px));max-width:calc(100vw - 24px)}#terminaldialog .terminal-heading>div{min-width:0}#terminaltitle,#terminalhint,#terminalstatus{overflow-wrap:anywhere}#terminalhint{display:block;line-height:1.5}#terminalclose{flex-shrink:0}@media(max-width:600px){#terminaldialog{padding:12px}#terminaldialog .terminal-heading{gap:10px}#terminal{padding:4px}} .cluster-member{font-size:12px;line-height:1.5;overflow-wrap:anywhere;margin:8px 0!important}.server-card h3{overflow-wrap:anywhere} /* Release branding */ .brand-meta{display:flex;align-items:center;gap:12px;margin-top:7px;flex-wrap:wrap}.app-version{font-size:12px;color:var(--muted);white-space:nowrap}.donate-link{display:inline-flex;align-items:center;padding:3px 9px;font-size:12px;line-height:1.5;border-color:var(--blue);color:var(--blue);white-space:nowrap} .server-card:disabled{opacity:1;cursor:not-allowed}.server-card:disabled:hover{transform:none;background:var(--card);border-color:var(--line)}.server-address{font-family:ui-monospace,monospace;overflow-wrap:anywhere;margin:8px 0!important;color:var(--primary-text-color)!important} #snapshots-dialog{width:850px;max-height:85vh;overflow:auto}.snapshot-create{display:flex;align-items:end;gap:8px;flex-wrap:wrap}.snapshot-create label{flex:1;min-width:160px}.snapshot-create input,#snapshot-rename{border:1px solid var(--line);border-radius:6px;padding:8px}.snapshot-item{padding:12px 0;border-bottom:1px solid var(--line)}.snapshot-item small{display:block;color:var(--muted);margin:6px 0}.snapshot-item button{margin:3px}.snapshot-row{display:flex;gap:4px}.snapshot-row button{flex:1;min-width:0;padding:4px!important;font-size:10px!important}.row-actions button{padding:4px 7px} .drag-handle{display:block;width:100%;margin-bottom:6px;touch-action:none;cursor:grab}.dragging{opacity:.55}.drop-target{outline:3px solid var(--blue);outline-offset:3px;border-radius:13px} .server-wrap{min-width:0}.server-wrap .server-card{width:100%;height:100%}.server-wrap:has(.move-controls) .server-card{height:auto}.move-controls{display:flex;gap:6px;padding:8px 0}.move-controls button{flex:1}#order-controls{margin-bottom:16px}#order-controls p{color:var(--secondary-text-color)} .header-actions a.add-server{display:inline-block;background:#0284c7;color:white;border-color:#0284c7}';
// xterm's CSS must live in the same shadow root as its terminal DOM.
const originalBuild=ScottiBYTEIncusPanel.prototype.build;
ScottiBYTEIncusPanel.prototype.build=function(){originalBuild.call(this);const css=document.createElement('link');css.rel='stylesheet';css.href=BASE+'/vendor/xterm.css';this.shadowRoot.append(css);};
const SNAPSHOT_SPACING_STYLE = "\n/* Snapshot dialog spacing, v0.1.7. */\n#snapshots-dialog{padding:28px;line-height:1.5}\n#snapshots-dialog .terminal-heading{align-items:flex-start;margin-bottom:18px;gap:24px}\n#snapshots-title{min-width:0;overflow-wrap:anywhere;line-height:1.35}\n#snapshots-close{flex-shrink:0}\n#snapshots-dialog>.terminal-heading+p{margin:0 0 24px}\n.snapshot-create{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:end;gap:12px}\n.snapshot-create label{display:flex;flex-direction:column;gap:8px;min-width:0}\n.snapshot-create input{margin:0;padding:10px 12px;min-height:44px}\n.snapshot-create>button{min-height:44px;white-space:nowrap}\n#snapshots-status{margin:22px 0 8px;line-height:1.5;min-height:21px}\n.snapshot-item{padding:20px 0}\n.snapshot-item strong{display:block;overflow-wrap:anywhere}\n.snapshot-item small{margin:8px 0 14px;line-height:1.6;overflow-wrap:anywhere}\n.snapshot-item>div{display:flex;flex-wrap:wrap;gap:8px}\n.snapshot-item button{margin:0;min-height:40px}\n#snapshot-confirm{width:560px;padding:28px;line-height:1.6}\n#snapshot-confirm h2{line-height:1.35}\n#snapshot-confirm p{margin:18px 0}\n#snapshot-rename-label{display:block;margin-top:18px}\n#snapshot-rename{display:block;margin-top:8px;padding:10px 12px}\n#snapshot-confirm .dialog-actions{margin-top:26px;gap:12px}\n@media(max-width:600px){\n #snapshots-dialog,#snapshot-confirm{padding:20px;width:calc(100vw - 24px);max-width:calc(100vw - 24px)}\n #snapshots-dialog .terminal-heading{gap:12px}\n #snapshots-title{font-size:17px}\n .snapshot-create{grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px}\n .snapshot-create label{grid-column:1/-1}\n .snapshot-create>button{white-space:normal;padding:9px}\n}\n";
const MOBILE_ACTION_STYLE = "\n/* Mobile action controls, v0.1.9. */\n@media(max-width:700px){\n th:nth-child(8),td:nth-child(8):not([colspan]){width:144px;min-width:144px;max-width:144px}\n .row-actions{gap:6px}\n .row-actions .snapshot-row{display:flex;flex-direction:column;gap:6px}\n .row-actions button,.row-actions .snapshot-row button{\n   display:block;box-sizing:border-box;width:100%;min-width:0;min-height:36px;\n   padding:7px 8px!important;font-size:12px!important;line-height:1.3;\n   white-space:normal;overflow-wrap:normal;word-break:normal\n }\n}\n";
const MOBILE_SERVER_NAME_STYLE = "\n/* Mobile server names, v0.1.10. */\n@media(max-width:700px){\n th:nth-child(1),td:nth-child(1):not([colspan]){width:128px;min-width:128px;max-width:128px}\n td:nth-child(1) .host-link{\n   display:block;max-width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;\n   overflow-wrap:normal;word-break:normal\n }\n}\n";
const CARD_ALIGNMENT_STYLE = "\n/* Consistent card sections, v1.2.0-beta.2. */\n.server-wrap{display:flex;flex-direction:column;min-width:0}\n.server-wrap>.server-card{display:flex;flex-direction:column;align-items:stretch;justify-content:flex-start;flex:1 1 auto;height:auto;min-width:0}\n.server-card .card-top,.card-identity{flex:0 0 auto}\n.card-identity h3{line-height:1.4;margin:14px 0 4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}\n.card-identity .server-address{margin:4px 0!important;line-height:1.5;height:1.5em;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}\n.card-identity .card-version{margin:4px 0;line-height:1.5;height:1.5em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}\n.card-identity .cluster-member{margin:4px 0!important;line-height:1.5;height:1.5em;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}\n.server-card .host-metrics{flex:1 0 auto;margin:12px 0 0}\n.server-card .host-metrics>.host-metrics-hint{height:1.5em;line-height:1.5;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.server-card .host-metrics dl{grid-template-columns:minmax(0,1fr);gap:7px;margin:8px 0 12px}\n.host-metrics dd,.host-disk strong,.card-counts strong{font-variant-numeric:tabular-nums}\n.server-card .host-disks{height:132px;max-height:132px;overflow:auto;scrollbar-gutter:stable}\n.server-card .host-disk{display:grid;grid-template-columns:minmax(0,1fr) max-content;align-items:baseline;gap:8px;margin:6px 0;line-height:1.5}\n.server-card .host-disk>span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;overflow-wrap:normal}\n.server-card .host-disk strong{text-align:right;white-space:nowrap}\n.server-card .card-counts{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:auto;padding:18px 0;flex:0 0 auto}\n.card-counts>span{display:flex;align-items:baseline;gap:5px;white-space:nowrap}\n.card-counts strong{margin-right:0;min-width:3ch;text-align:right}\n.server-card .card-bottom{margin-top:0;flex:0 0 auto}\n.server-wrap>.drag-handle,.server-wrap>.move-controls{flex:0 0 auto}\n@media(max-width:600px){\n .card-identity .server-address{height:auto;min-height:1.5em;display:block;white-space:normal;overflow-wrap:anywhere}\n .card-identity .membership-placeholder{display:none}\n .server-card .host-metrics>.host-metrics-hint{height:auto}.server-card .host-disks{height:auto;max-height:132px}\n .server-card .host-disk{grid-template-columns:minmax(0,1fr);gap:2px}\n .server-card .host-disk>span{white-space:normal;overflow-wrap:anywhere}\n}\n";
const COMPACT_METRICS_STYLE = "\n/* Compact resource panel with complete mobile filesystem rows. */\n.server-card{padding:18px}\n.card-identity h3{margin-top:8px}\n.card-identity .cluster-member{margin:0!important}\n.server-card .host-metrics{margin:8px 0 0;padding:10px;border-radius:8px;border-left:2px solid var(--blue);background:color-mix(in srgb,var(--blue) 6%,transparent)}\n.server-card .host-metrics dl{margin:0 0 8px;gap:5px}\n.server-card .host-metrics dt,.server-card .host-metrics dd{font-size:13px;color:var(--primary-text-color)}\n.server-card .host-metrics dd{font-weight:600}\n.metrics-stale{font-size:10px;color:var(--muted);font-weight:400}\n.server-card .host-disks{height:108px;max-height:108px}\n.server-card .host-disk{grid-template-columns:minmax(0,1fr);font-size:12px;margin:0;padding:5px 0;gap:1px;border-top:1px solid var(--line)}\n.server-card .host-disk strong{font-weight:600;text-align:left}\n.server-card .card-counts{padding:12px 0;gap:8px}\n@media(max-width:600px){\n .server-card .host-disks{height:auto;max-height:none;overflow:visible;scrollbar-gutter:auto}\n .server-card .host-disk{grid-template-columns:minmax(0,1fr);gap:2px;padding:7px 0;font-size:13px}\n .server-card .host-disk>span{white-space:normal;overflow:visible;overflow-wrap:anywhere;line-height:1.35}\n .server-card .host-disk strong{text-align:left;white-space:normal;line-height:1.4}\n .server-card .host-metrics dt,.server-card .host-metrics dd{font-size:14px}\n .server-card .card-bottom{gap:8px;flex-wrap:wrap}\n .server-card .card-counts strong{min-width:0}\n}\n";
if(!customElements.get('scottibyte-incus-panel'))customElements.define('scottibyte-incus-panel',ScottiBYTEIncusPanel);

