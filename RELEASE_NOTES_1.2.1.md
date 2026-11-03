# ScottiBYTE Incus v1.2.1

Maintenance release addressing Home Assistant event-loop responsiveness during setup.

- Move temporary credential file creation, SSL-context loading, and temporary directory cleanup off the event loop during token enrollment and duplicate-enrollment cleanup.
- Parse SSH private keys in the executor during automatic enrollment and host-metrics setup.
- Update installation instructions to lead with HACS search and remove stale beta/catalog-pending language.

No configuration migration is required.
