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
from flask import Flask, render_template, send_from_directory, jsonify, request, session
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
        MAX_CONTENT_LENGTH=int(os.environ.get('MAX_CONTENT_LENGTH', 64 * 1024)),
        DEVICES_FILE=os.environ.get('DEVICES_FILE', 'devices.yaml'),
        # Security settings
        SESSION_COOKIE_SECURE=os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() in ('true', '1', 't'),
        SESSION_COOKIE_HTTPONLY=os.environ.get('SESSION_COOKIE_HTTPONLY', 'true').lower() in ('true', '1', 't'),
        SESSION_COOKIE_SAMESITE='Strict',
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

    # Access control for the REST API (fail-closed). Every /api/* request must
    # come from either the bundled same-origin UI (signed, HttpOnly,
    # SameSite=Strict session cookie set on GET /) or a programmatic client
    # presenting a valid X-API-Key. Requests with neither are rejected (401).
    api_key = os.environ.get('API_KEY', '').strip()

    @app.before_request
    def _require_api_auth():
        if not request.path.startswith('/api/'):
            return None
        # 1) Browser UI: signed session cookie (SameSite=Strict → CSRF-safe).
        if session.get('ui_authenticated'):
            return None
        # 2) Programmatic client: constant-time X-API-Key comparison.
        if api_key:
            provided = request.headers.get('X-API-Key', '')
            if hmac.compare_digest(provided.encode('utf-8'), api_key.encode('utf-8')):
                return None
        return jsonify({'error': 'Unauthorized'}), 401

    if api_key:
        logger.info("API auth: UI session cookie or X-API-Key required for /api/*")
    else:
        logger.info(
            "API auth: UI session cookie required for /api/* "
            "(set API_KEY to also allow programmatic X-API-Key clients)"
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
        """Serve the main application page and establish a UI session."""
        # Mark this browser as an authenticated UI client. The cookie is signed
        # (SECRET_KEY), HttpOnly and SameSite=Strict, so JavaScript cannot read
        # it and a cross-site request will not send it (CSRF-safe).
        session['ui_authenticated'] = True
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
    
    # Baseline security headers (defense-in-depth). A strict CSP is intentionally
    # deferred until the CDN assets are self-hosted, since Alpine relies on
    # inline expressions/handlers that a strict policy would break.
    @app.after_request
    def _security_headers(response):
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('Referrer-Policy', 'no-referrer')
        return response

    return app

if __name__ == '__main__':
    app = create_app()
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5001))
    debug = os.environ.get('FLASK_DEBUG', 'false').lower() in ('true', '1', 't')
    
    logger.info(f"Starting server on {host}:{port} (debug={debug})")
    app.run(debug=debug, host=host, port=port)
