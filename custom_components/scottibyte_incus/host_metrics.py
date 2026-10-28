"""Whole Linux host measurements over a metrics-only, pinned SSH connection."""

import base64
import json
import shlex
import shutil
from pathlib import Path
from uuid import uuid4

import asyncssh

from .const import DOMAIN

# Runs as the SSH account on the host, independent of Incus and guest agents.
# No third-party Python packages, sudo, listener, or persistent daemon required.
COLLECTOR = r'''
import fcntl,json,os,re,sys
from pathlib import Path
marker=sys.argv[1]
if os.environ.get('SSH_ORIGINAL_COMMAND')=='remove-ha-host-metrics':
    path=Path.home()/'.ssh/authorized_keys'
    with path.open('r+') as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        lines=f.readlines()
        f.seek(0);f.writelines(line for line in lines if not line.rstrip().endswith(' '+marker));f.truncate()
    print(json.dumps({'removed':True}));sys.exit()
fields=[int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]
mem={}
for line in Path('/proc/meminfo').read_text().splitlines():
    key,value=line.split(':',1);mem[key]=int(value.split()[0])*1024
mounts=[];seen=set()
# Local persistent filesystems; network, pseudo and container overlay mounts are excluded.
allowed={'ext2','ext3','ext4','xfs','btrfs','zfs','f2fs','vfat','exfat','ntfs','ntfs3','bcachefs','jfs','reiserfs'}
for line in Path('/proc/self/mountinfo').read_text().splitlines():
    left,right=line.split(' - ',1);a=left.split();b=right.split()
    if b[0] not in allowed:continue
    if a[3]!='/' and b[0]!='btrfs':continue
    mount=re.sub(r'\\([0-7]{3})',lambda m:chr(int(m[1],8)),a[4])
    if mount.startswith(('/var/lib/docker/','/run/','/snap/')):continue
    if mount.startswith(('/var/lib/incus/','/var/lib/lxd/')) and any(part in mount for part in ('/containers/','/virtual-machines/','/snapshots/')):continue
    if len(mounts)>=64:break
    identity=(a[2],b[0])
    if identity in seen:continue
    try:
        st=os.statvfs(mount)
        total=st.f_blocks*st.f_frsize
        if total<=0:continue
        mounts.append({'mount':mount,'filesystem':b[0],'used':(st.f_blocks-st.f_bfree)*st.f_frsize,'total':total})
        seen.add(identity)
    except OSError:pass
mounts.sort(key=lambda m:(m['mount']!='/',m['mount']))
print(json.dumps({'schema':1,'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),'cpu_total':sum(fields),'cpu_idle':fields[3]+fields[4],'memory_total':mem['MemTotal'],'memory_available':mem.get('MemAvailable'),'filesystems':mounts}))
'''

INSTALLER = r'''
import fcntl,json,os,sys
from pathlib import Path
request=json.load(sys.stdin)
directory=Path.home()/'.ssh';directory.mkdir(mode=0o700,exist_ok=True)
path=directory/'authorized_keys'
with path.open('a+') as f:
    os.chmod(path,0o600);fcntl.flock(f,fcntl.LOCK_EX)
    f.seek(0);previous=f.read()
    f.seek(0,2)
    if previous and not previous.endswith('\n'):f.write('\n')
    f.write(request['line']+'\n')
print(json.dumps({'installed':True}))
'''


def python_command(source, marker=None):
    encoded = base64.b64encode(source.encode()).decode()
    code = f"import base64;exec(base64.b64decode('{encoded}'))"
    return "python3 -c " + shlex.quote(code) + (" " + shlex.quote(marker) if marker else "")


def authorized_line(public_key, marker):
    command = python_command(COLLECTOR, marker).replace('\\', '\\\\').replace('"', '\\"')
    line = f'restrict,command="{command}" {public_key.strip()} {marker}'
    if len(line.encode()) >= 8192:
        raise ValueError("Host metrics key exceeds the OpenSSH line limit")
    return line


async def install(hass, settings, host_key):
    """Enroll a metrics-only identity and roll back failed setup attempts."""
    from homeassistant.components import persistent_notification

    ident = "metrics-" + uuid4().hex
    marker = "ha-scottibyte-host-" + ident.removeprefix("metrics-")
    key = asyncssh.generate_private_key('ssh-ed25519')
    line = authorized_line(key.export_public_key().decode(), marker)
    keys = [asyncssh.import_private_key(settings['ssh_key'], settings.get('key_passphrase') or None)] if settings.get('ssh_key') else []
    config = {'credential_id': ident, 'host': settings['host'], 'port': settings['ssh_port'],
              'username': settings['username'], 'marker': marker}
    directory = Path(hass.config.path('.storage', DOMAIN, ident))

    def connection():
        return asyncssh.connect(host=settings['host'], port=settings['ssh_port'], username=settings['username'],
            password=settings.get('password') or None, client_keys=keys, agent_path=None,
            known_hosts=([host_key], [], []), connect_timeout=10, login_timeout=15)

    def save():
        directory.mkdir(mode=0o700, parents=True)
        for name, content in [('ssh.key', key.export_private_key().decode()), ('host.pub', host_key.export_public_key().decode())]:
            path = directory / name
            path.write_text(content)
            path.chmod(0o600)

    attempted_install = False
    try:
        async with connection() as conn:
            # Verify Python and OS counters before modifying authorized_keys.
            result = await conn.run(python_command(COLLECTOR, marker), check=True, timeout=12)
            normalize(json.loads(result.stdout), None)
            attempted_install = True
            await conn.run(python_command(INSTALLER), input=json.dumps({'line': line}), check=True, timeout=12)
        await hass.async_add_executor_job(save)
        # Custom AuthorizedKeysFile/ForceCommand policies may reject a valid key.
        monitor = HostMonitor(hass, config)
        value = await monitor.collect()
        if not value['online']:
            raise ValueError('The restricted metrics key could not authenticate')
    except BaseException:
        if attempted_install:
            try:
                async with connection() as conn:
                    await conn.run("SSH_ORIGINAL_COMMAND=remove-ha-host-metrics " + python_command(COLLECTOR, marker), check=True, timeout=12)
            except Exception:
                persistent_notification.async_create(hass,
                    f"Host metrics setup failed. Remove only the authorized_keys line ending with {marker} from SSH account {settings['username']} on {settings['host']}.",
                    title="Host metrics setup cleanup required")
        await hass.async_add_executor_job(shutil.rmtree, directory, True)
        raise
    return config


def normalize(raw, previous):
    """Calculate CPU deltas and memory use; never infer host load from guests."""
    if raw.get('schema') != 1 or not isinstance(raw.get('boot_id'), str):
        raise ValueError('Invalid host metrics response')
    total, idle = int(raw['cpu_total']), int(raw['cpu_idle'])
    if total < 0 or idle < 0 or idle > total:
        raise ValueError('Invalid CPU counters')
    cpu = None
    if previous and previous['boot_id'] == raw['boot_id']:
        delta, idle_delta = total - previous['cpu_total'], idle - previous['cpu_idle']
        if delta > 0 and 0 <= idle_delta <= delta:
            cpu = round(100 * (delta - idle_delta) / delta, 1)
    memory_total = int(raw['memory_total'])
    available = raw.get('memory_available')
    if memory_total <= 0 or (available is not None and not 0 <= int(available) <= memory_total):
        raise ValueError('Invalid memory counters')
    used = memory_total - int(available) if available is not None else None
    disks = []
    for fs in raw.get('filesystems', [])[:64]:
        used_bytes, total_bytes = int(fs['used']), int(fs['total'])
        if 0 <= used_bytes <= total_bytes and total_bytes > 0:
            disks.append({'mount': str(fs['mount']), 'filesystem': str(fs['filesystem']), 'used': used_bytes, 'total': total_bytes})
    return {'online': True, 'configured': True, 'cpu_percent': cpu, 'memory_percent': round(100 * used / memory_total, 1) if used is not None else None,
            'memory_used': used, 'memory_total': memory_total, 'filesystems': disks}


class HostMonitor:
    def __init__(self, hass, config):
        self.hass, self.config, self.previous = hass, config, None
        self.last = {'configured': bool(config), 'online': False}

    async def connection(self):
        config = self.config
        directory = Path(self.hass.config.path('.storage', DOMAIN, config['credential_id']))

        def credentials():
            return asyncssh.read_private_key(directory / 'ssh.key'), asyncssh.read_public_key(directory / 'host.pub')

        key, host_key = await self.hass.async_add_executor_job(credentials)
        return await asyncssh.connect(host=config['host'], port=config['port'], username=config['username'],
            client_keys=[key], password=None, agent_path=None, known_hosts=([host_key], [], []),
            connect_timeout=6, login_timeout=6)

    async def collect(self):
        from .models import utc_now

        if not self.config:
            return self.last
        try:
            async with await self.connection() as conn:
                result = await conn.run('host-metrics', check=True, timeout=10)
                if len(result.stdout) > 131072:
                    raise ValueError('Host metrics response too large')
                raw = json.loads(result.stdout)
                self.last = {**normalize(raw, self.previous), 'last_success': utc_now()}
                self.previous = {key: raw[key] for key in ('boot_id', 'cpu_total', 'cpu_idle')}
        except Exception:
            self.previous = None
            self.last = {**self.last, 'online': False, 'configured': True}
        return self.last

    async def remove(self):
        if not self.config:
            return
        async with await self.connection() as conn:
            result = await conn.run('remove-ha-host-metrics', check=True, timeout=10)
            if json.loads(result.stdout).get('removed') is not True:
                raise ValueError('Host key removal failed')
