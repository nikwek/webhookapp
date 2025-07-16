# app/__init__.py
"""Flask application factory and extension initialization.
Restored after accidental deletion so that `run.py` can import `create_app` again.
"""

from __future__ import annotations

import logging
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, flash, jsonify, render_template, request
from flask_apscheduler import APScheduler
from flask_caching import Cache
from flask_login import logout_user
from flask_mail import Mail
from flask_security import Security, SQLAlchemyUserDatastore, user_authenticated
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import inspect, text

from config import get_config
from app.forms.custom_login_form import CustomLoginForm
from app.forms.custom_2fa_form import Custom2FACodeForm
from flask_security.forms import RegisterFormV2

# ---------------------------------------------------------------------------
# Extension instances (singletons that will be imported elsewhere)
# ---------------------------------------------------------------------------

db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()
mail = Mail()
sess = Session()
cache = Cache()
security = Security()
scheduler = APScheduler()

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_app(test_config: dict | None = None):  # noqa: C901 complex
    """Application factory used by run.py and WSGI servers."""

    load_dotenv()

    app = Flask(__name__)
    app.jinja_env.add_extension("jinja2.ext.do")

    # Config
    if test_config is None:
        app.config.from_object(get_config())
    else:
        app.config.update(test_config)

    # Logging defaults
    app.logger.setLevel(logging.DEBUG if app.debug else logging.INFO)
    logging.getLogger("flask_security").setLevel(logging.INFO)

    # ---------------------------------------------------------------------
    # Extension init
    # ---------------------------------------------------------------------
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    mail.init_app(app)
    sess.init_app(app)

    # Cache – default to SimpleCache if none provided
    app.config.setdefault("CACHE_TYPE", "SimpleCache")
    app.config.setdefault("CACHE_DEFAULT_TIMEOUT", 300)
    cache.init_app(app)

    # Scheduler
    app.config.setdefault("SCHEDULER_API_ENABLED", False)
    scheduler.init_app(app)
    scheduler.start()

    # Register daily snapshot job (00:05 UTC)
    try:
        from app.services.strategy_value_service import snapshot_all_strategies

        scheduler.add_job(
            id="daily_strategy_snapshot",
            func=snapshot_all_strategies,
            trigger="cron",
            hour=0,
            minute=5,
            misfire_grace_time=3600,
        )
        app.logger.info("Scheduled daily_strategy_snapshot job via APScheduler.")
    except Exception as err:  # pragma: no cover
        app.logger.error("Failed to schedule snapshot job: %s", err, exc_info=True)

    # Rate limiter built in webhook routes
    from app.routes.webhook import limiter
    limiter.init_app(app)

    # ---------------------------------------------------------------------
    # Database bootstrap & security setup – inside app context
    # ---------------------------------------------------------------------
    with app.app_context():
        from app.models.user import User, Role  # avoid circular imports at top-level

        inspector = inspect(db.engine)
        if not inspector.has_table("users"):
            db.create_all()
            app.logger.info("Initial database tables created.")

        # Sanity query so we fail fast if DB unreachable
        db.session.execute(text("SELECT 1"))

        # Flask-Security
        user_datastore = SQLAlchemyUserDatastore(db, User, Role)
        security.init_app(
            app,
            user_datastore,
            register_form=RegisterFormV2,
            login_form=CustomLoginForm,
            two_factor_verify_code_form=Custom2FACodeForm,
            flash_messages=True,
        )

        # Block suspended users
        @user_authenticated.connect_via(app)  # pylint: disable=unused-variable
        def _block_suspended(app, user, **extra):  # noqa: ANN001
            if getattr(user, "is_suspended", False):
                logout_user()
                flash("Your account is suspended.", "error")
                return False

    # ---------------------------------------------------------------------
    # Blueprints
    # ---------------------------------------------------------------------
    from app.routes import bp as main_bp
    from app.routes.auth import bp as auth_bp
    from app.routes.dashboard import bp as dashboard_bp
    from app.routes.webhook import bp as webhook_bp
    from app.routes.exchange import exchange_bp
    from app.routes.two_factor import bp as two_factor_bp
    from app.routes.admin import bp as admin_bp
    from app.routes.debug import debug as debug_bp
    from app.routes.api import api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
    app.register_blueprint(webhook_bp)
    app.register_blueprint(exchange_bp)
    app.register_blueprint(two_factor_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(debug_bp)
    app.register_blueprint(api_bp)

    # ---------------------------------------------------------------------
    # Error handlers & health
    # ---------------------------------------------------------------------
    @app.errorhandler(404)
    def _404(e):  # noqa: D401
        if request.path.startswith("/api/"):
            return jsonify({"error": "Not Found", "message": str(e)}), 404
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def _500(e):  # noqa: D401
        logger.error("Unhandled 500: %s", e, exc_info=True)
        return jsonify({"error": "Internal Server Error"}), 500

    @app.route("/health")
    def _health():
        return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}, 200

    # ---------------------------------------------------------------------
    # Exchange adapters
    # ---------------------------------------------------------------------
    from app.exchanges.init_exchanges import initialize_exchange_adapters

    registered = initialize_exchange_adapters()
    app.logger.info("Initialized exchange adapters: %s", registered)

    return app
