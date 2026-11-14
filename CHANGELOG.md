# Changelog

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
