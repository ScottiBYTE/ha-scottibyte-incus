# ScottiBYTE Incus v0.1.5 — first tagged prerelease

This is a testing release on the path to v1.0, not a declaration of production stability.

## Included

- Multiple Incus servers, combined totals, searchable instance inventory, start/graceful stop, and container root terminals.
- Sticky table headers/actions, compact expandable network details, automatic hostname naming, and an Add server shortcut.
- Reverse DNS using Home Assistant's resolver and persistent drag-and-drop server ordering.
- CPU % of host with detected logical CPU capacity, including per-member capacity for cluster instances. Core usage remains available in Details; the existing per-core CPU entity retains its calculation.
- Primary IP selection favors configured guest NICs over recognizable nested Docker/bridge interfaces.
- Snapshot creation and management for containers and VMs: list, rename, delete, and stopped-instance restore. New snapshots omit running memory. Delete and restore require confirmation; operations share the instance lifecycle lock.
- In-place server address/project changes and trust renewal preserve the config-entry/entity identity and saved card order. Failed connection validation does not replace existing settings.
- Server deletion attempts to revoke only its own HA certificate. An unreachable server does not block local deletion; HA provides a manual-cleanup notification.

## Validation

39 Python tests, lint, JavaScript syntax, and browser regression checks pass locally. Live multi-server monitoring, local DNS, HACS updates, and drag reordering have been exercised in Scott's installation. Snapshot operations, normalized CPU metrics, trust cleanup, and recovery scenarios still require live acceptance testing.

## Install/update

Add https://github.com/ScottiBYTE/ha-scottibyte-incus as a HACS custom repository of type Integration. Enable beta versions when needed to select this prerelease. Restart HA and hard-refresh the frontend after updating.

## Limitations

No VM console, forced stop, snapshot export/scheduling/expiry editing, or stateful-memory snapshot creation/restore. Snapshot names created/managed here use 1–63 letters, digits, dots, underscores, or hyphens, with no consecutive dots. Attached custom storage volumes are not included in instance snapshots. Snapshots are not external backups.

In-place server reconfiguration and trust renewal require live validation. Removed-instance registry cleanup remains open release-readiness work. See RELEASE_CHECKLIST.md and VALIDATION.md. Default HACS catalog listing is a separate submission; this release supports custom-repository installation.
