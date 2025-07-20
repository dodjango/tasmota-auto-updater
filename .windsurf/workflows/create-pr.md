---
description: Create a Pull Request for this Feature Branch in GitHub.
---

## Preparation Steps

1. Check if we are on a feature branch
```bash
git branch --show-currentasdas
```
If the output is "main" or "master", abort the workflow and warn the user that pull requests should only be created from feature branches.

2. Check for uncommitted changes
```bash
git status --porcelain
```
If there are uncommitted changes, prompt the user to commit them first with a meaningful commit message:
```bash
git add .
git commit -m "[YOUR COMMIT MESSAGE]"
```

3. Make sure the local branch is up to date with the remote main
```bash
git fetch origin
git merge origin/main --no-commit --no-ff
```
If there are merge conflicts, abort and ask the user to resolve them manually:
```bash
git merge --abort
```
Then instruct the user to:
```bash
git pull origin main
# Resolve conflicts manually
git add .
git commit -m "Merge main into feature branch"
```

4. Run tests to ensure code quality
```bash
pytest
```
If tests fail, warn the user and ask if they want to continue anyway. It's generally not recommended to create PRs with failing tests.

## Push to GitHub

5. Check if the branch exists on the remote
```bash
git ls-remote --heads origin $(git branch --show-current)
```

6. Push the branch to GitHub
// turbo
```bash
git push -u origin $(git branch --show-current)
```

## Create Pull Request

7. Generate a comprehensive PR description using the following template:
```
## Changes
[Describe the changes made in this PR]

## Testing
[Describe how these changes were tested]

## Related Issues
[Link to any related issues]

## Checklist
- [ ] Code follows project style guidelines
- [ ] Tests for the changes have been added
- [ ] Documentation has been updated
- [ ] Changes generate no new warnings
```

8. Create the Pull Request using GitHub CLI
```bash
gh pr create --title "[FEATURE] $(git branch --show-current | sed 's/-/ /g' | sed 's/\b\(\w\)/\u\1/g')" --body-file pr-description.md
```
If GitHub CLI is not installed, abort.

9 Remove the generated file pr-description.md.

9. After PR creation, provide the PR URL and suggest next steps:
- Request reviews from team members
- Address any feedback or comments
- Monitor CI/CD pipeline for any issues