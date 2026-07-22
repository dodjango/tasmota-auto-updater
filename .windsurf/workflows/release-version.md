---
description: How releases work (automated via release-please)
---

# Releasing a New Version

Releases are **fully automated** by [release-please](https://github.com/googleapis/release-please)
via the `.github/workflows/release-please.yml` workflow. There is no manual
version-bump / tag / `gh release create` step anymore.

## How it works

1. **Merge conventional commits to `main`.** Version bumps are derived from the
   commit types:
   - `feat: …` → minor bump (e.g. 0.3.0 → 0.4.0)
   - `fix: …` → patch bump (e.g. 0.3.0 → 0.3.1)
   - `feat!: …` / `BREAKING CHANGE:` → minor bump while < 1.0.0
     (`bump-minor-pre-major` is enabled)
   - `chore`/`docs`/`test`/`ci`/dependency bumps → no release on their own
2. **release-please opens/updates a release PR** titled `chore(main): release x.y.z`.
   It keeps the version (`app/version.py`, `app/__init__.py`, `pyproject.toml`)
   and `CHANGELOG.md` up to date as more commits land.
3. **Merge the release PR** to cut the release. That creates the git tag
   `vx.y.z` and the GitHub release, and then dispatches the
   *Publish Container Image* workflow for the new tag so the versioned container
   image is built.

## Version source of truth

`app/version.py` (`__version__`) is what the app serves at `/version`.
release-please keeps `app/version.py`, `app/__init__.py`, and
`pyproject.toml` in sync — configuration lives in `release-please-config.json`
and the current released version in `.release-please-manifest.json`.

## If a release PR does not appear

- Check the `release-please` workflow run under the Actions tab.
- Confirm there is at least one release-triggering commit (`feat`/`fix`) since
  the last release.
