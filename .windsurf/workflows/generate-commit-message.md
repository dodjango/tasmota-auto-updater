---
description: Generate a conventional commit message for staged changes
---

# Generate Conventional Commit Message

This workflow helps you create a well-formatted conventional commit message following the project's Git workflow guidelines.

## Steps

1. View the staged changes to understand what's being committed:
```bash
git diff --staged
```

2. Identify the appropriate commit type based on the changes:
   - `feat`: A new feature
   - `fix`: A bug fix
   - `docs`: Documentation changes only
   - `style`: Changes that don't affect code meaning (formatting, etc.)
   - `refactor`: Code change that neither fixes a bug nor adds a feature
   - `perf`: Code change that improves performance
   - `test`: Adding or correcting tests
   - `chore`: Changes to build process or auxiliary tools
   - `ci`: Changes to CI configuration files and scripts

3. Identify the scope of the changes (the component or module affected):
   - `tasmota`: Changes to Tasmota-related functionality
   - `api`: Changes to API endpoints
   - `ui`: Changes to user interface
   - `device`: Changes to device management
   - `auth`: Changes to authentication
   - `config`: Changes to configuration handling
   - `workflow`: Changes to workflows or processes
   - `db`: Changes to database models or operations
   - *(omit scope if changes span multiple components)*

4. Write a concise description in imperative mood:
   - Start with a verb (e.g., "add", "fix", "update", "remove")
   - Keep it under 50 characters if possible
   - Don't capitalize the first letter
   - No period at the end

5. If needed, add a more detailed body after a blank line:
   - Explain the motivation for the change
   - Contrast with previous behavior
   - Include issue references (e.g., "Fixes #123")

6. Assemble the commit message in the format:
```
<type>(<scope>): <description>

[optional body]
[optional footer]
```

7. Example commit messages:
   - `feat(device): add automatic discovery mechanism`
   - `fix(api): handle timeout errors in device communication`
   - `docs(readme): update installation instructions`
   - `refactor(tasmota): improve error handling in update process`
   - `style(ui): align form elements consistently`
   - `perf(api): optimize device status polling`
   - `test(updater): add test cases for firmware validation`
   - `chore(deps): update dependencies to latest versions`

8. Commit with your generated message:
```bash
git commit -m "type(scope): description"
```

9. For multi-line commit messages, use:
```bash
git commit -m "type(scope): description" -m "Detailed explanation of changes. Fixes #123"
```
