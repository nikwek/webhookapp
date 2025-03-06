import pytest
from flask_security import hash_password
from app.models.user import User, Role
from app import db

def test_login_success(client, regular_user):
    response = client.post('/login', data={
        'email': 'testuser@example.com',  # Updated to use email
        'password': 'password'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Dashboard' in response.data

def test_login_failure(client):
    response = client.post('/login', data={
        'email': 'wrong@example.com',
        'password': 'wrong'
    }, follow_redirects=True)
    assert b'Invalid email or password' in response.data

def test_register(client, app):
    with app.app_context():
        # Create default roles if they don't exist
        if not Role.query.filter_by(name='user').first():
            db.session.add(Role(name='user'))
            db.session.commit()
            
    response = client.post('/register', data={
        'email': 'newuser@example.com',
        'password': 'newpass',
        'password_confirm': 'newpass'  # Flask-Security requires confirmation
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Registration successful' in response.data

def test_register_duplicate_email(client, regular_user):
    response = client.post('/register', data={
        'email': 'testuser@example.com',  # Same as regular_user
        'password': 'password',
        'password_confirm': 'password'
    }, follow_redirects=True)
    assert b'Email address is already associated' in response.data

def test_protected_routes(client):
    protected_routes = [
        '/dashboard',
        '/settings',
        '/api/logs',
        '/api/coinbase/portfolios'
    ]
    for route in protected_routes:
        response = client.get(route)
        assert response.status_code == 302
        assert '/login' in response.location

def test_logout(auth_client):
    response = auth_client.get('/logout', follow_redirects=True)
    assert response.status_code == 200
    
    # Verify session is cleared
    with auth_client.session_transaction() as session:
        assert 'user_id' not in session
    
    # Verify protected routes are inaccessible
    response = auth_client.get('/dashboard')
    assert response.status_code == 302

@pytest.fixture
def regular_user(app):
    """Updated fixture for Flask-Security user"""
    with app.app_context():
        # Create user role if it doesn't exist
        user_role = Role.query.filter_by(name='user').first()
        if not user_role:
            user_role = Role(name='user')
            db.session.add(user_role)
            db.session.commit()
            
        user = User(
            email='testuser@example.com',
            password=hash_password('password'),
            active=True
        )
        user.roles.append(user_role)
        db.session.add(user)
        db.session.commit()
        return user
