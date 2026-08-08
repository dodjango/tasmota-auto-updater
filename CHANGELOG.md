# Changelog

## [0.6.0](https://github.com/dodjango/tasmota-auto-updater/compare/v0.5.4...v0.6.0) (2026-08-08)


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
