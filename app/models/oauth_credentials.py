from datetime import datetime, timedelta
from app import db
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
from app.utils.encryption import encrypt_value, decrypt_value  # We'll create this

class OAuthCredentials(db.Model):
    __tablename__ = 'oauth_credentials'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    provider = db.Column(db.String(50), nullable=False)
    _access_token = db.Column('access_token', db.LargeBinary, nullable=False)
    _refresh_token = db.Column('refresh_token', db.LargeBinary, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    scope = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_refresh_attempt = db.Column(db.DateTime, nullable=True)
    refresh_error = db.Column(db.String(500), nullable=True)
    is_valid = db.Column(db.Boolean, default=True)

    # Relationships
    user = relationship("User", back_populates="oauth_credentials")

    @hybrid_property
    def access_token(self):
        if self._access_token:
            return decrypt_value(self._access_token)
        return None

    @access_token.setter
    def access_token(self, value):
        if value:
            self._access_token = encrypt_value(value)
        else:
            self._access_token = None

    @hybrid_property
    def refresh_token(self):
        if self._refresh_token:
            return decrypt_value(self._refresh_token)
        return None

    @refresh_token.setter
    def refresh_token(self, value):
        if value:
            self._refresh_token = encrypt_value(value)
        else:
            self._refresh_token = None

    def is_expired(self):
        """Check if the access token is expired or about to expire"""
        if not self.expires_at:
            return False
        # Consider tokens expiring in the next 5 minutes as expired
        buffer_time = datetime.utcnow() + timedelta(minutes=5)
        return buffer_time > self.expires_at

    def needs_refresh(self):
        """Check if the token needs to be refreshed"""
        return self.is_valid and self.is_expired() and self.refresh_token is not None

    def mark_refresh_attempt(self, error=None):
        """Record a refresh attempt and any error"""
        self.last_refresh_attempt = datetime.utcnow()
        self.refresh_error = error
        if error:
            self.is_valid = False

    def to_dict(self):
        return {
            'id': self.id,
            'provider': self.provider,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'scope': self.scope,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'is_valid': self.is_valid,
            'last_refresh_attempt': self.last_refresh_attempt.isoformat() if self.last_refresh_attempt else None,
            'refresh_error': self.refresh_error
        }
