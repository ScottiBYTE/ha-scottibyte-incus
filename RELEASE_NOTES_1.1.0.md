# ScottiBYTE Incus v1.1.0

- Add multiple members of the same Incus cluster as separate server entries and cards.
- Distinguish member identity from the shared pinned cluster certificate; preserve existing entries.
- Filter each card to instances located on that member, including saved pre-upgrade inventories.
- Show cluster membership, member name, cluster size and active API address; wrap long addresses on mobile.
- Discover and checkpoint trusted cluster endpoint addresses, with connection selection on refresh when the active endpoint becomes unreachable.
- Reject duplicate member aliases and attempt to revoke their newly enrolled identity.
- Keep each member's client credentials independent for removal and trust renewal.

## Validation

46 Python regression tests pass locally, including member enrollment, duplicate handling, inventory isolation, legacy cache handling, offline status and endpoint selection. Browser regression checks pass at 360, 390, 480 and desktop widths. JavaScript syntax and Ruff pass. GitHub tests and hassfest must pass on the exact release commit before publication.

Live testing against Scott's three-member cluster is still required. Test adding VMSFog-Incus and Incus-member while retaining VMSCloud-Incus, compare per-member inventories with Incus, and verify access to healthy members while one endpoint is unavailable.

## Scope

Only configured members contribute inventory. Failover requires prior discovery and reachable/resolvable advertised HTTPS member addresses, valid shared trust and a functioning cluster quorum. Offline members remain unavailable. No action request is automatically replayed; existing terminals do not reconnect automatically. Migrated-instance HA registry cleanup remains manual.
