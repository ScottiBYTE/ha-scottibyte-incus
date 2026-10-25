# Version 0.1.0 validation

## Completed locally

- **17 Python tests pass** using the actual Home Assistant **2026.10.4** runtime on Python **3.14.8**.
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

## Not yet completed

- Connection to an actual Incus 7.5.1 server or the user's production servers.
- Real sudo elevation paths and different SSH server configurations.
- Independent-host and cluster behavior under real networking, failover, and guest-agent failures.
- Termination behavior of real guest shells on browser/network loss, guest shutdown timeouts, and unusual guest distributions.
- Long-running load, large output, terminal backpressure, reconnection, and HA restart behavior.
- HACS installation from the published repository and a remote GitHub Actions/hassfest run.
- HACS default-catalog acceptance.

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

The initial build has no VM console, forced stop, lifecycle automation services, project/address reconfiguration flow, automatic remote trust revocation, or removed-entity registry cleanup. These limitations are documented in README.md.
