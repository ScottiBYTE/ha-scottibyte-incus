# ScottiBYTE Incus v0.1.6 — native snapshot restore behavior

- Remove the integration's stopped-first restriction for snapshot restore.
- Allow restore for running containers and VMs. Incus handles their stop/restore/restart sequence; stopped instances remain stopped.
- Keep confirmation that the current disk/configuration will be replaced and clarify that saved running memory is not restored.
- Retain instance operation locking, administrator-only access, snapshot existence validation, and operation-completion checks.

40 Python tests pass locally, including running and stopped restore requests. Browser tests verify the revised confirmation text. Scott reported successful container restore and restart; this exact integration update still requires live confirmation. This remains a prerelease on the path to v1.0.
