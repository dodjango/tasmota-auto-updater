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

1. Create a new branch for your feature or bugfix:
   ```bash
   git checkout -b feature/amazing-feature
   # or
   git checkout -b fix/bug-description
   ```

2. Make your changes, following the coding standards

3. Add tests for your changes if applicable

4. Run the tests to ensure everything works:
   ```bash
   pytest
   ```

5. Commit your changes with a descriptive commit message:
   ```bash
   git commit -m "Add amazing feature"
   ```

6. Push to your fork:
   ```bash
   git push origin feature/amazing-feature
   ```

7. Create a Pull Request from your fork to the main repository

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

1. **Device Discovery**: Implement automatic device discovery on the local network
2. **Authentication**: Add user authentication for the web interface
3. **Device Grouping**: Allow organizing devices into logical groups
4. **Custom Firmware Support**: Add support for custom firmware sources
5. **Scheduled Updates**: Implement scheduled updates through the web interface
6. **Notifications**: Add email or push notifications for update results
7. **Dark Mode**: Implement a dark mode theme for the web interface
8. **Localization**: Add support for multiple languages

## Architecture Overview

Understanding the project architecture will help you contribute effectively:

### Command-Line Tool

- `tasmota_updater.py`: Main script for the command-line interface
- Uses modules from the `app/tasmota` directory for core functionality

### Web Application

- `app.py`: Main entry point for the Flask web application
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
