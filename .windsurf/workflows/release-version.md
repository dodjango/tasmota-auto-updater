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

## Who authors the release PR (and why it matters)

GitHub deliberately does not run workflows for anything the built-in
`GITHUB_TOKEN` creates — "events triggered by the `GITHUB_TOKEN` will not create
a new workflow run" — to prevent recursive runs. A release PR authored that way
therefore never gets its `pytest (3.10/3.11/3.12)` runs, and because those are
required status checks on `main`, the PR is **unmergeable**: the checks are not
failing, they are missing. `gh pr checks` looks all-green because it only lists
checks that exist.

The fix is to let a **GitHub App** author the PR — a separate identity, so CI
runs normally. Set up once:

1. Create a GitHub App (personal or org): *Settings → Developer settings →
   GitHub Apps → New GitHub App*.
   - Repository permissions: **Contents: Read & write** and
     **Pull requests: Read & write**. Nothing else.
   - No webhook needed (uncheck Active).
2. Install it on this repository (*Install App*, "Only select repositories").
3. Generate a private key on the App's settings page (downloads a `.pem`).
4. In this repository: *Settings → Secrets and variables → Actions*
   - Variable `RELEASE_APP_CLIENT_ID` = the App's Client ID (not a secret).
   - Secret `RELEASE_APP_PRIVATE_KEY` = the full contents of the `.pem`.

`release-please.yml` mints a short-lived installation token from these via
`actions/create-github-app-token` and hands it to release-please. The token is
revoked when the job ends. **Until `RELEASE_APP_CLIENT_ID` exists the workflow
falls back to `GITHUB_TOKEN`**, so nothing breaks before the App is configured.

### Fallback: unblocking a release PR without the App

While the App is not set up, each release PR has a parked workflow run that must
be approved by hand:

```bash
# find the parked run (conclusion: action_required)
gh run list --branch release-please--branches--main--components--tasmota-updater --limit 5

gh api -X POST repos/dodjango/tasmota-auto-updater/actions/runs/<id>/approve
```

If the PR is also `BEHIND` (the `main` ruleset is strict), update the branch
**first** — the update creates a new commit and therefore a new parked run, so
approving before updating is wasted.

### Known follow-up: duplicate container publish

Once the App creates the tags, the tag push itself triggers
*Publish Container Image* (it listens on `push: tags: ['v*']`). The explicit
`gh workflow run` dispatch in `release-please.yml` was only needed because
`GITHUB_TOKEN` tags do not trigger anything, so the first App-driven release will
likely publish the image **twice** (same content, harmless but wasteful). Verify
the tag-triggered run happens, then remove the dispatch step.

## Version source of truth

`app/version.py` (`__version__`) is what the app serves at `/version`.
release-please keeps `app/version.py`, `app/__init__.py`, and
`pyproject.toml` in sync — configuration lives in `release-please-config.json`
and the current released version in `.release-please-manifest.json`.

## If a release PR does not appear

- Check the `release-please` workflow run under the Actions tab.
- Confirm there is at least one release-triggering commit (`feat`/`fix`) since
  the last release.
