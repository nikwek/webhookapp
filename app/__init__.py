# app/__init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from config import Config
from flask_wtf.csrf import CSRFProtect
import os
import logging


# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
bcrypt = Bcrypt()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
csrf = CSRFProtect()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Configure logging
    if not app.debug:
        # Set the logging level to INFO
        logging.basicConfig(level=logging.INFO)

    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Initialize Flask extensions
    db.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Register Jinja2 filters
    app.jinja_env.filters['from_json'] = from_json_filter

    with app.app_context():
        # Import models (after db initialization)
        from app.models.user import User
        from app.models.automation import Automation
        from app.models.webhook import WebhookLog
        from app.models.exchange_credentials import ExchangeCredentials

        # Register blueprints
        from app.routes import auth, dashboard, webhook, admin, automation, coinbase
        app.register_blueprint(auth.bp)
        app.register_blueprint(dashboard.bp)
        app.register_blueprint(webhook.bp)
        app.register_blueprint(admin.bp)
        app.register_blueprint(automation.bp)
        app.register_blueprint(coinbase.bp)

        # Initialize database
        db.create_all()
        
        # Create admin user if needed
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            admin_user = User(
                username='admin',
                is_admin=True,
                require_password_change=True
            )
            admin_user.set_password('admin')
            db.session.add(admin_user)
            db.session.commit()

    return app

@login_manager.user_loader
def load_user(id):
    from app.models.user import User
    return User.query.get(int(id))

def from_json_filter(value):
    """Convert a JSON string to a Python object."""
    import json
    try:
        return json.loads(value)
    except:
        return value