# ScottiBYTE Incus v1.2.0-beta.1

Testing release: whole-server OS utilization and saved global polling interval. v1.1.3 remains the stable release.

- Server cards show total OS CPU busy percentage across all logical CPUs, RAM utilization based on MemAvailable, and used/total per local persistent filesystem. These measurements include all server applications and do not derive from Incus instances or pools.
- Collect through an SSH key restricted to a fixed Python collector and removal of that key. No daemon, sudo polling, third-party host package, or extra listener. SSH host identity remains pinned. The user's setup password/private key is not saved; only a new dedicated private key is stored in Home Assistant.
- Automatic SSH enrollment offers host monitoring. Existing and token-enrolled entries can configure it through Reconfigure → Set up or disable whole-server metrics.
- Collect each cluster member directly over its own SSH connection. Host monitoring can remain available if Incus is down. Failures retain last-known values with an unavailable label; CPU requires two samples and resets after a failure or reboot.
- Dashboard Refresh every selector saves 10, 30, 60 or 300 seconds globally and updates coordinator polling. The browser continues reading HA's cache every five seconds. Server order and refresh preferences preserve each other.
- Disabling host monitoring or removing an entry attempts to remove only its authorized_keys line and removes its local key files. A notification identifies manual cleanup if remote removal fails.

## Validation

68 automated Python tests pass locally, including SSH enrollment/poll/removal with an isolated AsyncSSH test server, rollback of rejected keys, host-key pin rejection, preservation of unrelated keys, OS counter calculations, independent availability, setup/disable flows, secret handling, refresh persistence and existing regressions. Browser checks pass at 360, 390, 480 and desktop widths. Ruff and JavaScript syntax checks pass. An isolated real OpenSSH daemon could not run in this execution environment because its privilege-separation chroot is blocked; live OpenSSH acceptance remains required. GitHub HACS validation, hassfest and tests must pass for the release commit before publication.

## Live acceptance required

Install the beta explicitly in HACS, restart HA, and configure host metrics on one server through Reconfigure. Check CPU after two refresh cycles, memory against total minus available RAM, and filesystem used/total against df. Test a cluster member, an unreachable SSH endpoint, refresh persistence, and key removal. Do not describe this beta as fully live-tested.

## Scope

Linux hosts with OpenSSH, Python 3, readable /proc and writable ~/.ssh/authorized_keys. Custom AuthorizedKeysFile or forced-command policies may prevent enrollment; setup verifies key authentication and attempts rollback. No interactive SSH MFA support. Local persistent filesystem types are selected; pseudo, network, overlay and Incus guest mounts are excluded. Filesystems sharing capacity are not summed. Credentials are per member, and Incus endpoint failover never substitutes another member's host metrics.
