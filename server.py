#!/usr/bin/env python3
"""
Tasmota Updater Web Application

A web interface for managing and updating Tasmota devices.
"""
import os
import hmac
import logging
import secrets
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, render_template, send_from_directory, jsonify, request
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
    
    # Resolve a secret key without a weak static fallback in production.
    # In debug we keep the convenient 'dev' key; otherwise, when SECRET_KEY
    # is unset we generate an ephemeral random key and warn loudly rather
    # than silently signing sessions with a publicly known value.
    secret_key = os.environ.get('SECRET_KEY')
    flask_debug = os.environ.get('FLASK_DEBUG', 'false').lower() in ('true', '1', 't')
    if not secret_key:
        if flask_debug:
            secret_key = 'dev'
        else:
            secret_key = secrets.token_hex(32)
            logger.warning(
                "SECRET_KEY is not set; generated an ephemeral random key. "
                "Sessions will not persist across restarts or across workers. "
                "Set SECRET_KEY in the environment for production deployments."
            )

    # Load default configuration
    app.config.from_mapping(
        SECRET_KEY=secret_key,
        DEVICES_FILE=os.environ.get('DEVICES_FILE', 'devices.yaml'),
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
    logger.info(f"Using devices file: {app.config['DEVICES_FILE']}")

    # Enable CORS
    # Enable CORS with an explicit, configurable allowlist.
    # Secure default: no cross-origin access (the bundled UI is same-origin).
    # Set CORS_ORIGINS to a comma-separated list of origins, or CORS_ORIGINS=*
    # to restore fully permissive behaviour.
    cors_origins_raw = os.environ.get('CORS_ORIGINS', '').strip()
    if cors_origins_raw:
        cors_origins = [o.strip() for o in cors_origins_raw.split(',') if o.strip()]
        CORS(app, resources={r"/api/*": {"origins": cors_origins}})
        logger.info(f"CORS enabled for /api/* origins: {cors_origins}")
    else:
        logger.info(
            "CORS restricted to same-origin requests "
            "(set CORS_ORIGINS to allow cross-origin API clients)"
        )

    # Optional API-key authentication for the REST API. When API_KEY is set,
    # every /api/* request must present a matching X-API-Key header.
    api_key = os.environ.get('API_KEY', '').strip()
    if api_key:
        @app.before_request
        def _require_api_key():
            if request.path.startswith('/api/'):
                provided = request.headers.get('X-API-Key', '')
                if not hmac.compare_digest(provided, api_key):
                    return jsonify({'error': 'Unauthorized'}), 401
        logger.info("API key authentication enabled for /api/* endpoints")
    else:
        logger.warning(
            "API_KEY is not set; the REST API is unauthenticated. "
            "Set API_KEY to require an X-API-Key header for /api/* requests."
        )
    
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
