from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from config import Config
from flask_migrate import Migrate

db = SQLAlchemy()
bcrypt = Bcrypt()
migrate = Migrate()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    bcrypt.init_app(app)
    migrate.init_app(app, db)

    from app.routes import auth, webhook, dashboard, admin
    app.register_blueprint(auth.bp)
    app.register_blueprint(webhook.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(admin.bp)

    # Add template filter
    @app.template_filter('from_json')
    def from_json(value):
        import json
        return json.loads(value) if value else {}

    return app