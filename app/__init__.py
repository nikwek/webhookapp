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

    # Create tables and admin user
    with app.app_context():
        # Import models so they're registered with SQLAlchemy
        from app.models.user import User
        from app.models.automation import Automation
        from app.models.webhook import WebhookLog
        
        # Create all tables
        db.create_all()
        
        # Create admin user if it doesn't exist
        if not User.query.filter_by(username='admin').first():
            admin_user = User(
                username='admin',
                password=bcrypt.generate_password_hash('fahrvergnuegen').decode('utf-8'),
                is_admin=True
            )
            db.session.add(admin_user)
            db.session.commit()

    return app