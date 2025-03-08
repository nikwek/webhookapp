import pytest
from app.models.user import User, Role
from app import db

def test_admin_access(admin_client, app):
    """Test admin route access with admin_client fixture"""
    admin_routes = [
        '/admin/users',
        '/admin/automations',
        '/admin/settings'
    ]
    
    for route in admin_routes:
        print(f"Testing route {route}")
        response = admin_client.get(route)
        if response.status_code != 200:
            print(f"Response content: {response.data.decode('utf-8')}")
        assert response.status_code == 200, f"Failed to access {route}, got {response.status_code}"

def test_admin_user_has_admin_role(app, admin_user):
    """Test admin user has admin role"""
    with app.app_context():
        # Get fresh user to avoid any detached object issues
        admin = User.query.filter_by(id=admin_user.id).first()
        
        # Check if user has admin role
        admin_role = Role.query.filter_by(name='admin').first()
        assert admin_role in admin.roles, "Admin user is missing admin role"

def test_regular_user_cannot_access_admin(auth_client):
    """Test regular user cannot access admin routes"""
    admin_routes = [
        '/admin/users',
        '/admin/automations',
        '/admin/settings'
    ]
    for route in admin_routes:
        response = auth_client.get(route)
        assert response.status_code in [302, 403, 404], f"Regular user shouldn't access {route}, got {response.status_code}"