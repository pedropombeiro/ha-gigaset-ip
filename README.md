# Gigaset IP for Home Assistant

Monitor provider registration on a Gigaset IP base through its local web
configurator. Enter the base host and system PIN during setup.

## Status

This is development code. Parsing is checked against a private capture from an
S850A GO running firmware `42.263`. The async client also read all five
connections successfully from that base and logged out. On Home Assistant
`2026.11.0`, setup, registration entities, and the reboot button were tested
against that base. A failed provider registered successfully after an explicitly
approved reboot. Other models and languages are not verified.

## Features

- One connectivity entity per connection slot.
- Disabled accounts and the fixed line are disabled in the entity registry by default.
- A manual reboot button. Rebooting interrupts every provider and any active call.
- Reauthentication when the base explicitly rejects the PIN.
- Short, serialized sessions with logout after each poll. Polling runs every five minutes.

The integration does not send notifications or reboot automatically. Configure
those policies with Home Assistant automations.

## Install for development

1. Copy `custom_components/gigaset_ip` into your Home Assistant configuration's
   `custom_components` directory.
1. Restart Home Assistant.
1. Log out of the base's browser configurator.
1. Open **Settings > Devices & services > Add integration**, then select
   **Gigaset IP** and enter the host and four-digit PIN.

HACS custom-repository installation will be available after publication.

## Overall connectivity

Create a **Group > Binary sensor** helper with the provider entities you care
about. Enable **All entities** and select the connectivity device class.
All providers must be connected for the group to show connected. Unknown or
unavailable members make the aggregate unknown instead of healthy.

Use per-provider triggers for notifications: the group does not change again
when another provider fails while one is already disconnected.

## Limitations and security

- Only English status rows are currently supported.
- The base permits only one web session. Log out of its browser configurator
  before setup. A busy session makes polling unavailable, not disconnected.
- Home Assistant stores the PIN in its config entry on disk. Protect the config
  directory and backups. HTTP transmits the PIN without encryption on the LAN.
- The client never retries a failed login within a poll. An explicit invalid-PIN
  error stops polling and requests reauthentication.
- Account identifiers follow displayed VoIP row positions. Firmware that omits
  empty rows may change slot identity when accounts are removed. This needs live
  verification before relying on identities across account reconfiguration.
- No registration data is available while Home Assistant itself is down.

## Develop

```sh
mise run setup
mise run check
```

Public fixtures are synthetic. Do not commit raw captures, account names, PINs,
cookie jars, or login request bodies.

For Home Assistant-level tests, run `mise run setup:ha`, then
`mise run test:ha`. The test harness pins Home Assistant `2026.10.4`.
Its private logger imports are incompatible with `2026.11.0`, so do not override
that dependency. Automated tests cover `2026.10.4`; live Home Assistant setup
on `2026.11.0` remains a separate, pending validation step.

`mise run format` formats Python. `mise run lint:fix` also fixes lint findings.
CI uses these same tasks. Renovate groups Home Assistant test dependencies and
keeps GitHub Actions pinned. Releases remain manual during initial validation.
