# Changelog

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
