# app/models/user.py
from flask_security import UserMixin, RoleMixin
from flask_security.datastore import AsaList
from sqlalchemy.ext.mutable import MutableList
from app import db
from datetime import datetime, timezone

# Define the association table for users and roles
roles_users = db.Table('roles_users',
    db.Column('user_id', db.Integer(), db.ForeignKey('users.id')),
    db.Column('role_id', db.Integer(), db.ForeignKey('roles.id'))
)

class Role(db.Model, RoleMixin):
    __tablename__ = 'roles'
    id = db.Column(db.Integer(), primary_key=True)
    name = db.Column(db.String(80), unique=True)
    description = db.Column(db.String(255))

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True)
    username = db.Column(db.String(255), unique=True, nullable=True)
    password = db.Column(db.String(255), nullable=False)
    active = db.Column(db.Boolean())
    confirmed_at = db.Column(db.DateTime())
    fs_uniquifier = db.Column(db.String(255), unique=True)
    is_admin = db.Column(db.Boolean, default=False)
    require_password_change = db.Column(db.Boolean, default=False)
    is_suspended = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_activity = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Preferred display timezone (IANA tz string, e.g. "America/Los_Angeles")
    timezone = db.Column(db.String(64), nullable=True)
    
    # Two-Factor Authentication fields (match existing DB columns)
    tf_primary_method = db.Column(db.String(64))
    tf_totp_secret = db.Column(db.String(255))
    tf_phone_number = db.Column(db.String(128))
    tf_recovery_codes = db.Column(db.Text)
    # Flask-Security managed recovery codes (hashed list)
    mf_recovery_codes = db.Column(MutableList.as_mutable(AsaList()), nullable=True)

    roles = db.relationship('Role', secondary=roles_users,
                          backref=db.backref('users', lazy='dynamic'))
