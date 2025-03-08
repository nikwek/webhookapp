# tests/unit/test_templates.py
import pytest
from jinja2 import Environment, FileSystemLoader
import os

@pytest.fixture
def jinja_env(app):
    """Create a Jinja environment for testing templates directly"""
    template_dir = os.path.join(os.path.dirname(app.root_path), 'app', 'templates')
    return Environment(loader=FileSystemLoader(template_dir))

def test_admin_base_template(jinja_env):
    """Test that admin base template compiles without errors"""
    template = jinja_env.get_template('admin/base.html')
    
    # Test rendering with minimal context
    rendered = template.render(
        current_user=MagicMock(is_authenticated=True, 
                             has_role=lambda x: True),
        request=MagicMock(endpoint='admin.users'),
        url_for=lambda x: f"/mock/{x}"
    )
    
    assert '<html' in rendered
    assert 'Users' in rendered