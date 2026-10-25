"""UI setup, with a separate SSH identity confirmation before credential use."""

from pathlib import Path
from uuid import uuid4

try:
    import probatio as vol
except ImportError:  # Home Assistant versions before the schema migration
    import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .api import certificate_fingerprint
from .bootstrap import (
    EnrollmentError,
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

    async def async_step_user(self, user_input=None):
        return self.async_show_menu(step_id="user", menu_options=["ssh", "token"])

    async def async_step_ssh(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                user_input["host"] = validate_host(user_input["host"])
                parse_projects(user_input["projects"])
                user_input["_known_fingerprints"] = self._known_fingerprints()
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
                    vol.Optional("name", default=""): str,
                    vol.Required("host"): str,
                    vol.Required("ssh_port", default=22): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
                    vol.Required("api_port", default=8443): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
                    vol.Required("username"): str,
                    vol.Optional("password"): text(secret=True),
                    vol.Optional("sudo_password"): text(secret=True),
                    vol.Optional("ssh_key"): text(secret=True, multiline=True),
                    vol.Optional("key_passphrase"): text(secret=True),
                    vol.Required("projects", default="*"): str,
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
                parse_projects(user_input["projects"])
                cert, key = await self.hass.async_add_executor_job(generate_certificate)
                pem, info = await enroll_token(
                    user_input["host"],
                    user_input["api_port"],
                    user_input["token"],
                    cert,
                    key,
                    self._known_fingerprints(),
                )
                return await self._finish(user_input, pem, info, cert, key)
            except Exception:
                errors["base"] = "token_failed"
        return self.async_show_form(
            step_id="token",
            data_schema=vol.Schema(
                {
                    vol.Optional("name", default=""): str,
                    vol.Required("host"): str,
                    vol.Required("api_port", default=8443): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
                    vol.Required("token"): text(secret=True),
                    vol.Required("projects", default="*"): str,
                }
            ),
            errors=errors,
        )

    def _known_fingerprints(self):
        return {e.data.get("fingerprint") for e in self._async_current_entries()}

    async def _finish(self, settings, pem, info, cert, key):
        # Cluster members share a certificate: adding the same cluster twice is rejected.
        unique_id = certificate_fingerprint(pem)
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()
        projects = parse_projects(settings["projects"])
        detected_name = str(info.get("environment", {}).get("server_name") or "").strip()
        requested_name = str(settings.get("name") or "").strip()
        display_name = requested_name if requested_name and requested_name.casefold() != "incus" else detected_name or settings["host"]
        ident = uuid4().hex
        directory = Path(self.hass.config.path(".storage", DOMAIN, ident))

        def save():
            directory.mkdir(parents=True, mode=0o700)
            write_credentials(directory / "client.crt", directory / "client.key", cert, key)
            (directory / "server.crt").write_text(pem)

        await self.hass.async_add_executor_job(save)
        return self.async_create_entry(
            title=display_name,
            data={
                "host": settings["host"],
                "api_port": settings["api_port"],
                "projects": projects,
                "credential_id": ident,
                "server_name": detected_name or settings["host"],
                "fingerprint": unique_id,
            },
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return IncusOptionsFlow()


class IncusOptionsFlow(config_entries.OptionsFlow):
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
