# Contributing to Tasmota Updater

Thank you for your interest in contributing to the Tasmota Updater project!

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/yourusername/tasmota-updater.git`
3. Set up your development environment using `uv`:
   ```bash
   uv venv
   uv pip install -r requirements.txt
   ```
4. Create a branch for your changes: `git checkout -b feature/your-feature-name`

## Coding Guidelines

- Follow PEP 8 style guidelines for Python code
- Use meaningful variable and function names
- Add docstrings to all functions with parameters and return values
- Use type hints where appropriate

Example function format:

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

Use appropriate log levels (`DEBUG`, `INFO`, `WARNING`, `ERROR`) and include context in messages:

```python
logger.info(f"{device_info}: Upgrading to latest official release")
logger.error(f"{device_info}: Failed to connect: {error_message}")
```

## Testing

Before submitting changes, test in both normal and dry run modes, and verify error handling.

## Submitting Changes

1. Commit with clear, descriptive messages
2. Push to your fork
3. Submit a pull request with a description of the changes

---

Thank you for contributing to the Tasmota Updater project!
