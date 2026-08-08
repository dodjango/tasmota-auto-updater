# Contributing Guide

Thank you for your interest in contributing to Tasmota Remote Updater! This document provides guidelines and instructions for contributing to the project.

## Code of Conduct

Please be respectful and considerate of others when contributing to this project. We aim to foster an inclusive and welcoming community.

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally:
   ```bash
   git clone https://github.com/yourusername/tasmota-updater.git
   cd tasmota-updater
   ```
3. Set up the development environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   pip install -r requirements-dev.txt  # If exists
   ```

## Development Workflow

### Branches

Always branch off the current `main`:

```bash
git checkout main
git pull origin main
git checkout -b feature/123-device-discovery
```

Prefixes: `feature/`, `bugfix/`, `hotfix/`, `chore/`, `refactor/`. Use kebab-case
for the descriptive part and include the issue number when there is one
(`bugfix/456-connection-timeout`).

!!! warning "No `docs/...` branch names"
    A branch named `docs` already exists, so git rejects `docs/...` branch names
    with a "directory file conflict" error. Use `chore/...` for documentation work.

### Commit messages

This project uses [Conventional Commits](https://www.conventionalcommits.org/).
The format is not cosmetic: release-please derives the next version and the
changelog from it (see [Releasing](releasing.md)).

```
<type>(<scope>): <description>

[optional body]
[optional footer]
```

- **Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`
- **Scopes** in use: `tasmota`, `api`, `ui`, `device`, `auth`, `config`, `workflow`,
  `deps` — omit the scope when a change spans several components
- **Description**: imperative mood, lowercase, no trailing period, ideally under
  50 characters
- Reference issues in the body or footer (`Fixes #123`)

Examples:

```
feat(device): add automatic discovery mechanism
fix(api): handle timeout errors in device communication
refactor(tasmota): improve error handling in update process
chore(deps): update dependencies to latest versions
```

Commits on `main` must be signed. With `commit.gpgsign=true` configured locally
this happens automatically.

### Pull requests

1. Make your changes and add tests for them

2. Run the test suite:
   ```bash
   pytest --ignore=tests/e2e -m "not stale and not slow and not integration and not browser and not docker"
   ```

3. Bring the branch up to date with `main`:
   ```bash
   git fetch origin
   git merge origin/main
   ```

4. Review `README.md` — it drifts unnoticed because ordinary diffs never touch
   it. Check badges, the clone URL, ports, commands, and that no deprecated path
   is presented as current

5. Push and open the PR:
   ```bash
   git push -u origin "$(git branch --show-current)"
   gh pr create
   ```

6. **The PR title must itself be a valid conventional commit.** PRs are
   squash-merged, and the squash title is what release-please reads — an invalid
   title silently means no release

Describe *what* changed and *how you tested it* in the PR body, and link the
related issues.

## Coding Standards

### Python

- Follow PEP 8 style guidelines
- Use meaningful variable and function names
- Add docstrings to all functions and classes
- Keep functions focused on a single responsibility
- Use type hints where appropriate

### JavaScript

- Use modern ES6+ syntax
- Follow consistent indentation (2 spaces)
- Use meaningful variable and function names
- Add comments for complex logic

### HTML/CSS

- Use semantic HTML5 elements
- Follow BEM methodology for CSS classes
- Ensure responsive design works on all screen sizes

## Testing

- Add tests for new features
- Ensure all tests pass before submitting a Pull Request
- For bug fixes, add a test that would have caught the bug

## Documentation

- Update documentation for any changes to functionality
- Add docstrings to all new functions and classes
- Keep README and other documentation up to date

## Areas for Improvement

Here are some areas where contributions would be particularly welcome:

1. **Authentication**: Add user authentication for the web interface
2. **Device Grouping**: Allow organizing devices into logical groups
3. **Custom Firmware Support**: Add support for custom firmware sources
4. **Scheduled Updates**: Implement scheduled updates through the web interface
5. **Notifications**: Add email or push notifications for update results
6. **Dark Mode**: Implement a dark mode theme for the web interface
7. **Localization**: Add support for multiple languages
8. **Push Notifications**: Add support for push notifications
10. **Device Inventory**: Add support for tracking device inventory
11. **Toggle devices**: Add support for toggling devices on and off
12. **Bulk actions**: Add support for bulk actions on devices

## Architecture Overview

Understanding the project architecture will help you contribute effectively:

### Command-Line Tool

- `tasmota_updater.py`: **deprecated** — a stub that prints a notice and exits 1.
  Its ~900 lines duplicated the update logic from `app/tasmota` and had drifted
  away from it. Use the web UI or the REST API instead; a thin CLI wrapper over
  `app/tasmota` is a backlog item

### Web Application

- `server.py`: Main entry point for the Flask web application
- `wsgi.py`: WSGI entry point for production (Gunicorn)
- `app/__init__.py`: Flask application factory
- `app/tasmota/`: Core functionality modules
  - `api.py`: API endpoints
  - `updater.py`: Device update functionality
  - `utils.py`: Utility functions
- `app/templates/`: HTML templates
- `app/static/`: Static assets (CSS, JavaScript, images)

## Development Process and Insights

This project was developed with a focus on creating a user-friendly solution for managing Tasmota devices. Some key insights from the development process:

1. **Command-line First, Web Interface Second**: We started with a robust command-line tool to handle the core functionality, then built the web interface on top of that foundation.

2. **API-Driven Architecture**: The web interface communicates with the backend exclusively through the REST API. This clean separation allows for potential future integrations.

3. **Progressive Enhancement**: The web interface is designed to work even with JavaScript disabled for basic functionality, with enhanced features when JavaScript is available.

4. **User Experience Focus**: We prioritized clear visual feedback and intuitive workflows based on how users actually interact with their Tasmota devices.

5. **Error Handling**: Comprehensive error handling was implemented throughout the application to provide clear guidance when issues occur.

6. **Modular Design**: The codebase is organized into logical modules that can be maintained and extended independently.

## Submitting Pull Requests

1. Ensure your code follows the project's coding standards
2. Include tests for new functionality
3. Update documentation as needed
4. Describe your changes in detail in the Pull Request description
5. Link to any related issues

Thank you for contributing to Tasmota Remote Updater!
