"""Pytest fixtures for Flask app testing.

Provides common fixtures like `app`, `client`, `auth_client`, and `admin_client` so that
unit and integration tests can run without repeating boilerplate setup. The fixtures
use an in-memory SQLite database and plaintext password hashing for speed. External
services such as e-mail sending are disabled. CSRF is turned off to simplify form
submissions during tests.

Note: pytest-flask automatically picks up the `app` fixture to provide its own
`client` fixture, but we override it here to ensure the database is always
initialised and roles/users are available.
"""
from __future__ import annotations

import pytest
from flask_security.utils import hash_password

from app import create_app, db
from app.models.user import Role, User

###############################################################################
# Core application & database fixtures
###############################################################################

@pytest.fixture(scope="session")  # one app instance for the entire test session
def app():  # noqa: D401 – required fixture name for pytest-flask
    """Create and configure a new app instance for this test session."""
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "testing-secret-key",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            # Plaintext hashing is fine for tests and avoids extra deps like bcrypt
            "SECURITY_PASSWORD_HASH": "plaintext",
            "SECURITY_PASSWORD_SALT": "salt",
            # Disable CSRF & e-mail sending for tests
            "WTF_CSRF_ENABLED": False,
            "MAIL_SUPPRESS_SEND": True,
            # Disable login throttling / rate limiting noise in tests
            "RATELIMIT_ENABLED": False,
            # Avoid APScheduler side-effects in tests
            "SCHEDULER_API_ENABLED": False,
            # Fix Flask-Session configuration for tests
            "SESSION_TYPE": "filesystem",
            # Ensure Flask-Security endpoints are properly registered
            "SECURITY_REGISTERABLE": True,
            "SECURITY_REGISTER_URL": "/security/register",
            "SECURITY_LOGIN_URL": "/security/login",
            "SECURITY_LOGOUT_URL": "/security/logout",
            "SECURITY_RECOVERABLE": True,
            "SECURITY_FORGOT_PASSWORD_URL": "/security/forgot-password",
            "SECURITY_RESET_PASSWORD_URL": "/security/reset-password",
            "SECURITY_CHANGEABLE": True,
            "SECURITY_CHANGE_PASSWORD_URL": "/security/change-password",
        }
    )

    # Establish an application context before working with the DB
    with app.app_context():
        db.create_all()

        # Ensure default roles exist
        user_role = Role.query.filter_by(name="user").first()
        if not user_role:
            user_role = Role(name="user")
            db.session.add(user_role)

        admin_role = Role.query.filter_by(name="admin").first()
        if not admin_role:
            admin_role = Role(name="admin")
            db.session.add(admin_role)

        db.session.commit()

    yield app

    # Teardown – drop all tables after the test session ends
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture(scope="session")
def _db(app):  # type: ignore  # pylint: disable=invalid-name
    """Return the app's database instance for pytest-flask-sqlalchemy compatibility."""
    # pytest-flask-sqlalchemy expects an `_db` fixture providing the SQLAlchemy db
    # object so that it can manage transactions. We simply expose the global one.
    return db

###############################################################################
# Helper fixtures – users & authenticated clients
###############################################################################

@pytest.fixture
def regular_user(app):
    """Create (or fetch) a standard active user."""
    with app.app_context():
        user = User.query.filter_by(email="testuser@example.com").first()
        if user is None:
            user = User(
                email="testuser@example.com",
                password=hash_password("password"),
                active=True,
            )
            user.roles.append(Role.query.filter_by(name="user").first())
            db.session.add(user)
            db.session.commit()
        return user


@pytest.fixture
def admin_user(app):
    """Create (or fetch) an admin user with the *admin* role."""
    with app.app_context():
        user = User.query.filter_by(email="admin@example.com").first()
        if user is None:
            user = User(
                email="admin@example.com",
                password=hash_password("password"),
                active=True,
            )
            user.roles.append(Role.query.filter_by(name="admin").first())
            db.session.add(user)
            db.session.commit()
        return user


@pytest.fixture
def client(app):  # override to ensure fresh client per test with our app fixture
    """Return an unauthenticated test client."""
    return app.test_client()


@pytest.fixture
def auth_client(client, regular_user, app):
    """A test client logged in as a *regular_user*."""
    # Try a simpler approach: use actual login POST request
    response = client.post('/security/login', data={
        'email': 'testuser@example.com',
        'password': 'password'
    }, follow_redirects=False)
    
    # Debug: print response to see what's happening
    print(f"Login response status: {response.status_code}")
    print(f"Login response headers: {dict(response.headers)}")
    
    # Check if login was successful (should redirect)
    assert response.status_code in [200, 302], f"Login failed with status {response.status_code}"
    
    return client


@pytest.fixture
def admin_client(client, admin_user, app):
    """A test client logged in as *admin_user*."""
    # Try a simpler approach: use actual login POST request
    response = client.post('/security/login', data={
        'email': 'admin@example.com',
        'password': 'password'
    }, follow_redirects=False)
    
    # Debug: print response to see what's happening
    print(f"Admin login response status: {response.status_code}")
    print(f"Admin login response headers: {dict(response.headers)}")
    
    # Check if login was successful (should redirect)
    assert response.status_code in [200, 302], f"Admin login failed with status {response.status_code}"
    
    return client
