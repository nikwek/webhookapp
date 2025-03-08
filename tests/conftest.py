import pytest
import secrets
from app import create_app, db
from app.models.user import User, Role
from app.models.automation import Automation
from app.models.portfolio import Portfolio
from app.models.webhook import WebhookLog
from flask_security import hash_password

@pytest.fixture(scope='function')
def app():
    app = create_app()
    app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test_key',
        'SECURITY_PASSWORD_SALT': 'test_salt'
    })
    
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture(scope='function')
def client(app):
    return app.test_client()

@pytest.fixture(scope='function')
def user_role(app):
    """Create user role"""
    with app.app_context():
        role = Role.query.filter_by(name='user').first()
        if not role:
            role = Role(name='user', description='User')
            db.session.add(role)
            db.session.commit()
            # Get the fresh role from the database
            role = Role.query.filter_by(name='user').first()
        return role

@pytest.fixture(scope='function')
def admin_role(app):
    """Create admin role"""
    with app.app_context():
        role = Role.query.filter_by(name='admin').first()
        if not role:
            role = Role(name='admin', description='Administrator')
            db.session.add(role)
            db.session.commit()
            # Get the fresh role from the database
            role = Role.query.filter_by(name='admin').first()
        return role

@pytest.fixture(scope='function')
def regular_user(app, user_role):
    """Create regular user with proper role attachment"""
    with app.app_context():
        # First check if user exists
        user = User.query.filter_by(email='testuser@example.com').first()
        if user:
            # Make sure role is attached
            if user_role not in user.roles:
                user.roles.append(user_role)
                db.session.commit()
            return user
            
        # Create new user with role
        user = User(
            email='testuser@example.com',
            username='testuser',
            fs_uniquifier=secrets.token_hex(16),
            password=hash_password('password'),
            active=True
        )
        user.roles.append(user_role)  # Ensure role is valid
        db.session.add(user)
        db.session.commit()
        
        # Return fresh instance
        return User.query.filter_by(email='testuser@example.com').first()

@pytest.fixture(scope='function')
def admin_user(app, admin_role, user_role):
    """Create admin user with proper roles"""
    with app.app_context():
        # First check if admin exists
        admin = User.query.filter_by(email='admin@example.com').first()
        if admin:
            # Make sure roles are attached
            if admin_role not in admin.roles:
                admin.roles.append(admin_role)
            if user_role not in admin.roles:
                admin.roles.append(user_role)
            db.session.commit()
            return admin
            
        # Create new admin with roles
        admin = User(
            email='admin@example.com',
            username='admin',
            fs_uniquifier=secrets.token_hex(16),
            password=hash_password('adminpass'),
            active=True
        )
        admin.roles.append(admin_role)
        admin.roles.append(user_role)  # Admin should also have user role
        db.session.add(admin)
        db.session.commit()
        
        # Return fresh instance
        return User.query.filter_by(email='admin@example.com').first()

@pytest.fixture(scope='function')
def auth_client(app, client, regular_user):
    """Client with regular user logged in - works with Flask-Security"""
    with app.app_context():
        from flask_security.utils import login_user
        from flask import session
        
        # Use Flask-Security's login_user function
        with client.session_transaction() as sess:
            # Clear any existing session
            sess.clear()
        
        # Refresh user from the database
        user = User.query.get(regular_user.id)
        
        # Login using Flask-Security's utility
        with app.test_request_context():
            login_user(user)
            # Save the session values to use with the test client
            session_data = dict(session)
        
        # Apply the session values to the test client
        with client.session_transaction() as sess:
            for key, value in session_data.items():
                sess[key] = value
        
        return client

@pytest.fixture(scope='function')
def admin_client(app, client, admin_user):
    """Client with admin user logged in - works with Flask-Security"""
    with app.app_context():
        from flask_security.utils import login_user
        from flask import session
        
        # Use Flask-Security's login_user function
        with client.session_transaction() as sess:
            # Clear any existing session
            sess.clear()
        
        # Refresh admin user from the database
        admin = db.session.get(User, admin_user.id)
        
        # Login using Flask-Security's utility
        with app.test_request_context():
            login_user(admin)
            # Save the session values to use with the test client
            session_data = dict(session)
        
        # Apply the session values to the test client
        with client.session_transaction() as sess:
            for key, value in session_data.items():
                sess[key] = value
        
        return client

@pytest.fixture(scope='function')
def portfolio(app, regular_user):
    """Create a test portfolio"""
    with app.app_context():
        portfolio = Portfolio(
            user_id=regular_user.id,
            name='Test Portfolio',
            exchange='coinbase',
            portfolio_id='test-portfolio-id'
        )
        db.session.add(portfolio)
        db.session.commit()
        return portfolio

@pytest.fixture(scope='function')
def automation(app, regular_user):
    """Create a test automation without depending on portfolio fixture"""
    with app.app_context():
        # Create a portfolio specifically for this automation
        portfolio = Portfolio(
            user_id=regular_user.id,
            name='Test Automation Portfolio',
            exchange='coinbase',
            portfolio_id='automation-test-portfolio'  # Unique portfolio_id
        )
        db.session.add(portfolio)
        db.session.commit()
        
        # Now create the automation within the same session
        automation = Automation(
            user_id=regular_user.id,
            portfolio_id=portfolio.id,
            name='Test Automation',
            automation_id='test-auto-id',
            trading_pair='BTC-USD',
            conditions={
                'indicator': 'price',
                'operator': '>',
                'value': 50000
            },
            actions={
                'type': 'notify',
                'message': 'Test alert'
            },
            is_active=True
        )
        db.session.add(automation)
        db.session.commit()
        return automation