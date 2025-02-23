# app/services/notification_service.py
from flask import current_app
from app.models.user import User
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_oauth_error_notification(user_id, error_message):
    """Send an email notification about OAuth errors"""
    user = User.query.get(user_id)
    if not user or not user.email:
        current_app.logger.error(f"Cannot send notification - no email for user {user_id}")
        return

    subject = "Action Required: Trading Bot OAuth Connection Issue"
    body = f"""
    Hello {user.username},

    There was an issue refreshing your Coinbase OAuth connection for your trading bot.
    This means your automations may not be able to execute trades until this is resolved.

    Error: {error_message}

    Please visit {current_app.config['APPLICATION_URL']}/settings to reconnect your Coinbase account.

    Best regards,
    Your Trading Bot Team
    """

    try:
        msg = MIMEMultipart()
        msg['From'] = current_app.config['MAIL_DEFAULT_SENDER']
        msg['To'] = user.email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(current_app.config['MAIL_SERVER'], current_app.config['MAIL_PORT'])
        if current_app.config['MAIL_USE_TLS']:
            server.starttls()
        if current_app.config['MAIL_USERNAME'] and current_app.config['MAIL_PASSWORD']:
            server.login(current_app.config['MAIL_USERNAME'], current_app.config['MAIL_PASSWORD'])
        
        server.send_message(msg)
        server.quit()
        
        current_app.logger.info(f"Sent OAuth error notification to user {user_id}")
    except Exception as e:
        current_app.logger.error(f"Failed to send OAuth error notification: {str(e)}")
        raise