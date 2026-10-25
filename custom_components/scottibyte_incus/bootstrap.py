"""One-time SSH enrollment. SSH credentials are never written to config entries."""

import asyncio
import base64
import ipaddress
import json
import re
import shlex
import ssl
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import asyncssh
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from .api import IncusClient, certificate_fingerprint, make_ssl_context


class EnrollmentError(Exception):
    """Safe enrollment error shown in the configuration flow."""


def validate_host(host):
    host = host.strip().strip("[]")
    if not host or any(c in host for c in "/\\@?# \t\r\n"):
        raise ValueError("Enter an IP address or hostname without a URL or port")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", host) or host.startswith("-"):
            raise ValueError("Invalid hostname") from None
    return host


def api_url(host, port):
    return f"https://{'[' + host + ']' if ':' in host else host}:{port}"


def generate_certificate():
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Home Assistant ScottiBYTE Incus")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    return (
        cert.public_bytes(serialization.Encoding.PEM).decode(),
        key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        ).decode(),
    )


async def discover_server(host, port):
    """Read the SSH key for explicit fingerprint confirmation before passwords are sent."""
    key = await asyncio.wait_for(asyncssh.get_server_host_key(host, port=port), 15)
    if key is None:
        raise EnrollmentError("SSH did not supply a host key")
    return key


async def fetch_server_certificate(host, port, expected_fingerprint):
    """Fetch and validate the Incus certificate against the authenticated token."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    _reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port, ssl=context), 15)
    try:
        der = writer.get_extra_info("ssl_object").getpeercert(binary_form=True)
        pem = ssl.DER_cert_to_PEM_cert(der)
        if certificate_fingerprint(pem) != expected_fingerprint.replace(":", "").lower():
            raise EnrollmentError("Incus certificate does not match the enrollment token")
        return pem
    finally:
        writer.close()
        await writer.wait_closed()


async def enroll_token(host, port, token, cert, key, known_fingerprints=()):
    """Consume a trust token without invoking an Incus CLI inside Home Assistant."""
    try:
        decoded = json.loads(base64.b64decode(token, validate=True))
        fingerprint = decoded["fingerprint"]
    except (ValueError, KeyError, TypeError) as err:
        raise EnrollmentError("Invalid Incus trust token") from err
    pem = await fetch_server_certificate(host, port, fingerprint)
    if certificate_fingerprint(pem) in known_fingerprints:
        raise EnrollmentError("This Incus server or cluster is already configured")
    with tempfile.TemporaryDirectory(prefix="ha-incus-") as directory:
        cert_path, key_path = Path(directory) / "client.crt", Path(directory) / "client.key"
        await asyncio.to_thread(write_credentials, cert_path, key_path, cert, key)
        context = await asyncio.to_thread(make_ssl_context, pem, cert_path, key_path)
        client = IncusClient(api_url(host, port), context)
        try:
            await client.request(
                "POST",
                "/1.0/certificates",
                payload={
                    "type": "client",
                    "name": "Home Assistant ScottiBYTE Incus",
                    "certificate": base64.b64encode(ssl.PEM_cert_to_DER_cert(cert)).decode(),
                    "trust_token": token,
                },
            )
            info = await client.metadata("/1.0")
            if info.get("auth") != "trusted":
                raise EnrollmentError("The server did not trust the enrolled certificate")
            return pem, info
        finally:
            await client.close()


def write_credentials(cert_path, key_path, cert, key):
    cert_path.write_text(cert)
    cert_path.chmod(0o600)
    key_path.write_text(key)
    key_path.chmod(0o600)


async def enroll_ssh(settings, host_key, cert, key):
    """Obtain token over authenticated SSH, then enroll over the Incus HTTPS API."""
    password = settings.get("password") or None
    kwargs = {
        "host": settings["host"],
        "port": settings["ssh_port"],
        "username": settings["username"],
        "password": password,
        "known_hosts": ([host_key], [], []),
        "agent_path": None,
        "client_keys": [],
        "connect_timeout": 15,
        "login_timeout": 20,
    }
    if settings.get("ssh_key"):
        kwargs["client_keys"] = [
            asyncssh.import_private_key(settings["ssh_key"], settings.get("key_passphrase") or None)
        ]
    async with asyncssh.connect(**kwargs) as conn:
        sudo = False
        result = await conn.run("incus --force-local query /1.0", check=False, timeout=15)
        if result.exit_status != 0:
            sudo = True

        async def run(command):
            if sudo:
                command = "sudo -S -p '' -- " + command
            result = await conn.run(
                command,
                input=(settings.get("sudo_password") or password or "") + "\n" if sudo else None,
                check=False,
                timeout=25,
            )
            if result.exit_status != 0:
                # Do not expose command output: it may contain tokens or credentials.
                raise EnrollmentError(
                    "SSH account cannot administer Incus. Check its Incus permissions or sudo password."
                )
            return result.stdout.strip()

        await run("incus --force-local query /1.0")
        listener = await run("incus --force-local config get core.https_address")
        enabled_listener = False
        if not listener:
            if not settings.get("enable_https"):
                raise EnrollmentError(
                    "Incus HTTPS is disabled. Enable automatic HTTPS setup or configure it on the server."
                )
            await run(
                "incus --force-local config set core.https_address " + shlex.quote(":" + str(settings["api_port"]))
            )
            enabled_listener = True
        try:
            token = await run(
                "incus --force-local config trust add "
                + shlex.quote("ha-scottibyte-" + certificate_fingerprint(cert)[:12])
                + " --quiet"
            )
            # --quiet returns a single base64 token; never log or persist it.
            return await enroll_token(
                settings["host"], settings["api_port"], token, cert, key, settings.get("_known_fingerprints", ())
            )
        except BaseException:
            if enabled_listener:
                # Revert only the listener created by this attempt.
                current = await run("incus --force-local config get core.https_address")
                if current == ":" + str(settings["api_port"]):
                    await run("incus --force-local config unset core.https_address")
            raise
