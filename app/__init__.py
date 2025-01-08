# app/__init__.py
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

    from app.routes import auth, webhook, dashboard
    app.register_blueprint(auth.bp)
    app.register_blueprint(webhook.bp)
    app.register_blueprint(dashboard.bp)

    # Add template filter
    from json import loads
    @app.template_filter('from_json')
    def from_json(value):
        return loads(value)
    
    with app.app_context():
        db.create_all()
        # Create admin if doesn't exist
        from app.models.user import User
        if not User.query.filter_by(username='admin').first():
            admin_user = User(
                username='admin',
                password=bcrypt.generate_password_hash('fahrvergnuegen').decode('utf-8'),
                is_admin=True
            )
            db.session.add(admin_user)
            db.session.commit()

    return app
