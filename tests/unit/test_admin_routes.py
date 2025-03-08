# tests/unit/test_admin_routes.py
import pytest

@pytest.fixture
def mock_render_template(monkeypatch):
    """Mock render_template to avoid template errors"""
    def mock_render(*args, **kwargs):
        return "Mocked template"
    
    monkeypatch.setattr('app.routes.admin.render_template', mock_render)
    return mock_render

def test_admin_routes_access(admin_client, mock_render_template):
    """Test admin route access with routes isolated from templates"""
    admin_routes = [
        '/admin/users',
        '/admin/automations',
        '/admin/settings'
    ]
    
    for route in admin_routes:
        response = admin_client.get(route)
        assert response.status_code == 200