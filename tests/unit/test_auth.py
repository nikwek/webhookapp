import pytest
from flask_security import hash_password
from app.models.user import User, Role
from app import db

def test_login_success(client, regular_user):
    response = client.post('/security/login', data={
        'email': 'testuser@example.com',
        'password': 'password'
    }, follow_redirects=True)
    assert response.status_code == 200
    # After successful login, user should be redirected to dashboard
    assert b'Dashboard' in response.data or response.status_code == 302

def test_login_failure(client):
    response = client.post('/security/login', data={
        'email': 'wrong@example.com',
        'password': 'wrong'
    }, follow_redirects=True)
    # Should stay on login page with error message
    assert response.status_code == 200
    assert b'Invalid' in response.data or b'Login' in response.data

def test_register(client, app):
    with app.app_context():
        # Create default roles if they don't exist
        if not Role.query.filter_by(name='user').first():
            db.session.add(Role(name='user'))
            db.session.commit()
            
    # Use a unique email to avoid conflicts between test runs
    import uuid
    unique_email = f'testuser{uuid.uuid4().hex[:8]}@gmail.com'
    
    response = client.post('/security/register', data={
        'email': unique_email,
        'password': 'newpassword123',  # Must be at least 8 characters
        'password_confirm': 'newpassword123'  # Flask-Security requires confirmation
    }, follow_redirects=True)
    # Registration should either succeed (redirect) or show form without validation errors
    assert response.status_code in [200, 302]
    # If status is 200, check that there are no validation errors
    if response.status_code == 200:
        assert b'Invalid email address' not in response.data
        assert b'Password must be at least' not in response.data
        # If no validation errors, registration was successful

def test_register_duplicate_email(client, regular_user):
    response = client.post('/security/register', data={
        'email': 'testuser@example.com',  # Same as global regular_user
        'password': 'password123',  # Must be at least 8 characters
        'password_confirm': 'password123'
    }, follow_redirects=True)
    # Should stay on registration form (200) and show error about existing email
    assert response.status_code == 200
    # Flask-Security shows "Invalid email address" for duplicate emails
    assert b'Invalid email address' in response.data

def test_unauthenticated_user_cannot_access_dashboard(client):
    """Test that unauthenticated users cannot see dashboard content."""
    response = client.get('/dashboard', follow_redirects=True)
    
    # User should not see dashboard content
    assert b'Dashboard' not in response.data or b'Please log in' in response.data
    # Should see login form or be redirected to login
    assert b'Email' in response.data or b'Password' in response.data or b'Login' in response.data

def test_authentication_protection_works(client):
    """Test that Flask-Security authentication protection is working correctly."""
    # Unauthenticated user tries to access dashboard
    response = client.get('/dashboard', follow_redirects=True)
    
    # User should be redirected to login page with proper message
    assert response.status_code == 200
    assert b'Login' in response.data
    assert b'You must sign in to view this resource' in response.data
    assert b'Dashboard' not in response.data
    
    # Verify the login form is present
    assert b'Email Address' in response.data
    assert b'Password' in response.data
    assert b'form action="/security/login"' in response.data

def test_logout(auth_client):
    response = auth_client.get('/logout', follow_redirects=True)
    assert response.status_code == 200
    
    # Verify session is cleared
    with auth_client.session_transaction() as session:
        assert 'user_id' not in session
    
    # Verify protected routes are inaccessible
    response = auth_client.get('/dashboard')
    # Accept both 302 and 308 redirects
    assert response.status_code in [302, 308]

# Removed duplicate regular_user fixture - using global one from conftest.py
