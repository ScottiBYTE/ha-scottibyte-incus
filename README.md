# ScottiBYTE Incus for Home Assistant

A HACS-installable custom integration that brings multiple Incus servers into one Home Assistant sidebar dashboard.

**Version 0.1.0 — initial testing build.** Tested locally with Home Assistant 2026.10.4 and simulated Incus HTTPS/SSH endpoints. Live Incus-host validation is required before publishing a stable release. This repository is not yet in HACS's default catalog.

## Features

- Add one server at a time through **Settings → Devices & services → Add integration → ScottiBYTE Incus**.
- Automatic certificate enrollment using SSH credentials supplied during setup. No manual trust-token copying is required.
- Combined totals for instances, running/stopped instances, containers, VMs, and reachable servers.
- Server cards, per-server sortable instance tables, and global search by instance, server, project, status, IP, DNS label, or MAC.
- Start containers and VMs; request orderly shutdown with a confirmation that identifies the instance.
- Embedded root terminals for running Linux system containers, using Incus interactive execution. No SSH server is needed inside containers.
- Administrator-only panel and backend management/terminal API.
- Native Home Assistant devices and entities for automation and history.
- Last-known inventory retained and clearly marked stale when a server is unreachable.
- Projects and clusters supported. Enroll a cluster only once; each instance's cluster location appears in the table.
- Bundled terminal assets: no CDN connection is needed at runtime.

## Requirements

- Home Assistant **2026.10 or newer**. The tested runtime is 2026.10.4.
- An initialized Incus server. Version 7.5.1 is the initial live-test target; protocol compatibility with other versions is not yet certified.
- Home Assistant must reach the server over SSH during automatic setup and over HTTPS for normal use (default ports 22 and 8443).
- An SSH account with Incus administrative access, either directly or through sudo. Password or a pasted private key is supported. SSH setups requiring interactive MFA are not supported by this initial build.
- A Linux system container with `/bin/sh` for terminal access. Bash is used when present.

This is an integration, not a Home Assistant app/add-on or a separate web service. It works through the HA backend and needs no Docker sidecar.

## Install through HACS

The intended repository URL is `https://github.com/ScottiBYTE/ha-scottibyte-incus`. The source package does not create or publish that repository automatically. If you choose a different repository name, update the documentation and issue-tracker URLs in `manifest.json` before publishing.

1. Publish this repository to GitHub.
2. In HACS, open **Custom repositories**, add your repository URL, and select **Integration**.
3. Find **ScottiBYTE Incus**, download it, then restart Home Assistant.
4. Open **Settings → Devices & services → Add integration → ScottiBYTE Incus**.
5. Choose **Automatic setup using SSH**.
6. Enter the server address, display name, SSH credentials, and API port.
7. Verify the displayed SSH host-key fingerprint, then continue. On the server, an administrator can compare it with `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` when that is the key offered by SSH.
8. Open **Incus** in the HA sidebar.
9. Use **Add integration** again to enroll another independent server.

Default-catalog inclusion requires a separate HACS submission after the repository and integration meet its requirements. Installation as a custom repository does not imply default-catalog acceptance.

### Manual installation for initial testing

Copy **only** `custom_components/scottibyte_incus` to your Home Assistant configuration directory:

```text
/config/custom_components/scottibyte_incus/
```

The resulting folder must contain `manifest.json`, `__init__.py`, `config_flow.py`, and `frontend/` directly. Restart HA and add the integration through Devices & services. No dashboard YAML or resource registration is required.

## What automatic setup changes

1. Retrieves the SSH host key for confirmation before sending the supplied password.
2. Authenticates over SSH with that exact key pinned.
3. Checks access to the server's local Incus API; uses sudo if direct access fails.
4. If `core.https_address` is unset and automatic HTTPS setup is selected, sets it to `:<selected port>`, which listens on the server's interfaces. Existing listeners are preserved. The integration does not change firewall rules, router forwarding, or public DNS.
5. Creates a one-time Incus trust token on the host.
6. Checks the HTTPS server certificate against the fingerprint in that token.
7. Registers a newly generated HA client certificate using the token.
8. Stores the client certificate/private key and pinned server certificate in HA's `.storage/scottibyte_incus/` directory. The private key has mode `0600`.
9. Discards the SSH password, sudo password, pasted SSH key, and token. Ongoing requests use certificate authentication only.

If enrollment fails after this attempt enabled the HTTPS listener, the integration attempts to revert that newly enabled listener. A firewall or unreachable address can still require an administrator's intervention. An unused token may remain until its Incus expiry. If you abandon setup after successful enrollment but before HA saves the entry, a certificate can remain in the server trust list and can be removed by an administrator.

**The enrolled client is an Incus management identity.** Hiding controls in the UI does not make its server-side credentials read-only. Host access, container lifecycle operations, and root execution are privileged capabilities; protect your HA administrator accounts and backups accordingly.

### Advanced token setup

For installations where SSH is unavailable, create a one-time token using Incus and select **Advanced: existing trust token**. The integration verifies the token's server fingerprint and enrolls its own client certificate. A used or expired token must be replaced.

## Dashboard behavior

The top row shows combined inventory totals; server cards sit below it. Click a card to open that server's instance table. Search always spans all configured servers, including while viewing one server. Click a server name in a search result to open its inventory.

- **Start** is available for stopped instances.
- **Stop** requests graceful shutdown with a 60-second guest timeout. There is no forced-stop button in version one.
- **Terminal** is available only for running system containers. It opens a root shell, closes on disconnect/unsubscribe, and sends SIGHUP to the shell on cleanup. Sessions close after 15 minutes without keyboard input or four hours total. There is a limit of two terminals per HA user and ten overall.
- Action requests recheck live instance state and serialize operations per instance. Success is displayed only after Incus reports the operation completed.
- A browser disconnection does not cancel an already requested start/stop operation. Refresh to see the resulting state.
- Server inventory polls every 30 seconds by default. Change it under the integration's options (10–300 seconds). The panel rereads HA's cached inventory every five seconds; it does not poll Incus every five seconds.
- A server failure preserves the previous instance states and displays **Offline · stale**. Summary totals explicitly note when they include stale data. The successful update time is shown in the server view. It is not equivalent to the panel's latest view-refresh time.

## Entities

Each server has a connectivity binary sensor and total/running/stopped/container/VM count sensors. Each discovered instance gets a child device with a status sensor. CPU, memory, and disk sensors are registered but disabled by default to avoid a large recorder history; enable the ones you want in HA. The panel shows reported metrics regardless of those entity settings.

Status values include `Running`, `Stopped`, transitional states, and `unavailable` when its server cannot be reached. You can use those entities in ordinary HA automations. Management actions in this initial build are panel-only; lifecycle services and button entities are not yet exposed for automations.

## Metric details and limitations

- CPU is calculated from successive cumulative CPU samples: **100% equals one CPU core**, so multi-core workloads can exceed 100%. It needs two successful samples and resets after reconnection or a counter reset.
- Memory is used bytes plus a configured absolute memory limit, when available. A percentage limit is not converted to a guessed capacity.
- Disk is root-disk usage plus the configured root-disk size limit when reported. A missing configured limit is not the storage pool's total free space.
- IP/MAC information comes from Incus instance state. A VM without a functioning Incus agent may have no guest IP or usage information.
- DNS labels come from optional instance configuration `user.dns_name`. The integration does not assume the instance name is a real DNS record and does not perform reverse lookups.
- VM start/stop is included. VM shells, serial consoles, and graphical consoles are not included in version one.
- Cluster inventory is grouped under one configured entry; instance location is displayed under its server label. Shared server-certificate fingerprints prevent enrolling the same cluster more than once. Servers deliberately reusing identical certificates will also be treated as duplicates.
- Snapshot checkpoints are saved approximately every two minutes. A crash can lose recent inventory changes.
- Removed instances leave their registered HA entities unavailable; automatic registry cleanup is deferred.
- Readdressing a server, changing selected projects, or rotating its certificate currently requires removing and enrolling the entry again. Reconfiguration/reauthentication flows are future work. Removing an entry resets its entity identities on re-addition.

## Removal and trust revocation

Removing the integration entry deletes its local credential directory and saved inventory. It does **not** automatically revoke the remote certificate. Before removing an entry, record its client-certificate fingerprint if you want to revoke its server trust. An Incus administrator can inspect `incus config trust list` and remove the matching HA identity with `incus config trust remove <fingerprint>`. Do not remove a different HA installation's certificate by name alone.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Cannot obtain SSH host key | Address, SSH port, HA-to-server routing, and SSH service |
| SSH succeeds but enrollment fails | Incus permissions, sudo password, selected HTTPS port, existing listener binding, firewall |
| Server becomes unavailable after certificate changes | Re-enroll with the new server certificate; trust is pinned deliberately |
| Missing VM IP or metrics | Incus agent inside that VM |
| No terminal button | A running Linux system container is required |
| Blank/missing panel after an update | Reload the HA browser/app frontend; confirm the bundled frontend directory was installed |
| Shutdown times out | Resolve guest shutdown problems; version one does not force-kill instances |

## Development and release

See [DEVELOPMENT.md](DEVELOPMENT.md) for staging in an Incus container, running checks, and pushing to GitHub. See [VALIDATION.md](VALIDATION.md) for the test scope and live acceptance checklist.

Project code is MIT licensed. Bundled xterm.js and its fit addon retain their upstream MIT license files in `frontend/vendor/`.
