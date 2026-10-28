"""Host counters, restricted enrollment, cleanup, and independent availability."""
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import asyncssh
import pytest

from custom_components.scottibyte_incus.coordinator import IncusCoordinator
from custom_components.scottibyte_incus.host_metrics import HostMonitor, authorized_line, install, normalize


def sample(**changes):
    return {'schema': 1, 'boot_id': 'boot', 'cpu_total': 1000, 'cpu_idle': 800,
            'memory_total': 10000, 'memory_available': 4000,
            'filesystems': [{'mount': '/', 'filesystem': 'ext4', 'used': 300, 'total': 1000}], **changes}


def test_host_cpu_memory_and_storage_are_independent_of_instances():
    first = sample()
    assert normalize(first, None)['cpu_percent'] is None
    value = normalize(sample(cpu_total=2000, cpu_idle=1500), first)
    assert value['cpu_percent'] == 30.0
    assert value['memory_percent'] == 60.0
    assert value['memory_used'] == 6000
    assert value['filesystems'][0]['used'] == 300
    assert normalize(sample(boot_id='reboot'), first)['cpu_percent'] is None
    assert normalize(sample(cpu_total=10, cpu_idle=5), first)['cpu_percent'] is None
    assert normalize(sample(memory_available=None), None)['memory_percent'] is None
    with pytest.raises(ValueError):
        normalize(sample(memory_available=20000), None)


def test_authorized_key_cannot_open_shell_or_forward_ports():
    key = asyncssh.generate_private_key('ssh-ed25519')
    public = key.export_public_key().decode()
    line = authorized_line(public, 'ha-scottibyte-host-test')
    parsed = asyncssh.import_authorized_keys(line)
    options = parsed.validate(key.convert_to_public(), '', '')
    assert options['restrict'] is True
    assert 'base64' in options['command']
    assert len(line.encode()) < 8192


@pytest.mark.asyncio
@pytest.mark.usefixtures('socket_enabled')
@pytest.mark.parametrize('reject_key', [False, True])
async def test_enrollment_poll_and_remove_preserve_other_ssh_keys(tmp_path, reject_key):
    remote_home = tmp_path / 'remote'
    remote_home.mkdir()
    sshdir = remote_home / '.ssh'
    sshdir.mkdir()
    existing = asyncssh.generate_private_key('ssh-ed25519').export_public_key().decode().strip() + ' existing-user-key\n'
    authorized = sshdir / 'authorized_keys'
    authorized.write_text(existing)
    hostkey = asyncssh.generate_private_key('ssh-ed25519')
    forced = {}

    class Server(asyncssh.SSHServer):
        def connection_made(self, conn):
            self.peer = conn.get_extra_info('peername')

        def begin_auth(self, username):
            return True

        def password_auth_supported(self):
            return True

        def validate_password(self, username, password):
            return username == 'scott' and password == 'setup-only-secret'

        def public_key_auth_supported(self):
            return True

        def validate_public_key(self, username, key):
            if reject_key:
                return False
            options = asyncssh.import_authorized_keys(authorized.read_text()).validate(key, '', '')
            if options is not None and options.get('command'):
                forced[self.peer] = options['command']
                return True
            return False

    async def process(proc):
        command = forced.get(proc.get_extra_info('peername'), proc.command)
        env = {**os.environ, 'HOME': str(remote_home), 'SSH_ORIGINAL_COMMAND': proc.command}
        child = await asyncio.create_subprocess_shell(command, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env)
        payload = None
        # Installer alone expects JSON on stdin; collector does not.
        if command == proc.command:
            import base64
            import re
            match = re.search(r"b64decode\('([A-Za-z0-9+/=]+)'\)", command.replace("'\"'\"'", "'"))
            if match and 'json.load(sys.stdin)' in base64.b64decode(match[1]).decode():
                payload = await proc.stdin.read()
        stdout, stderr = await child.communicate(payload.encode() if payload else None)
        proc.stdout.write(stdout.decode())
        proc.stderr.write(stderr.decode())
        proc.exit(child.returncode)

    listener = await asyncssh.create_server(Server, '127.0.0.1', 0, server_host_keys=[hostkey], process_factory=process)
    hass = SimpleNamespace(config=SimpleNamespace(path=lambda *parts: str((tmp_path / 'ha').joinpath(*parts))), async_add_executor_job=AsyncMock(side_effect=lambda fn, *args: fn(*args)))
    try:
        if reject_key:
            with pytest.raises(ValueError, match='restricted metrics key'):
                await install(hass, {'host': '127.0.0.1', 'ssh_port': listener.get_port(), 'username': 'scott', 'password': 'setup-only-secret'}, hostkey.convert_to_public())
            assert authorized.read_text() == existing
            assert not list((tmp_path / 'ha/.storage/scottibyte_incus').glob('metrics-*'))
            return
        config = await install(hass, {'host': '127.0.0.1', 'ssh_port': listener.get_port(), 'username': 'scott', 'password': 'setup-only-secret'}, hostkey.convert_to_public())
        assert 'password' not in config
        directory = Path(hass.config.path('.storage', 'scottibyte_incus', config['credential_id']))
        assert (directory / 'ssh.key').stat().st_mode & 0o777 == 0o600
        assert 'setup-only-secret' not in ''.join(p.read_text() for p in directory.iterdir())
        assert existing.strip() in authorized.read_text()
        assert config['marker'] in authorized.read_text()
        monitor = HostMonitor(hass, config)
        first = await monitor.collect()
        second = await monitor.collect()
        assert first['online'] and second['online']
        assert second['memory_total'] > 0
        assert second['cpu_percent'] is not None
        pinned = directory / 'host.pub'
        original_pin = pinned.read_text()
        pinned.write_bytes(asyncssh.generate_private_key('ssh-ed25519').export_public_key())
        assert not (await monitor.collect())['online']
        pinned.write_text(original_pin)
        assert (await monitor.collect())['online']
        # A request for a shell is still forced to return metrics by this key.
        async with await monitor.connection() as conn:
            result = await conn.run('uname -a', check=True)
            assert json.loads(result.stdout)['schema'] == 1
        await monitor.remove()
        assert authorized.read_text() == existing
    finally:
        listener.close()
        await listener.wait_closed()


@pytest.mark.asyncio
async def test_host_metrics_can_be_online_when_incus_is_offline():
    host = {'configured': True, 'online': True, 'cpu_percent': 42.0}
    obj = SimpleNamespace(host_monitor=SimpleNamespace(collect=AsyncMock(return_value=host)), client=SimpleNamespace(inventory=AsyncMock(side_effect=OSError('Incus down'))), entry=SimpleNamespace(data={'projects': ['*']}, title='Host'), snapshot={'online': False, 'instances': []}, _sample_at=None)
    value = await IncusCoordinator._async_update_data(obj)
    assert not value['online']
    assert value['host_metrics']['online']
    assert value['host_metrics']['cpu_percent'] == 42.0


@pytest.mark.asyncio
async def test_collector_failure_marks_stale_and_resets_cpu_baseline():
    monitor = HostMonitor(SimpleNamespace(), {'credential_id': 'unused'})
    monitor.last = {'configured': True, 'online': True, 'cpu_percent': 25.0, 'last_success': 'yesterday'}
    monitor.previous = sample()
    monitor.connection = AsyncMock(side_effect=OSError('Host unavailable'))
    value = await monitor.collect()
    assert value['online'] is False
    assert value['cpu_percent'] == 25.0
    assert value['last_success'] == 'yesterday'
    assert monitor.previous is None
