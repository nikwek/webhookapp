# app/__init__.py
# Update this import at the top of the file:
from flask import Flask, flash, jsonify, render_template, request
from flask_security import user_authenticated, Security, SQLAlchemyUserDatastore
from flask_security.forms import RegisterFormV2, LoginForm
from flask_login import logout_user
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text 
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail
from flask_session import Session
from config import get_config
import os
import logging
from datetime import datetime, timezone
from app.forms.custom_login_form import CustomLoginForm


# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
security = Security()
mail = Mail()
sess = Session()


# Check if account is suspended 
def check_if_account_is_suspended(app, user, **kwargs):
    logger = logging.getLogger(__name__)
    
    logger.info(f"Checking if user {user.email} is suspended: {user.is_suspended}")
    
    if user and hasattr(user, 'is_suspended') and user.is_suspended:
        logger.warning(f"Blocking login attempt for suspended user: {user.email}")
        flash("Your account has been suspended. Please contact support for assistance.", "error")
        return False
    return True

def create_app(test_config=None):
    app = Flask(__name__)

    logging.getLogger('flask_security').setLevel(logging.DEBUG)  # debugging flash messages

    if test_config is None:
        app.config.from_object(get_config())
    else:
        app.config.update(test_config)

    # Configure logging
    app.logger.setLevel(logging.DEBUG)
    if not app.debug:
        logging.basicConfig(level=logging.INFO)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    mail.init_app(app)
    sess.init_app(app)

    with app.app_context():
        try:
            # Import models
            from app.models.user import User, Role
            from app.models.automation import Automation
            from app.models.webhook import WebhookLog
            from app.models.exchange_credentials import ExchangeCredentials
            from app.models.account_cache import AccountCache
            
            # Check if database needs to be created using inspect
            inspector = inspect(db.engine)
            if not inspector.has_table('users'):
                app.logger.info("Creating database tables...")
                db.create_all()
                app.logger.info("Database tables created successfully")
            
            # Verify critical tables exist using text()
            db.session.execute(text('SELECT 1 FROM users'))
            db.session.execute(text('SELECT 1 FROM roles'))
            
        except Exception as e:
            app.logger.error(f"Database initialization error: {e}")
            app.logger.info("Attempting to recreate database tables...")
            db.create_all()
            
        # Setup Flask-Security
        app.config['SECURITY_FLASH_MESSAGES'] = True
        user_datastore = SQLAlchemyUserDatastore(db, User, Role)
        security.init_app(
            app,
            user_datastore,
            register_form=RegisterFormV2,
            login_form=CustomLoginForm,
            flash_messages=True
        )

        # Configure login redirect
        app.config.update(
            SECURITY_POST_LOGIN_VIEW='/login-redirect',
            SECURITY_POST_REGISTER_VIEW='/dashboard',
        )

        @user_authenticated.connect_via(app)
        def _on_user_authenticated(app, user, **extra):
            app.logger.info(f"Auth signal: Checking if user {user.email} is suspended")
            
            if user and hasattr(user, 'is_suspended') and user.is_suspended:
                app.logger.warning(f"Auth signal: Blocking suspended user: {user.email}")
                flash("Your account has been suspended. Please contact support for assistance.", "error")
                # Force logout
                logout_user()
                # Return False to indicate authentication failure
                return False

        # Register blueprints
        from app.routes import dashboard, webhook, admin, automation
        app.register_blueprint(dashboard.bp)
        app.register_blueprint(webhook.bp)
        app.register_blueprint(admin.bp)
        app.register_blueprint(automation.bp)
        
        # Register coinbase blueprint
        from app.routes.coinbase import bp as coinbase_bp
        app.register_blueprint(coinbase_bp)
        
        # Import debug blueprint here (after app is created) to avoid circular imports
        from app.routes.debug import debug as debug_blueprint
        app.register_blueprint(debug_blueprint)
        
        # Register auth routes blueprint
        from app.routes.auth import bp as auth_bp
        app.register_blueprint(auth_bp)

        # Register error handlers
        @app.errorhandler(404)
        def page_not_found(e):
            # Check if it's an API request or a browser request
            if request.path.startswith('/api/') or request.headers.get('Content-Type') == 'application/json':
                # API request - return JSON
                return jsonify({
                    "error": "Not Found",
                    "message": str(e)
                }), 404
            else:
                # Browser request - render template
                return render_template('404.html'), 404

        @app.errorhandler(500)
        def internal_server_error(e):
            # Log the error
            logger.error(f"Internal server error: {str(e)}", exc_info=True)
            return jsonify({
                'error': 'An internal server error occurred',
                'status_code': 500
            }), 500

        @app.errorhandler(429)
        def too_many_requests(e):
            return jsonify({
                'error': 'Rate limit exceeded',
                'status_code': 429,
                'retry_after': e.description.get('retry_after', 60)
            }), 429

        @app.errorhandler(Exception)
        def handle_unhandled_exception(e):
            # Only trigger in production
            if not app.debug:
                logger.error(f"Unhandled exception: {str(e)}", exc_info=True)
                return jsonify({
                    'error': 'An unexpected error occurred',
                    'status_code': 500
                }), 500
            # In debug mode, let the default handlers deal with it
            raise e

        # Initialize database
        db.create_all()

        # Configure SSL for the app if enabled
        if app.config.get('SSL_ENABLED', False) or os.environ.get('GUNICORN_SSL', False):
            app.config['SESSION_COOKIE_SECURE'] = True
            app.logger.info(f"SSL enabled with cert: {app.config.get('SSL_CERT')}")
        else:
            app.logger.info("Running without SSL")

        # Initialize Health Check System
        from app.utils.health_check import HealthCheck

        health_check = HealthCheck.get_instance()
        health_check.start(app)

        # Register a shutdown function to clean up
        @app.teardown_appcontext
        def shutdown_health_check(exception=None):
            health_check.shutdown()

        # Add health check endpoint
        @app.route('/health')
        def health_check_endpoint():
            system_health = health_check.get_system_health()
            service_statuses = {
                name: info['status'] 
                for name, info in health_check.services.items()
            }
            
            status_code = 200
            if system_health == HealthCheck.STATUS_DEGRADED:
                status_code = 429  # Too Many Requests
            elif system_health == HealthCheck.STATUS_UNHEALTHY:
                status_code = 503  # Service Unavailable
            
            return jsonify({
                'status': system_health,
                'services': service_statuses,
                'timestamp': datetime.now().isoformat()
            }), status_code

    return app