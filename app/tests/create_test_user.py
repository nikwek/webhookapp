from app import create_app, db
from app.models.user import User, Role
import secrets
from flask_security.utils import hash_password  # Import the proper password hashing function

app = create_app()

with app.app_context():
    # Create roles if they don't exist
    admin_role = Role.query.filter_by(name='admin').first()
    if not admin_role:
        admin_role = Role(name='admin', description='Administrator')
        db.session.add(admin_role)
    
    # Create a test admin user
    test_user = User.query.filter_by(email='admin@example.com').first()
    if not test_user:
        test_user = User(
            email='admin@example.com',
            username='admin',
            fs_uniquifier=secrets.token_hex(16),
            password=hash_password('password123'),  # Use Flask-Security's hash_password
            active=True
        )
        test_user.roles.append(admin_role)
        db.session.add(test_user)
    
    db.session.commit()
    print('Test user created successfully!')