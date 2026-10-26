# ScottiBYTE Incus v0.1.8 — offline server cards and addresses

- Show each server's configured IP address or hostname on its card, including while offline.
- Disable instance drill-down on offline server cards. Reordering remains available through the separate drag handles and arrow controls.
- Exclude offline servers' cached instance lists from the dashboard API and global search.
- Return an open inventory view to the server cards when its server becomes unreachable; clear an open snapshot list.
- Retain internal snapshots and clearly labelled last-known counts for recovery and summaries. Offline means unreachable, not necessarily powered off.

41 Python tests and browser checks cover offline list suppression, card addresses, loss of reachability while viewing instances, and recovery. Testing prerelease.
