# Contributing to Tasmota Updater

Thank you for your interest in contributing to the Tasmota Updater project! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Environment](#development-environment)
- [Making Changes](#making-changes)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Submitting Changes](#submitting-changes)
- [Feature Requests](#feature-requests)
- [Bug Reports](#bug-reports)

## Code of Conduct

Please be respectful and considerate of others when contributing to this project. We aim to foster an inclusive and welcoming community.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/yourusername/tasmota-updater.git`
3. Set up your development environment (see below)
4. Create a new branch for your changes: `git checkout -b feature/your-feature-name`

## Development Environment

This project uses `uv` for dependency management. To set up your development environment:

```bash
# Install uv if you don't have it
curl -sSf https://install.ultraviolet.rs | sh

# Create a virtual environment and install dependencies
uv venv
uv pip install -r requirements.txt
```

## Making Changes

### Adding New Features

When adding new features:

1. Make sure your feature aligns with the project's purpose
2. Add appropriate logging using the existing logging framework
3. Update documentation (README.md) to reflect your changes
4. Add appropriate error handling

### Modifying Existing Code

When modifying existing code:

1. Maintain backward compatibility when possible
2. Preserve the existing logging structure
3. Follow the established coding style

## Coding Standards

- Follow PEP 8 style guidelines for Python code
- Use meaningful variable and function names
- Add docstrings to all functions and classes
- Keep functions focused on a single responsibility
- Use type hints where appropriate

Example function with proper documentation:

```python
def update_device(device_config: dict, dry_run: bool = False) -> bool:
    """
    Update a Tasmota device with the latest firmware
    
    Args:
        device_config (dict): Device configuration containing address and credentials
        dry_run (bool): If True, simulate the update without making changes
        
    Returns:
        bool: True if the update was successful, False otherwise
    """
    # Implementation here
```

## Logging

The project uses Python's built-in logging module. When adding new code:

1. Use the appropriate log level:
   - `DEBUG`: Detailed information for diagnosing problems
   - `INFO`: Confirmation that things are working as expected
   - `WARNING`: Indication that something unexpected happened
   - `ERROR`: Due to a more serious problem, a function failed
   - `CRITICAL`: A serious error that may prevent the program from continuing

2. Include relevant context in log messages:
   - For device operations, include the device address/hostname
   - For file operations, include the file path
   - For errors, include the error message

Example:

```python
logger.info(f"{device_info}: Upgrading to latest official release")
logger.error(f"{device_info}: Failed to connect: {error_message}")
```

## Testing

Before submitting changes:

1. Test your changes in both normal and dry run modes
2. Verify that logging works correctly
3. Test with different configuration files
4. Test error handling by simulating failure conditions

## Submitting Changes

1. Commit your changes with clear, descriptive commit messages
2. Push to your fork
3. Submit a pull request with a clear description of the changes
4. Reference any related issues in your pull request

## Feature Requests

When requesting new features:

1. Clearly describe the feature and its purpose
2. Explain how it would benefit users
3. Provide examples of how it would be used

## Bug Reports

When reporting bugs:

1. Describe the bug clearly
2. Include steps to reproduce the issue
3. Describe the expected behavior
4. Include logs if available
5. Specify your environment (OS, Python version, etc.)

---

Thank you for contributing to the Tasmota Updater project!
