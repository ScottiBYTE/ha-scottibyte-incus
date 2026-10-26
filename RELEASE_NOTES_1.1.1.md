# ScottiBYTE Incus v1.1.1

- Enable the existing root terminal for running Linux VMs via the Incus agent.
- Include guest OS metadata and terminal eligibility in normalized inventory. Known Windows/BSD/macOS VMs are excluded; guests with missing OS metadata may attempt the Linux shell.
- Explain agent/shell requirements when VM exec fails and release failed terminal reservations.
- Wrap long terminal titles and help text; keep the dialog and close control within mobile viewports.
- Preserve cluster cards, pinned trust, terminal ownership checks and session limits.

55 Python tests pass locally. Browser checks cover VM terminal opening and closing at 360, 390, 480 and desktop widths, alongside existing regression checks. Ruff and JavaScript syntax validation pass. GitHub tests/hassfest must pass for the release commit. Scott confirmed the agent responds to exec in Desktop-2404; live acceptance of the embedded VM shell remains to be done after installation.

This is a root guest shell, not a serial or graphical VM console. Existing terminals do not automatically reconnect after endpoint failure.
