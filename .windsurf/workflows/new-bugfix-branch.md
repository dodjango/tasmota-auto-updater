---
description: Create a new local git bugfix branch based on the latest main branch.
---

## Bugfix Branch Creation Workflow

1. **Gather Bug Information**
   - What issue is being fixed? (e.g., connection timeout, firmware validation)
   - Is there an associated issue/ticket number?
   - What are the steps to reproduce the bug?

2. **Generate Branch Name**
   // turbo
   - Format: `bugfix/{issue-number}-{descriptive-name}`
   - Example: `bugfix/456-connection-timeout` or `bugfix/firmware-validation-error`
   - Use kebab-case (lowercase with hyphens) for descriptive part

3. **Update Main Branch**
   // turbo
   ```bash
   git checkout main
   git pull origin main
   ```

4. **Create and Switch to Bugfix Branch**
   // turbo
   ```bash
   git checkout -b bugfix/{branch-name}
   ```

5. **Verify Branch Creation**
   // turbo
   ```bash
   git branch --show-current
   ```

6. **Set Upstream for Collaboration** (Optional)
   ```bash
   git push -u origin bugfix/{branch-name}
   ```

7. **Document Bug Fix Context** (Recommended)
   - Create a brief note about what's being fixed
   - Include any relevant error logs or screenshots
   - Document the expected behavior after the fix
