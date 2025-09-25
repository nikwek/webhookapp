# app/models/notification.py
from datetime import datetime, timezone
from app import db


class UserNotificationPreference(db.Model):
    __tablename__ = 'user_notification_preferences'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    notif_type = db.Column(db.String(64), nullable=False)
    enabled = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Unique index so a user has at most one row per notification type
    __table_args__ = (
        db.UniqueConstraint('user_id', 'notif_type', name='uq_user_notif_type'),
    )
