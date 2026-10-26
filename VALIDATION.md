# v1.0.0 validation

## Live acceptance

Scott confirmed that all current features have been tested in his live deployment. The latest mobile layout was visually confirmed in the Pixel 7 Home Assistant Companion app. Release selection was verified using numbered HACS releases rather than development commit hashes.

The observed environment uses Home Assistant Core 2026.10.4 and Incus 7.5.1, with multiple independent servers. This record does not claim separate live certification of every cluster topology, hardware architecture, or Incus version.

## Automated coverage

The regression suite covers integration setup/unload, certificate enrollment and pinning, secret handling, administrator enforcement, instance lifecycle and terminal requests, snapshot operations, CPU calculations and member targeting, DNS caching, offline data suppression/recovery, server reconfiguration, and trust cleanup. Browser checks cover summary/search, drill-down, management dialogs, terminal interaction, server reordering, and narrow layouts.

Before publication, run pytest, Ruff, JavaScript syntax validation, and the GitHub Checks workflow (tests and hassfest) for the exact release commit. The stable publishing helper stops if that workflow fails.

## Remaining limitations and follow-up

Removed-instance registry cleanup remains manual. Default HACS catalog acceptance is separate from this stable release. See README.md and RELEASE_NOTES_1.0.0.md for the supported feature scope and limitations.
