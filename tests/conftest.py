# tests/conftest.py
import pytest
from app import create_app, db
from app.models.user import User
from app.models.automation import Automation
from app.models.webhook import WebhookLog
import tempfile
from pathlib import Path

@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdirname:
        yield Path(tmpdirname)

@pytest.fixture
def mock_env_file(temp_dir):
    """Create a temporary .env file with test contents."""
    env_content = """
TEST_KEY1=value1
TEST_KEY2=value2
# This is a comment
TEST_KEY3=value3 with spaces
"""
    env_file = temp_dir / '.env'
    env_file.write_text(env_content.strip())
    return env_file

@pytest.fixture
def mock_project_root(monkeypatch, temp_dir):
    """Mock the project root directory."""
    def mock_get_project_root():
        return temp_dir
    
    # Add project root to Python path if needed
    import sys
    from pathlib import Path
    project_root = Path(__file__).parent.parent
    if str(project_root) not in sys.path:
        sys.path.append(str(project_root))
    
    from scripts import ScriptUtils
    monkeypatch.setattr(ScriptUtils, 'get_project_root', mock_get_project_root)
    return temp_dir

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
    user = User(username='testuser')
    user.set_password('password')
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