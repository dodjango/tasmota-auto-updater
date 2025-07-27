---
description: Create a new local git feature branch based on the latest main branch.
---

## Feature Branch Creation Workflow

1. **Gather Feature Information**
   - What is the feature purpose? (e.g., device discovery, firmware update)
   - Is there an associated issue/ticket number?

2. **Generate Branch Name**
   // turbo
   - Format: `feature/{issue-number}-{descriptive-name}`
   - Example: `feature/123-device-discovery` or `feature/tasmota-auto-update`
   - Use kebab-case (lowercase with hyphens) for descriptive part

3. **Update Main Branch**
   // turbo
   ```bash
   git checkout main
   git pull origin main
   ```

4. **Create and Switch to Feature Branch**
   // turbo
   ```bash
   git checkout -b feature/{branch-name}
   ```

5. **Verify Branch Creation**
   // turbo
   ```bash
   git branch --show-current
   ```

6. **Set Upstream for Collaboration** (Optional)
   ```bash
   git push -u origin feature/{branch-name}
   ```