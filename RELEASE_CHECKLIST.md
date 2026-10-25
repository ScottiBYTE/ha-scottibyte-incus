# v1.0 release readiness

Version 0.1.5 is a testing build, not a stable-release declaration.

## Implemented; verify in live HA

- [ ] Snapshot create/list/rename/delete/restore on disposable container and VM; running restore rejected; cancellations change nothing.

- [ ] CPU % of host matches sampled Incus usage divided by the actual host logical CPU count.
- [ ] Cluster instances use their member's capacity; a move resets the CPU sample.
- [ ] Primary IP prefers the guest NIC over nested Docker networks; every IP remains visible in Details.
- [ ] Delete a disposable server entry: only its HA certificate is revoked; guests keep running.
- [ ] Delete while unreachable: HA removal succeeds and a cleanup notification identifies the certificate.

## Remaining engineering and validation

- [x] Implement in-place address/project reconfiguration and deliberate certificate trust renewal, preserving entity identity.
- [ ] Verify both reconfiguration paths in live HA, including a rejected connection test and a rotated certificate.
- [ ] Define and implement cleanup for removed instance devices/entities.
- [ ] Add recovery/enrollment failure regressions where automated coverage is missing.
- [ ] Exercise non-admin access, lifecycle actions, timeouts, and terminal cleanup on disposable guests.
- [ ] Exercise outage → HA restart → reconnect, large output, and prolonged use.
- [ ] Verify saved order survives HA restart and is consistent across devices. Drag interaction is confirmed working.
- [ ] Validate a Raspberry Pi/ARM host and document the supported HA/Incus versions actually tested.
- [ ] Capture current screenshots without private details and update user documentation.
- [ ] Fresh HACS install and upgrade to a tagged v1.0.0-rc.1 release; all CI checks pass for that commit.
- [ ] Resolve release-candidate findings before tagging v1.0.0.

## Separate distribution milestone

- [ ] Submit to the default HACS catalog after meeting its current requirements. A custom-repository install does not require catalog acceptance.
