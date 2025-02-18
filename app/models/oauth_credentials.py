from datetime import datetime
from app import db
from sqlalchemy.orm import relationship

class OAuthCredentials(db.Model):
    __tablename__ = 'oauth_credentials'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # Changed from 'user.id' to 'users.id'
    provider = db.Column(db.String(50), nullable=False)  # e.g., 'coinbase'
    access_token = db.Column(db.String(500), nullable=False)
    refresh_token = db.Column(db.String(500), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    scope = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="oauth_credentials")

    def is_expired(self):
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at

    def to_dict(self):
        return {
            'id': self.id,
            'provider': self.provider,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'scope': self.scope,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }
