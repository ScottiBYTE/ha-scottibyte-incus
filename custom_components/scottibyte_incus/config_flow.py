"""UI setup, with a separate SSH identity confirmation before credential use."""

import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

try:
    import probatio as vol
except ImportError:  # Home Assistant versions before the schema migration
    import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import persistent_notification
from homeassistant.helpers import selector

from .api import IncusClient, certificate_fingerprint, make_ssl_context
from .bootstrap import (
    EnrollmentError,
    api_url,
    discover_server,
    enroll_ssh,
    enroll_token,
    generate_certificate,
    validate_host,
    write_credentials,
)
from .const import DOMAIN


def text(secret=False, multiline=False):
    return selector.TextSelector(
        selector.TextSelectorConfig(
            type=selector.TextSelectorType.PASSWORD if secret else selector.TextSelectorType.TEXT, multiline=multiline
        )
    )


class IncusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_reconfigure(self, user_input=None):
        self._editing_entry = self._get_reconfigure_entry()
        return self.async_show_menu(step_id="reconfigure", menu_options=["connection", "renew_trust"])

    async def async_step_reauth(self, entry_data):
        self._editing_entry = self._get_reauth_entry()
        return await self.async_step_renew_trust()

    async def async_step_renew_trust(self, user_input=None):
        return await self.async_step_user()

    def _default(self, key, fallback=""):
        entry = getattr(self, "_editing_entry", None)
        if entry:
            if key == "name":
                return entry.title
            if key == "projects":
                return ",".join(entry.data["projects"])
            return entry.data.get(key, fallback)
        return fallback

    async def async_step_connection(self, user_input=None):
        entry = self._editing_entry
        errors = {}
        if user_input is not None:
            client = None
            try:
                host = validate_host(user_input["host"])
                projects = parse_projects(user_input["projects"])
                directory = Path(self.hass.config.path(".storage", DOMAIN, entry.data["credential_id"]))

                def context():
                    return make_ssl_context((directory / "server.crt").read_text(), directory / "client.crt", directory / "client.key")

                client = IncusClient(api_url(host, user_input["api_port"]), await self.hass.async_add_executor_job(context))
                info, _ = await client.inventory(projects)
                expected_member = entry.data.get("cluster_member")
                if expected_member and info.get("environment", {}).get("server_name") != expected_member:
                    raise ValueError("Use trust renewal to select a different member")
                return self.async_update_reload_and_abort(entry, data_updates={
                    "host": host, "api_port": user_input["api_port"], "projects": projects})
            except Exception:
                errors["base"] = "connection_failed"
            finally:
                if client:
                    await client.close()
        return self.async_show_form(step_id="connection", data_schema=vol.Schema({
            vol.Required("host", default=entry.data["host"]): str,
            vol.Required("api_port", default=entry.data["api_port"]): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
            vol.Required("projects", default=",".join(entry.data["projects"])): str,
        }), errors=errors)

    def _check_endpoint(self, host, port):
        for entry in self._async_current_entries():
            if entry is not getattr(self, "_editing_entry", None) and entry.data["host"].casefold() == host.casefold() and entry.data["api_port"] == port:
                raise ValueError("This endpoint is already configured")

    async def async_step_user(self, user_input=None):
        return self.async_show_menu(step_id="user", menu_options=["ssh", "token"])

    async def async_step_ssh(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                user_input["host"] = validate_host(user_input["host"])
                self._check_endpoint(user_input["host"], user_input["api_port"])
                parse_projects(user_input["projects"])
                user_input["_known_fingerprints"] = set()
                self._settings = user_input
                self._host_key = await discover_server(user_input["host"], user_input["ssh_port"])
                return await self.async_step_confirm_host()
            except ValueError:
                errors["base"] = "invalid_host"
            except Exception:
                errors["base"] = "ssh_unreachable"
        return self.async_show_form(
            step_id="ssh",
            data_schema=vol.Schema(
                {
                    vol.Optional("name", default=self._default("name")): str,
                    vol.Required("host", default=self._default("host")): str,
                    vol.Required("ssh_port", default=22): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
                    vol.Required("api_port", default=self._default("api_port", 8443)): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
                    vol.Required("username"): str,
                    vol.Optional("password"): text(secret=True),
                    vol.Optional("sudo_password"): text(secret=True),
                    vol.Optional("ssh_key"): text(secret=True, multiline=True),
                    vol.Optional("key_passphrase"): text(secret=True),
                    vol.Required("projects", default=self._default("projects", "*")): str,
                    vol.Required("enable_https", default=True): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_confirm_host(self, user_input=None):
        if user_input is not None:
            cert, key = await self.hass.async_add_executor_job(generate_certificate)
            try:
                pem, info = await enroll_ssh(self._settings, self._host_key, cert, key)
                return await self._finish(self._settings, pem, info, cert, key)
            except EnrollmentError as err:
                message = str(err)
            except Exception:
                message = "Could not enroll. Check SSH authentication, Incus permissions, API address/port, and network reachability."
            finally:
                # Passwords/private SSH keys never survive the enrollment attempt.
                self._settings = {
                    k: v
                    for k, v in self._settings.items()
                    if k not in ("password", "sudo_password", "ssh_key", "key_passphrase")
                }
            return self.async_show_form(
                step_id="failed", data_schema=vol.Schema({}), description_placeholders={"reason": message}
            )
        return self.async_show_form(
            step_id="confirm_host",
            data_schema=vol.Schema({}),
            description_placeholders={"host": self._settings["host"], "fingerprint": self._host_key.get_fingerprint()},
        )

    async def async_step_failed(self, user_input=None):
        return await self.async_step_user()

    async def async_step_token(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                user_input["host"] = validate_host(user_input["host"])
                self._check_endpoint(user_input["host"], user_input["api_port"])
                parse_projects(user_input["projects"])
                cert, key = await self.hass.async_add_executor_job(generate_certificate)
                pem, info = await enroll_token(
                    user_input["host"],
                    user_input["api_port"],
                    user_input["token"],
                    cert,
                    key,
                    (),
                )
                return await self._finish(user_input, pem, info, cert, key)
            except Exception:
                errors["base"] = "token_failed"
        return self.async_show_form(
            step_id="token",
            data_schema=vol.Schema(
                {
                    vol.Optional("name", default=self._default("name")): str,
                    vol.Required("host", default=self._default("host")): str,
                    vol.Required("api_port", default=self._default("api_port", 8443)): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
                    vol.Required("token"): text(secret=True),
                    vol.Required("projects", default=self._default("projects", "*")): str,
                }
            ),
            errors=errors,
        )

    async def _discard_enrollment(self, settings, pem, cert, key):
        # A duplicate reached through a DNS alias may already have enrolled.
        # Retire only the newly generated identity, never another entry's trust.
        with tempfile.TemporaryDirectory(prefix="ha-incus-duplicate-") as tmp:
            directory = Path(tmp)
            await self.hass.async_add_executor_job(write_credentials, directory / "client.crt", directory / "client.key", cert, key)
            context = await self.hass.async_add_executor_job(make_ssl_context, pem, directory / "client.crt", directory / "client.key")
            client = IncusClient(api_url(settings["host"], settings["api_port"]), context)
            fingerprint = certificate_fingerprint(cert)
            try:
                await client.request("DELETE", f"/1.0/certificates/{fingerprint}", timeout=10)
            except Exception:
                persistent_notification.async_create(self.hass,
                    f"Duplicate setup was rejected, but the new trust identity may remain. Remove only certificate {fingerprint} on {settings['host']}.",
                    title="Incus duplicate trust cleanup")
            finally:
                await client.close()

    def _known_fingerprints(self):
        return {e.data.get("fingerprint") for e in self._async_current_entries() if e is not getattr(self, "_editing_entry", None)}

    async def _finish(self, settings, pem, info, cert, key):
        fingerprint = certificate_fingerprint(pem)
        env = info.get("environment", {})
        member = str(env.get("server_name") or "").strip() if env.get("server_clustered") else ""
        if env.get("server_clustered") and not member:
            raise ValueError("Cluster member identity was not reported")
        unique_id = f"{fingerprint}:{member}" if member else fingerprint
        entry = getattr(self, "_editing_entry", None)
        for other in self._async_current_entries():
            if other is entry or other.data.get("fingerprint") != fingerprint:
                continue
            # Also recognizes entries created before member-specific identities.
            if not member or other.data.get("cluster_member", other.data.get("server_name")) == member:
                await self._discard_enrollment(settings, pem, cert, key)
                return self.async_abort(reason="already_configured")
        await self.async_set_unique_id(unique_id)
        if entry is None:
            self._abort_if_unique_id_configured()
        projects = parse_projects(settings["projects"])
        detected_name = str(info.get("environment", {}).get("server_name") or "").strip()
        requested_name = str(settings.get("name") or "").strip()
        display_name = (
            requested_name
            if requested_name and requested_name.casefold() != "incus"
            else detected_name or settings["host"]
        )
        ident = uuid4().hex
        directory = Path(self.hass.config.path(".storage", DOMAIN, ident))

        def save():
            directory.mkdir(parents=True, mode=0o700)
            write_credentials(directory / "client.crt", directory / "client.key", cert, key)
            (directory / "server.crt").write_text(pem)

        await self.hass.async_add_executor_job(save)
        data = {
            "host": settings["host"], "api_port": settings["api_port"], "projects": projects,
            "credential_id": ident, "server_name": detected_name or settings["host"], "fingerprint": fingerprint, "cluster_member": member,
        }
        entry = getattr(self, "_editing_entry", None)
        if entry is None:
            return self.async_create_entry(title=display_name, data=data)
        old_directory = Path(self.hass.config.path(".storage", DOMAIN, entry.data["credential_id"]))
        old_fingerprint = None
        try:
            old_fingerprint = await self.hass.async_add_executor_job(
                lambda: certificate_fingerprint((old_directory / "client.crt").read_text()))
        except OSError:
            pass
        result = self.async_update_reload_and_abort(entry, unique_id=unique_id, title=display_name, data=data)
        if old_fingerprint:
            client = None
            try:
                context = await self.hass.async_add_executor_job(
                    lambda: make_ssl_context(pem, directory / "client.crt", directory / "client.key"))
                client = IncusClient(api_url(settings["host"], settings["api_port"]), context)
                # A missing identity needs no cleanup; avoid DELETE returning a noisy 404.
                identities = await client.metadata("/1.0/certificates", params={"recursion": 1})
                if any(item.get("fingerprint") == old_fingerprint for item in identities):
                    await client.request("DELETE", f"/1.0/certificates/{old_fingerprint}", timeout=10)
            except Exception:
                persistent_notification.async_create(self.hass,
                    f"Trust was renewed for {display_name}, but the previous client certificate may remain trusted. "
                    f"Inspect the previous server's trust list and remove only fingerprint {old_fingerprint} if present.",
                    title="Incus previous trust cleanup", notification_id=f"{DOMAIN}_renew_{entry.entry_id}")
            finally:
                if client:
                    await client.close()
        await self.hass.async_add_executor_job(shutil.rmtree, old_directory, True)
        return result

    @staticmethod
    def async_get_options_flow(config_entry):
        return IncusOptionsFlow()


class IncusOptionsFlow(config_entries.OptionsFlowWithReload):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required("poll_seconds", default=self.config_entry.options.get("poll_seconds", 30)): vol.All(
                        vol.Coerce(int), vol.Range(min=10, max=300)
                    ),
                }
            ),
        )


def parse_projects(value):
    projects = sorted({p.strip() for p in value.split(",") if p.strip()})
    if not projects or ("*" in projects and projects != ["*"]):
        raise ValueError("Projects must be * or a comma-separated list of project names")
    return projects
