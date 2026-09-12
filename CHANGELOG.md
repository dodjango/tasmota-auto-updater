# Changelog

## [0.6.1](https://github.com/dodjango/tasmota-auto-updater/compare/v0.6.0...v0.6.1) (2026-08-09)


### Dependencies

* **deps:** bump the pip-minor-patch group with 3 updates ([#133](https://github.com/dodjango/tasmota-auto-updater/issues/133)) ([031a065](https://github.com/dodjango/tasmota-auto-updater/commit/031a065c5ee938d593bbc0ba62e11c02b2b6f8e7))
* **deps:** update zeroconf requirement from &gt;=0.149.12 to &gt;=0.150.0 ([#134](https://github.com/dodjango/tasmota-auto-updater/issues/134)) ([bcfc9b4](https://github.com/dodjango/tasmota-auto-updater/commit/bcfc9b4d0d58e18e418072eca9ef3cc66e6eb447))

## [0.6.0](https://github.com/dodjango/tasmota-auto-updater/compare/v0.5.4...v0.6.0) (2026-08-08)


### ⚠️ Breaking change: mount the configuration directory, not the file

The new device editor writes `devices.yaml`, and replacing a file that is bind-mounted individually fails with `EBUSY`. Mount its **directory** instead:

```yaml
- ./config:/app/config          # was: ./devices.yaml:/app/devices.yaml
```

Move `devices.yaml` into that directory. The image now defaults to `DEVICES_FILE=/app/config/devices.yaml`, so no extra environment variable is needed.

Deployments that keep the old single-file mount keep working — the editor stays read-only and explains why in the UI.


### Note on device discovery

The new network discovery needs no deployment change: the IP range scan works in the default bridge-network container.

mDNS does not, and cannot — multicast does not cross a container bridge, so that search will always come back empty there (the UI says so rather than claiming no devices exist). If you want mDNS, the container has to run with `network_mode: host`, which costs network isolation and port mapping and only helps on Linux. See [Container Setup](docs/container-setup.md) for the trade-off.


### Features

* **cli:** add a thin CLI over the maintained core ([#127](https://github.com/dodjango/tasmota-auto-updater/issues/127)) ([54a0b7a](https://github.com/dodjango/tasmota-auto-updater/commit/54a0b7ad5ffea84e115024a0118101ba6e9ab6cd))
* **editor:** manage devices from the web UI ([#128](https://github.com/dodjango/tasmota-auto-updater/issues/128)) ([30d5f63](https://github.com/dodjango/tasmota-auto-updater/commit/30d5f6314029b10353bef4b5802357855587608d))
* find Tasmota devices on the network ([#131](https://github.com/dodjango/tasmota-auto-updater/issues/131)) ([6e6b161](https://github.com/dodjango/tasmota-auto-updater/commit/6e6b16122171fefdf1c0e37afb01f478dd808e92))


### Dependencies

* **deps:** bump hypothesis in the pip-minor-patch group ([#125](https://github.com/dodjango/tasmota-auto-updater/issues/125)) ([5bb88f2](https://github.com/dodjango/tasmota-auto-updater/commit/5bb88f20f3d515108a1a0b99fa2e2d24e016eb98))

## [0.5.4](https://github.com/dodjango/tasmota-auto-updater/compare/v0.5.3...v0.5.4) (2026-07-27)


### Bug Fixes

* **ci:** make dependabot.yml schema-valid again ([#121](https://github.com/dodjango/tasmota-auto-updater/issues/121)) ([197a7f8](https://github.com/dodjango/tasmota-auto-updater/commit/197a7f802fce1368d39f858ba5422f4e68760044))

## [0.5.3](https://github.com/dodjango/tasmota-auto-updater/compare/v0.5.2...v0.5.3) (2026-07-26)


### Bug Fixes

* **ui:** don't show an unknown firmware version as "Up to Date" ([7065975](https://github.com/dodjango/tasmota-auto-updater/commit/70659752bdd9634d59f7c32fb29844c6aaab9c7b)), closes [#91](https://github.com/dodjango/tasmota-auto-updater/issues/91)

## [0.5.2](https://github.com/dodjango/tasmota-auto-updater/compare/v0.5.1...v0.5.2) (2026-07-25)


### Bug Fixes

* **security:** pass device credentials via auth instead of the URL ([51da930](https://github.com/dodjango/tasmota-auto-updater/commit/51da930e44aa2134aa5e743b329d015f9ec82186))
* verify the new firmware version before reporting update success ([6690305](https://github.com/dodjango/tasmota-auto-updater/commit/669030585a0173e27678a22e37a64d8be3cc0c4b)), closes [#87](https://github.com/dodjango/tasmota-auto-updater/issues/87)

## [0.5.1](https://github.com/dodjango/tasmota-auto-updater/compare/v0.5.0...v0.5.1) (2026-07-23)


### Bug Fixes

* **ui:** refresh device card after a successful update ([#84](https://github.com/dodjango/tasmota-auto-updater/issues/84)) ([5e9ea1d](https://github.com/dodjango/tasmota-auto-updater/commit/5e9ea1d3ff6364712cd3a1546164522b3f2261e6))

## [0.5.0](https://github.com/dodjango/tasmota-auto-updater/compare/v0.4.0...v0.5.0) (2026-07-23)


### Features

* async background jobs for batch device updates ([#80](https://github.com/dodjango/tasmota-auto-updater/issues/80)) ([e4787ab](https://github.com/dodjango/tasmota-auto-updater/commit/e4787ab949bed9fd666a091be52429446d9812c5)), closes [#70](https://github.com/dodjango/tasmota-auto-updater/issues/70)

## [0.4.0](https://github.com/dodjango/tasmota-auto-updater/compare/v0.3.1...v0.4.0) (2026-07-23)


### Features

* **security:** fail-closed API auth via UI session cookie + CSRF hardening ([#78](https://github.com/dodjango/tasmota-auto-updater/issues/78)) ([a6901fb](https://github.com/dodjango/tasmota-auto-updater/commit/a6901fb17ba872848787e0c4b11680c7eda93c75)), closes [#69](https://github.com/dodjango/tasmota-auto-updater/issues/69)

## [0.3.1](https://github.com/dodjango/tasmota-auto-updater/compare/v0.3.0...v0.3.1) (2026-07-22)


### Bug Fixes

* **ci:** stop Dependabot PR pileup from per-PR version.py bumps ([#62](https://github.com/dodjango/tasmota-auto-updater/issues/62)) ([6d4ea4e](https://github.com/dodjango/tasmota-auto-updater/commit/6d4ea4e082343341876899534be561f32bdabf8e))
