#!/usr/bin/env python3
"""
Tasmota Updater Web Application

A web interface for managing and updating Tasmota devices.
"""
import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, render_template, send_from_directory, jsonify
from flask_cors import CORS
from flasgger import Swagger
from app.tasmota.api import init_api
from app.version import __version__

# Setup logging
logging.basicConfig(
    level=getattr(logging, os.environ.get('LOGGING_LEVEL', 'INFO')),
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
env_file = os.environ.get("ENV_FILE", ".env")
if os.path.exists(env_file):
    logger.info(f"Loading environment from {env_file}")
    load_dotenv(env_file)
else:
    logger.warning(f"Environment file {env_file} not found, using default values")

def create_app(test_config=None):
    """Create and configure the Flask application"""
    # Create and configure the app
    app = Flask(__name__, 
                static_folder='app/static',
                template_folder='app/templates')
    
    # Load default configuration
    app.config.from_mapping(
        SECRET_KEY=os.environ.get('SECRET_KEY', 'dev'),
        DEVICES_FILE=os.environ.get('DEVICES_FILE', 'devices.yaml'),
        DEV_MODE=os.environ.get('DEV_MODE', 'false').lower() in ('true', '1', 't'),
        # Security settings
        SESSION_COOKIE_SECURE=os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() in ('true', '1', 't'),
        SESSION_COOKIE_HTTPONLY=os.environ.get('SESSION_COOKIE_HTTPONLY', 'true').lower() in ('true', '1', 't'),
        SWAGGER={
            'title': 'Tasmota Updater API',
            'description': 'API for managing and updating Tasmota devices',
            'version': __version__,
            'uiversion': 3,
        }
    )
    
    # Log the current configuration
    if app.config['DEV_MODE']:
        logger.info("Running in DEVELOPMENT MODE")
    
    logger.info(f"Using devices file: {app.config['DEVICES_FILE']}")

    # Enable CORS
    CORS(app)
    
    # Initialize Swagger
    Swagger(app)
    
    # Initialize API routes
    init_api(app)
    
    # Add version endpoint
    @app.route('/version')
    def get_version():
        """Return the application version"""
        return jsonify({
            'version': __version__,
            'name': 'Tasmota Updater'
        })
    
    # Main route
    @app.route('/')
    def index():
        """Serve the main application page"""
        return render_template('index.html')
    
    # Favicon route
    @app.route('/favicon.ico')
    def favicon():
        """Serve the favicon"""
        return send_from_directory(os.path.join(app.root_path, 'app/static/images'),
                                   'favicon.ico', mimetype='image/vnd.microsoft.icon')
    
    # Health check endpoint for Docker
    @app.route('/health')
    def health():
        """Health check endpoint for container orchestration"""
        return {"status": "healthy"}, 200
    
    return app

if __name__ == '__main__':
    app = create_app()
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5001))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() in ('true', '1', 't')
    
    logger.info(f"Starting server on {host}:{port} (debug={debug})")
    app.run(debug=debug, host=host, port=port)
