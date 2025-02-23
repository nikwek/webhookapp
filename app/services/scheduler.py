# app/services/scheduler.py
from flask_apscheduler import APScheduler
from flask import current_app
from app.models.oauth_credentials import OAuthCredentials
from app.models.automation import Automation
from app.services.oauth_service import refresh_access_token
from datetime import datetime, timedelta
from sqlalchemy import and_

scheduler = APScheduler()

def init_scheduler(app, db):
    """Initialize the scheduler with the app"""
    scheduler.init_app(app)
    scheduler.start()

    # Add jobs
    with app.app_context():
        # Check tokens every 30 minutes
        scheduler.add_job(
            id='check_oauth_tokens',
            func=check_oauth_tokens,
            trigger='interval',
            minutes=30,
            args=[app, db]
        )

def check_oauth_tokens(app, db):
    """Check and refresh OAuth tokens that are about to expire"""
    with app.app_context():
        current_app.logger.info("Starting OAuth token check")
        
        # Get all credentials for active automations that need refresh
        active_automations = db.session.query(Automation.user_id)\
            .filter(Automation.is_active == True)\
            .distinct()\
            .all()
        
        user_ids = [a[0] for a in active_automations]
        
        # Find credentials that will expire in the next hour
        expiry_threshold = datetime.utcnow() + timedelta(hours=1)
        credentials = OAuthCredentials.query.filter(
            and_(
                OAuthCredentials.user_id.in_(user_ids),
                OAuthCredentials.expires_at <= expiry_threshold,
                OAuthCredentials.is_valid == True
            )
        ).all()

        for cred in credentials:
            try:
                current_app.logger.info(f"Refreshing token for user {cred.user_id}")
                refresh_access_token(db, cred)
                
            except Exception as e:
                current_app.logger.error(f"Failed to refresh token for user {cred.user_id}: {str(e)}")
                
                # Send notification if configured
                if hasattr(app.config, 'ENABLE_EMAIL_NOTIFICATIONS') and app.config.ENABLE_EMAIL_NOTIFICATIONS:
                    try:
                        from app.services.notification_service import send_oauth_error_notification
                        send_oauth_error_notification(cred.user_id, str(e))
                    except Exception as notify_error:
                        current_app.logger.error(f"Failed to send notification: {str(notify_error)}")

        current_app.logger.info("Completed OAuth token check")