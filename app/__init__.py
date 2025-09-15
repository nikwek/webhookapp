# app/__init__.py
"""Flask application factory and extension initialization.
Restored after accidental deletion so that `run.py` can import `create_app` again.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

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
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from config import get_config
from app.forms.custom_login_form import CustomLoginForm
from app.forms.custom_2fa_form import Custom2FACodeForm
from app.forms.custom_register_form import CustomRegisterForm

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

    # Load environment variables - try multiple paths for dev/prod compatibility
    import os
    load_dotenv()  # Development (current directory)
    
    # Production explicit path for environment variables
    prod_env_path = '/home/nik/webhookapp/.env'
    if os.path.exists(prod_env_path):
        load_dotenv(prod_env_path, override=True)

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
    # APScheduler – enable admin API for easier debugging and set sane defaults
    app.config.setdefault("SCHEDULER_API_ENABLED", False)
    app.config.setdefault("SCHEDULER_JOB_DEFAULTS", {
        "misfire_grace_time": 86_400,  # 24 h tolerance
        "coalesce": True,
        "max_instances": 1
    })

    scheduler.init_app(app)

    # ---------------------------------------------------------------------
    # Log job outcomes so that failures never go unnoticed
    # ---------------------------------------------------------------------

    def _log_scheduler_event(job_event):  # noqa: ANN001
        """Write a concise log line for every APScheduler job completion/error."""
        if getattr(job_event, "exception", False):
            app.logger.error("Scheduler job %s failed: %s", job_event.job_id, job_event.exception, exc_info=True)
        else:
            app.logger.info("Scheduler job %s executed successfully.", job_event.job_id)

    scheduler.add_listener(_log_scheduler_event, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    scheduler.start()

    # Register daily snapshot job (00:05 UTC)
    # Only register jobs once to avoid conflicts in multi-worker setup
    # Use process ID check as a simpler approach
    import os

    # Get the current process ID and check if it's the "first" worker
    current_pid = os.getpid()
    app.logger.info(f"Worker PID {current_pid} attempting scheduler registration...")

    # Use a simple approach: only register if no job already exists
    existing_job = scheduler.get_job("daily_strategy_snapshot")
    should_register_job = existing_job is None

    if should_register_job:
        app.logger.info(f"Worker PID {current_pid} will register scheduler job (no existing job found).")
    else:
        app.logger.info(f"Worker PID {current_pid} skipping registration (job already exists).")

    if should_register_job:
        try:
            from app.services.strategy_value_service import snapshot_all_strategies

            # Create a wrapper function that provides Flask application context
            def scheduled_snapshot_with_context():
                with app.app_context():
                    try:
                        snapshot_all_strategies(source="scheduled_daily")
                    except Exception as exc:
                        app.logger.error(f"Daily strategy snapshot failed: {exc}", exc_info=True)
                        # Schedule a retry in 5 minutes
                        try:
                            scheduler.add_job(
                                id="daily_strategy_snapshot_retry",
                                func=scheduled_snapshot_retry,
                                trigger="date",
                                run_date=datetime.now() + timedelta(minutes=5),
                                replace_existing=True,
                                misfire_grace_time=3600,  # 1 hour grace period
                            )
                            app.logger.info("Scheduled retry for daily strategy snapshot in 5 minutes")
                        except Exception as retry_exc:
                            app.logger.error(f"Failed to schedule retry: {retry_exc}")
                        raise  # Re-raise so the failure is logged
            
            # Retry function with limited attempts
            def scheduled_snapshot_retry():
                with app.app_context():
                    try:
                        app.logger.info("Executing retry for daily strategy snapshot")
                        snapshot_all_strategies(source="scheduled_daily_retry")
                        app.logger.info("Retry successful")
                    except Exception as exc:
                        app.logger.error(f"Daily strategy snapshot retry failed: {exc}", exc_info=True)
                        # Don't schedule another retry to avoid infinite loops
                        raise

            # Check if job already exists to avoid duplicate registration
            existing_job = scheduler.get_job("daily_strategy_snapshot")
            if not existing_job:
                scheduler.add_job(
                    id="daily_strategy_snapshot",
                    func=scheduled_snapshot_with_context,
                    trigger="cron",
                    hour=0,
                    minute=5,
                    misfire_grace_time=86_400,  # retry for up to 24 h
                )
                app.logger.info("Scheduled daily_strategy_snapshot job via APScheduler.")
            else:
                app.logger.info("Daily snapshot job already exists, skipping registration.")
        except Exception as err:  # pragma: no cover
            app.logger.error(f"Worker PID {current_pid} failed to schedule snapshot job: %s", err, exc_info=True)

    # Rate limiter built in webhook routes
    from app.routes.webhook import limiter
    limiter.init_app(app)
    
    # reCAPTCHA is handled directly in our custom form validation
    # No need to initialize Flask-ReCaptcha extension

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

        # -----------------------------------------------------------------
        # Ensure we never miss a daily snapshot – if the last snapshot in the
        # DB is older than today, trigger one immediately on startup.
        # -----------------------------------------------------------------
        try:
            from datetime import date
            from sqlalchemy import func
            from app.models.trading import StrategyValueHistory

            last = db.session.query(func.max(StrategyValueHistory.timestamp)).scalar()
            if not last or last.date() < date.today():
                app.logger.info("No strategy snapshot for today – running catch-up …")
                # Use the imported function from the scheduler section above
                with app.app_context():
                    snapshot_all_strategies(source="startup_catchup")
        except Exception as _err:  # pragma: no cover
            app.logger.error("Failed catch-up snapshot: %s", _err, exc_info=True)

        # Flask-Security
        user_datastore = SQLAlchemyUserDatastore(db, User, Role)
        security.init_app(
            app,
            user_datastore,
            register_form=CustomRegisterForm,
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
    from app.routes.template_debug import template_debug
    from app.routes.api import api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
    app.register_blueprint(webhook_bp)
    app.register_blueprint(exchange_bp)
    app.register_blueprint(two_factor_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(debug_bp)
    app.register_blueprint(template_debug)
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
