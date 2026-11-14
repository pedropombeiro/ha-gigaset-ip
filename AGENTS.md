# Agent instructions

- Read `README.md` before changing the integration.
- Keep private captures outside this repository. Use synthetic fixtures.
- Never log or export credentials, raw HTML, cookie headers, or account labels.
- Do not test the reboot action on real hardware without explicit approval.
- Treat session conflicts as unavailable, not failed provider registration or bad PIN.
- Use mise tasks for setup and validation. Run `mise run check` before completing changes.
- Run `mise run setup:ha` and `mise run test:ha` for config-flow, coordinator,
  and entity changes. Do not report the full suite passing if HA tests are skipped.
- Tool versions live in `mise.toml`; Python dependencies live in `pyproject.toml`
  and `uv.lock`. Keep CI on the same mise tasks used locally.
- The deployed baseline is HA 2026.11.0 with Python 3.14. The test harness
  currently supports HA 2026.10.4. Do not override its HA pin: private logger
  imports are incompatible with 2026.11.0. Distinguish CI from live validation.
- Use scoped Conventional Commits and keep GitHub Actions pinned to commit SHAs.
- Do not add deployment or restart behavior to setup, test, or lint tasks.
- The integration supplies device state and manual actions. Notifications,
  provider selection, and automatic remediation belong in HA automations/helpers.
- Entity IDs must remain stable across provider display-name changes. Use device
  page slot metadata, never visible-row positions. Reject ambiguous mappings.
- Ask before publishing a repository or release, or restarting Home Assistant.
