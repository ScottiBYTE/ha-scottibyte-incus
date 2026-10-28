# ScottiBYTE Incus v1.2.0

Stable release of whole-server monitoring and dashboard improvements.

- Measure Linux host CPU and memory utilization across all applications, independently of instance metrics.
- Display local filesystem used/total capacity on each server card.
- Enable host monitoring during new-server setup or through reconfiguration of an existing server.
- Use a dedicated restricted SSH key for host monitoring; supplied setup credentials are discarded.
- Configure a persistent global refresh interval of 10 seconds, 30 seconds, 1 minute or 5 minutes.
- Keep server cards aligned, with compact tinted resource panels and readable mobile filesystem lists.
- Retain last-known indicators when host measurements are unavailable.

Existing server registrations and beta host-monitoring enrollment carry over. Existing stable installations can enable host monitoring through server reconfiguration. Host monitoring requires Linux, Python 3 and ongoing SSH connectivity.

This release promotes the tested v1.2.0-beta.3 functionality without behavioral changes. Live testing confirmed enrollment for both existing and newly added servers. HACS catalog inclusion is separate from this release.
