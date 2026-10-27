# ScottiBYTE Incus for Home Assistant

![ScottiBYTE Incus](custom_components/scottibyte_incus/brand/icon.png)


A HACS-installable custom integration that brings multiple Incus servers into one Home Assistant sidebar dashboard.

**Version 1.1.2 — cleaner cluster cards.** Scott has confirmed cluster member support in his live deployment. VM guest terminals pass automated tests and await live acceptance. Install the numbered release through HACS as a custom repository. Default HACS catalog listing is a separate submission.

## Features

- Add one server at a time through **Settings → Devices & services → Add integration → ScottiBYTE Incus**.
- Automatic certificate enrollment using SSH credentials supplied during setup. No manual trust-token copying is required.
- Combined totals for instances, running/stopped instances, containers, VMs, and reachable servers.
- Server cards, per-server sortable instance tables, and global search by instance, server, project, status, IP, DNS label, or MAC.
- Start containers and VMs; request orderly shutdown with a confirmation that identifies the instance.
- Create named or automatically named snapshots for containers and VMs; list creation/expiry times, rename, delete, and restore snapshots through the snapshot manager.
- Embedded root terminals for running Linux system containers and Linux VMs, using Incus interactive execution. VMs require a working Incus agent. No guest SSH server is needed.
- Administrator-only panel and backend management/terminal API.
- Native Home Assistant devices and entities for automation and history.
- Offline server cards show the configured address and last-known counts; instance listings are unavailable until the server reconnects.
- Projects and clusters supported. Enroll a cluster only once; each instance's cluster location appears in the table.
- Bundled terminal assets: no CDN connection is needed at runtime.

## Requirements

- Home Assistant **2026.10 or newer**. The tested runtime is 2026.10.4.
- An initialized Incus server. Live testing used Incus 7.5.1; compatibility with other Incus versions has not been separately certified.
- Home Assistant must reach the server over SSH during automatic setup and over HTTPS for normal use (default ports 22 and 8443).
- An SSH account with Incus administrative access, either directly or through sudo. Password or a pasted private key is supported. SSH setups requiring interactive MFA are not supported by this initial build.
- A Linux container or Linux VM with `/bin/sh` for terminal access. Bash is used when present. VMs need a working Incus agent.

This is an integration, not a Home Assistant app/add-on or a separate web service. It works through the HA backend and needs no Docker sidecar.

## Install through HACS

1. In HACS, open **Custom repositories**, add `https://github.com/ScottiBYTE/ha-scottibyte-incus`, and select **Integration**.
2. Find **ScottiBYTE Incus**, download it, then restart Home Assistant.
3. Open **Settings → Devices & services → Add integration → ScottiBYTE Incus**.
4. Choose **Automatic setup using SSH**.
5. Enter the server address, SSH credentials, and API port. Leave the optional display name blank to use the detected hostname.
6. Verify the displayed SSH host-key fingerprint, then continue. On the server, compare with `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` when that is the offered key.
7. Open **Incus** in the HA sidebar.
8. Use the dashboard's **Add server** shortcut for another independent server. Home Assistant's native integration page may call this **Add hub**.

After an update, restart Home Assistant and hard-refresh the browser (**Ctrl+Shift+R**). Select the numbered **v1.1.2** release in HACS. A hexadecimal commit identifier means the development branch is selected. Restart HA after installation; refresh the browser or reset the Companion frontend cache if an older interface remains visible. Tracking `main` is reserved for development testing.

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

- **Reorder servers** enables drag handles and arrow controls. Drag a handle onto another card, then **Save order**; **Cancel** discards edits. The order is shared across users and devices and stored in HA. Newly enrolled servers appear at the end.
- **Manage servers** opens the native integration page, where server entries can be renamed or deleted.
- **Start** is available for stopped instances.
- **Stop** requests graceful shutdown with a 60-second guest timeout. There is no forced-stop button in version one.
- **Snapshot** opens a named-snapshot form; leave the name blank for an automatic name. **Manage snapshots** (the compact **Manage** button beside Snapshot) lists existing snapshots, creation/expiry dates, and whether saved memory is present. New snapshots omit running memory and inherit the server's snapshot-expiry policy.
- Snapshot rename, delete, and restore are available in the manager. Delete and restore require confirmation. Restore accepts running or stopped instances and restores disk/configuration without saved running memory. Incus handles stopping and restarting an instance that is running; a stopped instance remains stopped. The integration does not issue a separate stop/start sequence. Mutations share the instance's lifecycle-operation lock and wait for Incus completion. An operation can continue if the browser disconnects; refresh before retrying after a timeout.
- Snapshots reside with the instance and do not replace external backups. Attached custom storage volumes are excluded. Applications may require their own quiescing or backup procedures for consistency.
- **Terminal** is available for running Linux system containers and Linux VMs. VM shells connect through the Incus agent. It opens a root shell, closes on disconnect/unsubscribe, and sends SIGHUP to the shell on cleanup. Sessions close after 15 minutes without keyboard input or four hours total. There is a limit of two terminals per HA user and ten overall.
- Action requests recheck live instance state and serialize operations per instance. Success is displayed only after Incus reports the operation completed.
- A browser disconnection does not cancel an already requested start/stop operation. Refresh to see the resulting state.
- Server inventory polls every 30 seconds by default. Change it under the integration's options (10–300 seconds). The panel rereads HA's cached inventory every five seconds; it does not poll Incus every five seconds.
- An unreachable server shows an offline, non-clickable card with its configured IP address or hostname. Cached instances are excluded from server drill-down and global search; a server that goes offline while open returns the view to the cards. HA retains its internal checkpoint for recovery and marks summary totals that include last-known counts. Offline does not distinguish a powered-off host from network/API failures.

## Entities

Each server has a connectivity binary sensor and total/running/stopped/container/VM count sensors. Each discovered instance gets a child device with a status sensor. CPU, memory, and disk sensors are registered but disabled by default to avoid a large recorder history; enable the ones you want in HA. The panel shows reported metrics regardless of those entity settings.

Status values include `Running`, `Stopped`, transitional states, and `unavailable` when its server cannot be reached. You can use those entities in ordinary HA automations. Management actions in this initial build are panel-only; lifecycle services and button entities are not yet exposed for automations.

## Metric details and limitations

- The table's **CPU % of host** is an instance's share of its host's logical CPU capacity, averaged over the polling interval. For example, 7.62 busy logical CPUs on a 32-thread host is 23.8%. This is not usage relative to the instance's CPU limit and is not the host's total system load. Details show cores used and the host CPU count.
- Capacity is read from the Incus resources API, separately for each cluster member, and cached for five minutes. Missing capacity produces an unknown percentage. CPU usage requires two successful samples and resets after reconnection, a counter reset, or a detected cluster-member move.
- The existing CPU entity retains the per-core percentage for automation compatibility (100% = one logical CPU). A separate disabled-by-default **CPU host share** entity exposes the normalized percentage.
- Memory is used bytes plus a configured absolute memory limit, when available. A percentage limit is not converted to a guessed capacity.
- Disk is root-disk usage plus the configured root-disk size limit when reported. A missing configured limit is not the storage pool's total free space.
- IP/MAC information comes from Incus instance state. A VM without a functioning Incus agent may have no guest IP or usage information.
- Primary IP selection prefers an explicitly named Incus NIC, then ordinary guest interfaces, ahead of recognizable nested Docker/bridge interfaces. IPv4 is preferred within the same interface tier. All reported addresses remain in Details. This is a heuristic, not route discovery; unusual multi-NIC configurations need validation.
- DNS labels prefer explicit `user.dns_name`, otherwise cached reverse lookups through HA's system resolver. Successful results are cached for ten minutes, missing records for one minute. Queries run in the background and names appear on a subsequent inventory poll. No Pi-hole credentials are needed. DHCP must configure a resolver that can answer local PTR queries. A forward DNS record alone does not guarantee a PTR record.
- VM start/stop and Linux VM agent-based shells are included. Windows shells, serial consoles, and graphical consoles are not included.
- Cluster inventory is grouped under one configured entry; instance location is displayed under its server label. Shared server-certificate fingerprints prevent enrolling the same cluster more than once. Servers deliberately reusing identical certificates will also be treated as duplicates.
- Snapshot checkpoints are saved approximately every two minutes. A crash can lose recent inventory changes.
- Removed instances leave their registered HA entities unavailable; automatic registry cleanup is deferred.
- Use the server entry’s **Reconfigure** action to change its address, API port, or projects after testing the connection with existing pinned trust. Choose **Renew certificate trust** for SSH/token enrollment after certificate changes. Both preserve the config-entry ID, entity IDs, and server order. Renewal retires the previous client identity when it can; a notification identifies any manual cleanup needed.

## Removal and trust revocation

Deleting a server entry first attempts to revoke **only that entry's client-certificate fingerprint** from the Incus trust store, then deletes its local credential directory and saved inventory. Containers and VMs keep running. No guest is deleted or stopped.

If the server is unavailable or rejects revocation, local removal still succeeds. A persistent HA notification provides the fingerprint and manual cleanup command. On that server, inspect `incus config trust list` and remove the matching certificate using `incus config trust remove <fingerprint>`. Do not identify a certificate by name alone.

Renaming an entry is supported through HA’s native integration page. Use **Reconfigure** on that entry for connection changes or trust renewal. Changes are validated before saving; failed connection tests preserve the existing configuration.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Cannot obtain SSH host key | Address, SSH port, HA-to-server routing, and SSH service |
| SSH succeeds but enrollment fails | Incus permissions, sudo password, selected HTTPS port, existing listener binding, firewall |
| Server becomes unavailable after certificate changes | Use Reconfigure → Renew certificate trust; verify the server identity again |
| Missing VM IP or metrics | Incus agent inside that VM |
| No terminal button | A running Linux container or VM is required; refresh inventory after updating |
| Blank/missing panel after an update | Reload the HA browser/app frontend; confirm the bundled frontend directory was installed |
| Shutdown times out | Resolve guest shutdown problems; version one does not force-kill instances |

## Development and release

See [DEVELOPMENT.md](DEVELOPMENT.md) for staging in an Incus container, running checks, and pushing to GitHub. See [VALIDATION.md](VALIDATION.md) for the test scope and live acceptance checklist.

Project code is MIT licensed. Bundled xterm.js and its fit addon retain their upstream MIT license files in `frontend/vendor/`.

## VM terminal requirements

VM guest terminals require a working Incus agent and `/bin/sh`. Known Windows and BSD/macOS guests are excluded from the Linux shell action. When guest OS metadata is absent, a shell attempt is allowed for custom Linux images; this does not guarantee a Linux guest or working agent. Agent or shell failures are reported in the terminal dialog. No SSH setup is required inside the guest.

## Support ScottiBYTE

If you find this integration useful, you can [donate through PayPal](https://www.paypal.com/paypalme/ScottiBYTE). The dashboard header also includes a Donate button. Its visible version comes from the installed integration manifest and identifies the frontend loaded in your browser or Companion app.

## Cluster member cards (v1.1.0)

Add each cluster member through Add server. Members share a pinned server certificate, but each configured member gets its own client certificate, entry and card. Existing entries remain in place. Cluster cards show the server IP, member name and cluster size. The redundant API address line is omitted. Card inventory and counts cover only that member; add all members for a complete cluster summary. Standalone server behavior is unchanged.

Endpoints are discovered through the authenticated cluster membership API and checkpointed with inventory. On a later refresh, an unreachable API endpoint can be replaced by another discovered member using the same pinned TLS context. Discovery addresses must resolve and be reachable from HA. No failover is possible before the first successful discovery. An actually offline member remains unavailable; other online member cards remain usable. Cluster quorum and Incus availability are still required. Existing terminals are not resumed after a connection failure, and action submissions are never automatically replayed.

Member card ordering and HA entry IDs survive this update. Instances migrated between members may leave old HA registry entities that require manual cleanup. Removing a member entry revokes only its own client identity. A failed remote revocation still requires the manual cleanup described by the integration notification.
