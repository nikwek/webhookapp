# app/app.py
from app.services.oauth_service import init_oauth

def create_app(test_config=None):
    app = Flask(__name__)

    # Initializations
    init_oauth(app)

    # Register blueprints
    from app.routes import auth, dashboard, webhook, admin, automation
    app.register_blueprint(auth.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(webhook.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(automation.bp)

    return app
