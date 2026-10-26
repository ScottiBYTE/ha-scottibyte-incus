# ScottiBYTE Incus v1.0.0

First stable release of the HACS-installable Incus integration for Home Assistant.

## Features

- Visible dashboard version and a Donate button linking to ScottiBYTE's PayPal page.

- Add independent servers through Devices & services, with automatic SSH-based certificate enrollment and a token enrollment alternative.
- Combined summary, server addresses/status, persistent drag-and-drop card ordering, and global instance search.
- Per-server sortable instance tables, sticky headers/actions, expandable network details, and a mobile layout tested in the Pixel 7 Companion app.
- CPU usage normalized to host logical CPU capacity, memory/disk metrics, preferred guest IP selection, and cached local reverse DNS.
- Start and gracefully stop containers/VMs; embedded root terminals for running Linux system containers.
- Create, list, rename, delete, and restore instance snapshots. Incus restarts an instance that was running before restore.
- Offline server cards cannot open cached instance lists; their instances are excluded from search.
- Server connection reconfiguration and trust renewal preserve HA entry/entity identities and saved card order.
- Server removal attempts to revoke its own certificate; failed cleanup generates a notification with manual instructions.
- Administrator-only management endpoints and native HA devices/entities.

## Validation and installation

Scott reports all current features tested in the live deployment. Automated Python tests, lint, JavaScript syntax, and hassfest must pass on this exact release commit before publication.

In HACS, add https://github.com/ScottiBYTE/ha-scottibyte-incus as a custom repository of type Integration and select v1.0.0. Restart HA and refresh the frontend after updating. This is a regular release, not a prerelease.

## Documented limitations

- Removed-instance HA registry entries are retained and may require manual cleanup.
- No VM console, forced-stop action, stateful-memory snapshot management, snapshot export/scheduling/expiry editing, or lifecycle services for automations.
- Snapshots do not include attached custom storage volumes and are not external backups.
- A VM needs a functioning Incus agent for guest IPs and metrics. Missing metrics remain unknown.
- Default HACS catalog inclusion is a separate submission.
