import asyncio
import base64
import json
import ssl
from datetime import datetime, timedelta, timezone

import pytest
from aiohttp import web
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from custom_components.scottibyte_incus.api import IncusClient, certificate_fingerprint, make_ssl_context
from custom_components.scottibyte_incus.bootstrap import (
    EnrollmentError,
    enroll_token,
    generate_certificate,
    validate_host,
    write_credentials,
)

pytestmark = pytest.mark.usefixtures("socket_enabled")


def server_credentials(tmp_path):
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-incus")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
        .sign(key, hashes.SHA256())
    )
    pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    key_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    write_credentials(tmp_path / "server.crt", tmp_path / "server.key", pem, key_pem)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(tmp_path / "server.crt", tmp_path / "server.key")
    return pem, ctx


@pytest.mark.asyncio
async def test_token_enrollment_and_pinned_api(aiohttp_server, tmp_path):
    pem, ctx = server_credentials(tmp_path)
    registered = False
    cert, key = generate_certificate()
    token = base64.b64encode(
        json.dumps({"fingerprint": certificate_fingerprint(pem), "secret": "secret", "addresses": []}).encode()
    ).decode()

    async def enroll(request):
        nonlocal registered
        body = await request.json()
        assert body["trust_token"] == token
        assert body["certificate"] == base64.b64encode(ssl.PEM_cert_to_DER_cert(cert)).decode()
        registered = True
        return web.json_response({"type": "sync", "metadata": {}})

    async def info(request):
        return web.json_response(
            {
                "type": "sync",
                "metadata": {
                    "auth": "trusted" if registered else "untrusted",
                    "environment": {"server_name": "demo-1"},
                },
            }
        )

    app = web.Application()
    app.router.add_post("/1.0/certificates", enroll)
    app.router.add_get("/1.0", info)
    server = await aiohttp_server(app, ssl=ctx)
    result, metadata = await enroll_token(server.host, server.port, token, cert, key)
    assert result == pem
    assert metadata["auth"] == "trusted"
    invalid = base64.b64encode(json.dumps({"fingerprint": "0" * 64}).encode()).decode()
    with pytest.raises(EnrollmentError, match="does not match"):
        await enroll_token(server.host, server.port, invalid, cert, key)


@pytest.mark.asyncio
async def test_state_wait_and_parallel_terminal_sockets(aiohttp_server, tmp_path):
    pem, ctx = server_credentials(tmp_path)
    cert, key = generate_certificate()
    write_credentials(tmp_path / "client.crt", tmp_path / "client.key", cert, key)
    connected = set()
    ready = asyncio.Event()
    received = []

    async def state(request):
        body = await request.json()
        assert body == {"action": "stop", "timeout": 60, "force": False}
        assert request.query["project"] == "project x"
        return web.json_response({"type": "async", "operation": "/1.0/operations/test"})

    async def wait(request):
        return web.json_response({"type": "sync", "metadata": {"status_code": 200}})

    async def execute(request):
        body = await request.json()
        assert body["interactive"] and body["user"] == 0
        return web.json_response(
            {
                "type": "async",
                "operation": "/1.0/operations/test",
                "metadata": {"metadata": {"fds": {"control": "control", "0": "data"}}},
            }
        )

    async def socket(request):
        secret = request.query["secret"]
        connected.add(secret)
        if len(connected) == 2:
            ready.set()
        # Both connections must arrive before either upgrade completes.
        await asyncio.wait_for(ready.wait(), 2)
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        if secret == "data":
            await ws.send_bytes(b"root@test:# ")
        async for frame in ws:
            received.append((secret, frame.data))
        return ws

    app = web.Application()
    app.router.add_put("/1.0/instances/test/state", state)
    app.router.add_get("/1.0/operations/test/wait", wait)
    app.router.add_post("/1.0/instances/test/exec", execute)
    app.router.add_get("/1.0/operations/test/websocket", socket)
    server = await aiohttp_server(app, ssl=ctx)
    client = IncusClient(
        str(server.make_url("")).rstrip("/"), make_ssl_context(pem, tmp_path / "client.crt", tmp_path / "client.key")
    )
    try:
        await client.change_state("project x", "test", "stop")
        terminal = await client.terminal("project x", "test", 100, 30)
        frame = await asyncio.wait_for(terminal.data.receive(), 2)
        assert frame.data == b"root@test:# "
        await terminal.resize(120, 40)
        await terminal.write(b"whoami\n")
        await terminal.close()
        assert connected == {"control", "data"}
        assert any(secret == "control" and "window-resize" in data for secret, data in received)
    finally:
        await client.close()


def test_host_validation():
    assert validate_host("172.16.0.100") == "172.16.0.100"
    assert validate_host("[::1]") == "::1"
    for bad in ["https://server:8443", "server;whoami", "$(id)", "-option", "host/path", "user@server"]:
        with pytest.raises(ValueError):
            validate_host(bad)


@pytest.mark.asyncio
async def test_automatic_ssh_bootstrap(aiohttp_server, tmp_path):
    import asyncssh

    from custom_components.scottibyte_incus.bootstrap import discover_server, enroll_ssh

    pem, ctx = server_credentials(tmp_path)
    cert, key = generate_certificate()
    token = base64.b64encode(
        json.dumps({"fingerprint": certificate_fingerprint(pem), "secret": "once", "addresses": []}).encode()
    ).decode()
    commands = []

    async def enroll(request):
        assert (await request.json())["trust_token"] == token
        return web.json_response({"type": "sync", "metadata": {}})

    async def info(request):
        return web.json_response({"type": "sync", "metadata": {"auth": "trusted", "environment": {}}})

    app = web.Application()
    app.router.add_post("/1.0/certificates", enroll)
    app.router.add_get("/1.0", info)
    server = await aiohttp_server(app, ssl=ctx)

    class SSHServer(asyncssh.SSHServer):
        def begin_auth(self, username):
            return True

        def password_auth_supported(self):
            return True

        def validate_password(self, username, password):
            return username == "novice" and password == "temporary-password"

    async def process(proc):
        command = proc.command
        commands.append(command)
        if command.startswith("incus --force-local config trust add "):
            proc.stdout.write(token + "\n")
        elif command == "incus --force-local config get core.https_address":
            proc.stdout.write("\n")
        elif command == "incus --force-local query /1.0":
            proc.stdout.write("{}\n")
        elif command.startswith("incus --force-local config set core.https_address "):
            pass
        else:
            proc.exit(1)
            return
        proc.exit(0)

    sshkey = asyncssh.generate_private_key("ssh-ed25519")
    listener = await asyncssh.create_server(
        SSHServer, "127.0.0.1", 0, server_host_keys=[sshkey], process_factory=process
    )
    try:
        settings = {
            "host": "127.0.0.1",
            "ssh_port": listener.get_port(),
            "api_port": server.port,
            "username": "novice",
            "password": "temporary-password",
            "enable_https": True,
        }
        discovered = await discover_server(settings["host"], settings["ssh_port"])
        enrolled, _ = await enroll_ssh(settings, discovered, cert, key)
        assert enrolled == pem
        assert any(c.startswith("incus --force-local config set core.https_address ") for c in commands)
        assert any(c.startswith("incus --force-local config trust add ha-scottibyte-") for c in commands)
    finally:
        listener.close()
        await listener.wait_closed()
