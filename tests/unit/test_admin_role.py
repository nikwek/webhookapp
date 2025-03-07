import pytest
import secrets
from flask_security import hash_password
from flask_security.utils import verify_password
from app.models.user import User, Role
from app import db

@pytest.fixture
def admin_role(app):
    """Create admin role"""
    with app.app_context():
        role = Role.query.filter_by(name='admin').first()
        if not role:
            role = Role(name='admin', description='Administrator')
            db.session.add(role)
            db.session.commit()
        return role

@pytest.fixture
def admin_user(app, admin_role):
    """Create admin user"""
    with app.app_context():
        admin = User.query.filter_by(email='admin@example.com').first()
        if not admin:
            admin = User(
                email='admin@example.com',
                username='admin',
                fs_uniquifier=secrets.token_hex(16),
                password=hash_password('adminpass'),
                active=True
            )
            admin.roles.append(admin_role)
            db.session.add(admin)
            db.session.commit()
        else:
            # Make sure existing admin has the admin role
            if admin_role not in admin.roles:
                admin.roles.append(admin_role)
                db.session.commit()
        return admin

def test_admin_access(client, admin_user, app):
    """Test admin route access"""
    with app.app_context():
        # Refresh admin user in session
        admin = User.query.get(admin_user.id)
        
        # Set session variables before login
        with client.session_transaction() as session:
            session['user_id'] = admin.id
            session['_fresh'] = True
            session['fs_uniquifier'] = admin.fs_uniquifier

        # Login
        response = client.post('/login', data={
            'email': 'admin@example.com',
            'password': 'adminpass'
        }, follow_redirects=True)
        assert response.status_code == 200
        
        # Print session info for debugging
        with client.session_transaction() as session:
            print("Session after login:", dict(session))

        # Test admin routes
        admin_routes = [
            '/admin/users',
            '/admin/automations',
            '/admin/settings'
        ]
        for route in admin_routes:
            response = client.get(route)
            print(f"Testing route {route}: {response.status_code}")
            if response.status_code != 200:
                print(f"Response data: {response.data.decode()}")
            assert response.status_code == 200

