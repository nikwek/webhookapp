import pytest
import secrets
from app import create_app, db
from app.models.user import User, Role
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from flask_security import hash_password
from app import db

@pytest.fixture
def app():
    app = create_app()
    app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test_key'
    })
    
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def auth_client(client, regular_user):
    with client.session_transaction() as session:
        session['user_id'] = regular_user.id
        session['_fresh'] = True
    client.environ_base['HTTP_AUTHORIZATION'] = f'Bearer test-token'
    return client

@pytest.fixture
def admin_client(client, admin_user):
    with client.session_transaction() as session:
        session['user_id'] = admin_user.id
        session['is_admin'] = True
        session['_fresh'] = True
    return client

@pytest.fixture
def regular_user(app):
    """Create a regular user for testing"""
    with app.app_context():
        user = User.query.filter_by(email='testuser@example.com').first()
        if not user:
            user = User(
                email='testuser@example.com',
                username='testuser',
                fs_uniquifier=secrets.token_hex(16),
                password=hash_password('password'),
                active=True
            )
            db.session.add(user)
            db.session.commit()
        return user

@pytest.fixture
def admin_user(app):
    return User.query.filter_by(username='admin').first()

@pytest.fixture
def automation(app, regular_user):
    automation = Automation(
        name='Test Automation',
        automation_id='test123',
        user_id=regular_user.id
    )
    db.session.add(automation)
    db.session.commit()
    return automation 