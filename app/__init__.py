# app/__init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_security import Security, SQLAlchemyUserDatastore
from flask_security.forms import RegisterFormV2
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail
from config import Config
import os
import logging
from datetime import datetime, timezone

# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
security = Security()
mail = Mail()

def create_app(test_config=None):
    app = Flask(__name__)
    
    if test_config is None:
        app.config.from_object(Config)
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

    with app.app_context():
        # Import models
        from app.models.user import User, Role
        from app.models.automation import Automation
        from app.models.webhook import WebhookLog
        from app.models.exchange_credentials import ExchangeCredentials
        from app.models.account_cache import AccountCache
        
        # Setup Flask-Security
        user_datastore = SQLAlchemyUserDatastore(db, User, Role)
        security.init_app(
            app,
            user_datastore,
            register_form=RegisterFormV2
        )

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
        from app.routes.auth_routes import bp as auth_routes_bp
        app.register_blueprint(auth_routes_bp)

        # Configure login redirect
        app.config.update(
            SECURITY_POST_LOGIN_VIEW='/login-redirect',
        )
        
        # Initialize database
        db.create_all()

    return app