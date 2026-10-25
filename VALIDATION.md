# Version 0.1.5 validation

## Completed locally

- **39 Python regression tests pass** using the actual Home Assistant **2026.10.4** runtime on Python **3.14.8**.
- Actual integration loading: configuration-entry setup, sensors, connectivity entity, custom sidebar registration, and entry unloading.
- Configuration flow: method selection, SSH fingerprint confirmation, completed enrollment, and absence of SSH/sudo secrets in saved entry data. Private client key mode checked.
- SSH bootstrap against a local AsyncSSH server plus a TLS Incus-protocol simulator, including automatic listener setup and token retrieval.
- HTTPS token enrollment with fingerprint checking, client certificate submission, and pinned server trust. The payload uses Incus's `trust_token` field.
- Start/stop API payload and asynchronous operation completion.
- Interactive exec: concurrent PTY/control WebSocket attachment, output, input, terminal resizing, and closing.
- Backend administrator enforcement on every exposed WebSocket command, connection-bound terminal input, and rejection of unknown/offline targets.
- Inventory normalization: binary/decimal memory limits, unknown percentage limits, IP/MAC filtering, CPU delta/counter reset, and stopped instances.
- Offline behavior: preserve last successful inventory and timestamp while marking the server unreachable.
- Browser smoke test with bundled xterm assets and simulated HA responses: summary totals, cross-server search, server drill-down, start action, stop cancel/confirm, terminal keyboard input and unsubscribe cleanup, stale controls, narrow-screen width, and no JavaScript page errors.
- Python lint, JavaScript syntax, shell syntax, and JSON parsing checks.

Browser verification used Chromium 134 through Playwright 1.51.0. Browser data was simulated and does not claim connection to the user's servers. Temporary browser screenshots are QA artifacts, not repository content.

- Version 0.1.5 regression coverage: host-normalized CPU values and unknown capacity, member resource targeting/cache/failure isolation, cluster-move sample reset, guest NIC versus Docker bridge selection, deletion trust cleanup and offline fallback, snapshot API payloads/operation failures/path validation, and administrator-only snapshot endpoints.
- Snapshot browser checks: create, rename, delete cancellation/completion, and restore confirmation text. Live snapshot operations have not been claimed as verified.

- Reconfiguration tests: failed connection preserves settings, successful address/project changes preserve entry/credential identity, and certificate renewal preserves entry identity while retiring the previous client certificate.

## Confirmed in Scott's installation

- Automatic enrollment and inventory from multiple Incus 7.5.1 servers.
- HACS custom-repository installation and updates; GitHub Actions tests and hassfest passed through the previous builds.
- Sticky instance-table headers and compact network details.
- Local reverse DNS through HA's configured resolver.
- Drag-and-drop server card reordering (reported working by Scott).

## Still requires live validation

- Snapshot create/list/rename/delete/restore on disposable container and VM guests, including storage errors and stopping requirements.
- Version 0.1.5 host-normalized CPU readings and preferred guest IP selection.
- Remote trust revocation on deletion, including an unreachable server and manual cleanup notification.
- Raspberry Pi/ARM host, cluster-member targeting/migration, guest-agent failures, and different sudo configurations.
- Start/stop, shutdown timeouts, terminal cleanup under network loss, and long-running terminal output.
- Server outage followed by HA restart and recovery; order persistence across restart and another device.
- Fresh-install and upgrade checks for the release candidate; HACS default-catalog acceptance is separate.

## Live acceptance sequence

Use a separate HA test instance and disposable Incus guests.

1. Automatic SSH enrollment with a direct Incus-admin account, then an account using password-protected sudo.
2. Enrollment when HTTPS is already enabled; verify its existing listener is preserved.
3. Enrollment with HTTPS disabled; verify automatic setup and failed-attempt rollback.
4. Match totals, status, address, CPU, memory, and disk values against Incus CLI results. Verify unavailable metrics remain unset.
5. Start and gracefully stop both a container and a VM. Test a shutdown timeout without force-killing it.
6. Root container shell: `whoami`, Ctrl+C, window resize, copy/paste, `exit`, explicit close, page navigation, browser disconnect, and idle expiry. Verify shell processes do not accumulate.
7. Add a second server, duplicate instance names, multiple projects, and an Incus cluster enrolled only once.
8. Confirm non-admin users cannot access the panel or issue management/terminal API calls.
9. Interrupt server reachability, restart HA during the outage, and confirm stale data and recovery.
10. Install from HACS as a custom repository and test an update before issuing a stable release.

Version one excludes VM consoles, forced stop, and lifecycle automation services. In-place connection/trust reconfiguration is implemented and requires live validation. Removed-entity registry cleanup remains open. Remote trust cleanup now runs on deletion with a manual-cleanup notification if it fails. These limitations are documented in README.md.
