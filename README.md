# Tasmota Remote Updater

![Tasmota Logo](https://tasmota.github.io/docs/_media/logo.png)

> Keep your Tasmota devices up to date with a single command or click

Tasmota Remote Updater is a very simple tool that automatically updates multiple Tasmota devices to the latest firmware over your network. No more manual updates or complex scripts - just point it at your devices and let it handle the rest.

[![Python 3.6+](https://img.shields.io/badge/python-3.6+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## ✨ Features

**Two powerful interfaces in one tool:**

### 🖥️ Command-Line
- Update multiple devices with a single command
- Automatic version checking and smart updates
- Detailed reporting and logging

### 🌐 Web Interface
- Modern, responsive dashboard
- Real-time status monitoring
- One-click updates for individual or all devices
- RESTful API with Swagger documentation

![Screenshot](docs/images/dashboard.png)

## 🚀 Quick Start

```bash
# Clone the repository
git clone https://github.com/yourusername/tasmota-updater.git
cd tasmota-updater

# Create a virtual environment and install dependencies
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Run the web interface
python app.py
```

Then visit http://localhost:5001 in your browser.

## 🔄 Development with VS Code

This project includes VS Code tasks:

1. **Automatic Development Server**: The Flask development server starts automatically when you open the project in VS Code.

2. **Additional Tasks**: You can also run these tasks manually from the VS Code Command Palette (`Ctrl+Shift+P` or `Cmd+Shift+P`):
   - `Start Flask Development Server`: Basic Flask server with auto-reload
   - `Start Enhanced Development Server`: Flask server with enhanced file watching (includes static files)
   - `Setup Development Environment`: Install required dependencies

The development server will automatically reload when code changes are detected, making the development process faster and more efficient.

## 📚 Documentation

- [Installation Guide](docs/installation.md)
- [Command-Line Usage](docs/cli-usage.md)
- [Web Interface Guide](docs/web-interface.md)
- [API Documentation](docs/api.md)
- [Configuration Options](docs/configuration.md)
- [Troubleshooting](docs/troubleshooting.md)

## 🤝 Contributing

Contributions are welcome! See our [Contributing Guide](docs/contributing.md) for more details.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Tasmota](https://tasmota.github.io/docs/) - For their excellent open-source firmware
- [Flask](https://flask.palletsprojects.com/) - Web framework
- [Bulma](https://bulma.io/) - CSS framework
- [Alpine.js](https://alpinejs.dev/) - JavaScript framework


