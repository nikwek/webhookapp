# app/services/notification_service.py
from __future__ import annotations

from typing import Dict, List, Optional
from flask import current_app, render_template
from flask_mail import Message
from datetime import datetime

from app import db, mail
from app.models import User, Role, UserNotificationPreference

# Notification type constants
ADMIN_NEW_USER_SIGNUP = "ADMIN_NEW_USER_SIGNUP"
USER_TRANSACTION_ACTIVITY = "USER_TRANSACTION_ACTIVITY"

AVAILABLE_USER_NOTIFICATIONS: List[str] = [
    USER_TRANSACTION_ACTIVITY,
]

AVAILABLE_ADMIN_NOTIFICATIONS: List[str] = [
    ADMIN_NEW_USER_SIGNUP,
]


class NotificationService:
    @staticmethod
    def is_enabled(user_id: int, notif_type: str) -> bool:
        try:
            pref = UserNotificationPreference.query.filter_by(user_id=user_id, notif_type=notif_type).first()
            return bool(pref and pref.enabled)
        except Exception as e:  # Table may not exist yet during migration window
            current_app.logger.debug(f"Notification prefs check failed (likely before migration): {e}")
            return False

    @staticmethod
    def get_prefs_map(user_id: int) -> Dict[str, bool]:
        try:
            prefs = UserNotificationPreference.query.filter_by(user_id=user_id).all()
            return {p.notif_type: bool(p.enabled) for p in prefs}
        except Exception as e:
            current_app.logger.debug(f"Notification prefs fetch failed (likely before migration): {e}")
            return {}

    @staticmethod
    def save_preferences(user_id: int, enabled_types: List[str], scope: str = "user") -> None:
        """
        Save preferences for a user. 'scope' controls which types are writable (user|admin).
        Any types in the allowed list but not in enabled_types are set to disabled.
        """
        allowed = AVAILABLE_ADMIN_NOTIFICATIONS if scope == "admin" else AVAILABLE_USER_NOTIFICATIONS
        try:
            existing = {p.notif_type: p for p in UserNotificationPreference.query.filter_by(user_id=user_id).all()}
            for t in allowed:
                should_enable = t in enabled_types
                if t in existing:
                    existing[t].enabled = should_enable
                else:
                    db.session.add(UserNotificationPreference(user_id=user_id, notif_type=t, enabled=should_enable))
            db.session.commit()
        except Exception as e:
            current_app.logger.error(f"Failed to save notification preferences: {e}")
            db.session.rollback()

    # -----------------------
    # Sending helpers
    # -----------------------
    @staticmethod
    def send_admin_new_user_signup(new_user_email: str) -> None:
        # Find all admins who have opted in
        role = Role.query.filter_by(name="admin").first()
        if not role:
            return
        admins = role.users
        for admin in admins:
            if NotificationService.is_enabled(admin.id, ADMIN_NEW_USER_SIGNUP):
                subject = "Webhook App: New user sign-up"
                preheader = f"{new_user_email} just created an account"
                ctx = {
                    "new_user_email": new_user_email,
                    "current_year": datetime.utcnow().year,
                    "preheader": preheader,
                    "subject": subject,
                }
                NotificationService._send_email(
                    recipients=[admin.email],
                    subject=subject,
                    html_template="email/admin_new_user.html",
                    text_template="email/admin_new_user.txt",
                    context=ctx,
                )

    @staticmethod
    def send_user_transaction_activity(
        user: User,
        exchange_display_name: str,
        strategy_name: str,
        information: str,
        status: str,
        timestamp: Optional[str] = None,
        client_order_id: Optional[str] = None,
    ) -> None:
        if not NotificationService.is_enabled(user.id, USER_TRANSACTION_ACTIVITY):
            return
        # Extract action/pair from information for a sharper subject if possible
        subject_detail = information.upper()
        subject = f"Webhook App: {exchange_display_name} — {subject_detail} ({status})"
        preheader = f"{strategy_name}: {information}"
        ctx = {
            "exchange": exchange_display_name,
            "strategy_name": strategy_name,
            "information": information,
            "status": status,
            "timestamp": timestamp,
            "client_order_id": client_order_id,
            "current_year": datetime.utcnow().year,
            "preheader": preheader,
            "subject": subject,
        }
        NotificationService._send_email(
            recipients=[user.email],
            subject=subject,
            html_template="email/transaction_activity.html",
            text_template="email/transaction_activity.txt",
            context=ctx,
        )

    @staticmethod
    def _send_email(
        recipients: List[str],
        subject: str,
        body: Optional[str] = None,
        html_template: Optional[str] = None,
        text_template: Optional[str] = None,
        context: Optional[Dict] = None,
    ) -> None:
        try:
            msg = Message(subject=subject, recipients=recipients)
            if html_template or text_template:
                ctx = context or {}
                if text_template:
                    try:
                        msg.body = render_template(text_template, **ctx)
                    except Exception:
                        # Fallback to body or blank if template missing
                        msg.body = body or ""
                else:
                    msg.body = body or ""
                if html_template:
                    try:
                        msg.html = render_template(html_template, **ctx)
                    except Exception:
                        # If HTML fails, ensure we at least have plain text
                        if not msg.body:
                            msg.body = body or ""
            else:
                msg.body = body or ""
            mail.send(msg)
        except Exception as e:
            # Avoid crashing business flow on email failure; log and continue
            current_app.logger.error(f"Failed to send email '{subject}' to {recipients}: {e}")
