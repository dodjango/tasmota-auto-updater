---
description: Create a new release using Semantic Versioning
---
# Release a New Version

This workflow guides you through creating a new release of the Tasmota Updater project using Semantic Versioning with GitHub CLI.

## Prerequisites

1. Ensure GitHub CLI is installed and authenticated:
```bash
# Check if GitHub CLI is installed
gh --version

# If not installed, install it (example for Ubuntu/Debian)
# sudo apt install gh

# Authenticate with GitHub
gh auth login
```

## Steps

1. Ensure your working directory is clean and you're on the main branch:
```bash
# Check repository status
gh repo view --web

# Switch to main branch and pull latest changes
git checkout main
git pull
```

2. Update the version number in `app/version.py` according to Semantic Versioning rules:
   - MAJOR: Incompatible API changes
   - MINOR: Backward-compatible new functionality
   - PATCH: Backward-compatible bug fixes

3. Commit the version change:
```bash
git add app/version.py
git commit -m "Bump version to x.y.z"
```

4. Create a release branch (optional but recommended):
```bash
git checkout -b release/vx.y.z
```

5. Push the changes:
```bash
# If using a release branch
git push -u origin release/vx.y.z

# If working directly on main
git push origin main
```

6. Generate release notes from git commits and create a GitHub release:
```bash
# Generate release notes from commits since the last tag
PREVIOUS_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")

if [ -z "$PREVIOUS_TAG" ]; then
  # If there are no previous tags, get all commits
  RELEASE_NOTES=$(git log --pretty=format:"* %s (%h)" --no-merges)
else
  # Get commits since the last tag
  RELEASE_NOTES=$(git log ${PREVIOUS_TAG}..HEAD --pretty=format:"* %s (%h)" --no-merges)
fi

# Create a release with automatically generated notes
gh release create vx.y.z --title "Release vx.y.z" --notes "$RELEASE_NOTES"

# Alternative: Use GitHub's auto-generated release notes
# gh release create vx.y.z --title "Release vx.y.z" --generate-notes
```

7. Monitor the GitHub Actions workflow that will automatically:
```bash
# View the running workflows
gh workflow list

# View the status of the latest workflow run
gh run list --workflow "Publish Container Image" --limit 1

# Watch the workflow progress
gh run watch
```
