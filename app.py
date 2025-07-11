#!/usr/bin/env python3
"""
Tasmota Updater Web Application

A web interface for managing and updating Tasmota devices.
"""
import os
from flask import Flask, render_template, send_from_directory
from flask_cors import CORS
from flasgger import Swagger
from app.tasmota.api import init_api

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
        SWAGGER={
            'title': 'Tasmota Updater API',
            'description': 'API for managing and updating Tasmota devices',
            'version': '1.0.0',
            'uiversion': 3,
        }
    )

    # Enable CORS
    CORS(app)
    
    # Initialize Swagger
    Swagger(app)
    
    # Initialize API routes
    init_api(app)
    
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
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5001)
