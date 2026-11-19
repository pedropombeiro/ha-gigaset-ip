# Changelog

## 0.2.2

- Show the translated wrong-base error during reauthentication instead of a raw
  translation key. Keep the original configuration unchanged when another base
  is selected.
- Add a regression test for wrong-base reauthentication.

## 0.2.1

- Read the configured timezone without blocking Home Assistant's event loop
  during polling.

## 0.2.0

- Add Last NTP synchronization and Uptime since diagnostic timestamp sensors.
- Display readable firmware metadata and refresh it during polling.
- Retain valid timestamps through failed polls and missing or malformed fields.
  Expose parsing status separately without affecting provider registration.
- Interpret base-local timestamps using Home Assistant's timezone. Both must
  match. Reject ambiguous or nonexistent daylight-saving times.

All 40 automated tests pass against Home Assistant `2026.10.4`, along with
hassfest and all 10 HACS checks. The timestamp parsers also pass against the
private S850A GO capture. These additions have not yet been validated live.
Handset inventory and NTP-age alerts are not included.

## 0.1.0

- Monitor registration separately for each configured provider.
- Configure host and system PIN through Home Assistant, with reauthentication.
- Reboot the base manually and refresh registration status on demand.
- Report polling status and the last successful update as diagnostic sensors.
- Map accounts using firmware slot metadata rather than visible row positions.
- Install through Home Assistant Marketplace using the README shortcut.

Validated against an S850A GO running firmware `42.263` on Home Assistant
`2026.11.0`, including an approved reboot followed by provider recovery.
Automated integration tests use Home Assistant `2026.10.4`, the version supported
by the current test harness. Other base models and languages are unverified.
