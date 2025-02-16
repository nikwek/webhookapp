# app/__init__.py
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from config import Config
import os


# Initialize extensions
db = SQLAlchemy()
migrate = Migrate()
bcrypt = Bcrypt()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'

# Import models here
from app.models.user import User
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from app.models.exchange_credentials import ExchangeCredentials

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

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

    # Register Jinja2 filters
    app.jinja_env.filters['from_json'] = from_json_filter

    with app.app_context():
        # Register blueprints
        from app.routes import auth, dashboard, webhook, admin, automation
        app.register_blueprint(auth.bp)
        app.register_blueprint(dashboard.bp)
        app.register_blueprint(webhook.bp)
        app.register_blueprint(admin.bp)
        app.register_blueprint(automation.bp)

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