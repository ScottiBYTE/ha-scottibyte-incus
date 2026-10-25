# Staging and publishing

Your staging container is **ScottiBYTE-Incus**, running Ubuntu 26.04, with the **scott** sudo user. The repository owner is **ScottiBYTE** and the Git commit email is **vmsman@scottibyte.com**.

Use a dedicated Ubuntu Incus development container and keep this repository under your normal user, for example `/home/scott/ha-scottibyte-incus`. The container stores source and Git credentials; it does not need to run a dashboard web server.

Use a separate Home Assistant test instance for first installation. Its network must reach the Incus test server. Start with a disposable test container for lifecycle and terminal checks.

## Unpack the source

Download the source ZIP, place it in the development container, and run as your normal user:

```bash
sudo apt update
sudo apt install -y git unzip ca-certificates openssh-client
unzip ha-scottibyte-incus-v0.1.0.zip
cd ha-scottibyte-incus
bash tools/prepare_workspace.sh
```

If you already unpacked the source elsewhere, move that directory rather than unpacking another copy inside it. You do not need to install Python dependencies to push this repository or install it through HACS.

## Run tests

Tests require **Python 3.14.2 or newer**, matching the tested Home Assistant runtime. Install the appropriate interpreter for your development container before running:

```bash
python3 --version
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
```

The API/enrollment tests start local loopback SSH/HTTPS servers. They do not connect to your production Incus hosts. HA component tests load the actual 2026.10.4 runtime and use isolated temporary configuration directories.

If Node.js is installed, syntax-check the frontend with:

```bash
node --check custom_components/scottibyte_incus/frontend/panel.js
```

The browser smoke test uses a separate development dependency, Playwright. It supplies fake inventory and terminal responses and never controls an Incus server:

```bash
.venv/bin/python -m pip install playwright
.venv/bin/python -m playwright install chromium
.venv/bin/python tools/browser_smoke.py
```

## Push to GitHub

Create an empty repository named `ha-scottibyte-incus` under your ScottiBYTE GitHub account, then run from the unpacked source directory:

```bash
git init -b main
git config --local user.name "ScottiBYTE"
git config --local user.email "vmsman@scottibyte.com"
git add .
git commit -m "Initial ScottiBYTE Incus Home Assistant integration"
git remote add origin https://github.com/ScottiBYTE/ha-scottibyte-incus.git
git push -u origin main
```

Authenticate with your usual GitHub method. HTTPS requires a token or credential helper; GitHub account passwords do not authenticate Git pushes. Alternatively use your existing GitHub SSH key and the SSH remote URL.

The ZIP intentionally contains no Git credentials, server credentials, trust tokens, generated client certificates, or test virtual environments.

## First live test

1. Install the custom integration in the HA test instance and restart HA.
2. Add one test Incus server using automatic SSH setup.
3. Verify that no manual token step is needed.
4. Confirm summary counts and instance rows against `incus list` on that server.
5. Start and gracefully stop a disposable container from the panel.
6. Open its terminal, run `whoami`, resize it, test Ctrl+C and copy/paste, then close it.
7. Disconnect the browser and verify no interactive shell is left running.
8. Temporarily make the test server unreachable; verify stale inventory and disabled controls.
9. Reconnect it and verify recovery.
10. Add another independent server and test global search with duplicate instance names.

See VALIDATION.md for the remaining acceptance cases.

## Releases and HACS

The initial package is version `0.1.0` and should be treated as a testing build. Publish a GitHub **prerelease** for early testers after the live checks. Keep `manifest.json` and `const.py` versions aligned when changing versions.

HACS custom-repository installation works from a correctly structured repository; default-catalog submission is a separate step. Branding/catalog checks may require additional work before that submission. GitHub Actions includes Python tests, lint, frontend syntax, and hassfest validation. A remote CI run can only be confirmed after this repository is published.
