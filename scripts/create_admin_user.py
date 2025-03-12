from app import create_app, db
from app.models.user import User, Role
import secrets
from flask_security.utils import hash_password, verify_password
from datetime import datetime, timezone

app = create_app()

with app.app_context():
    # Create admin role if it doesn't exist
    admin_role = Role.query.filter_by(name='admin').first()
    if not admin_role:
        admin_role = Role(name='admin', description='Administrator')
        db.session.add(admin_role)
        db.session.commit()
        print("✓ Created admin role")
    else:
        print("✓ Admin role exists")

    # Create or verify admin user
    test_user = User.query.filter_by(email='admin@example.com').first()
    if test_user:
        # Update existing user
        if not test_user.confirmed_at:
            test_user.confirmed_at = datetime.now(timezone.utc)
            print("✓ Updated confirmed_at timestamp")
        
        # Ensure user is active
        if not test_user.active:
            test_user.active = True
            print("✓ Activated user")
            
        # Verify admin role
        if admin_role not in test_user.roles:
            test_user.roles.append(admin_role)
            print("✓ Added admin role")
            
        # Verify password
        test_password = 'password123'
        is_valid = verify_password(test_password, test_user.password)
        print(f"✓ Password verification: {'SUCCESS' if is_valid else 'FAILED'}")
        
        if not is_valid:
            test_user.password = hash_password('password123')
            print("✓ Updated password hash")
            
    else:
        # Create new user with confirmed status
        test_user = User(
            email='admin@example.com',
            username='admin',
            fs_uniquifier=secrets.token_hex(16),
            password=hash_password('password123'),
            active=True,
            confirmed_at=datetime.now(timezone.utc)
        )
        test_user.roles.append(admin_role)
        db.session.add(test_user)
        print("✓ Created new admin user")

    db.session.commit()
    
    # Verify final state
    print("\nFinal user state:")
    print(f"✓ Email: {test_user.email}")
    print(f"✓ Active: {test_user.active}")
    print(f"✓ Roles: {[role.name for role in test_user.roles]}")
    print(f"✓ Confirmed at: {test_user.confirmed_at}")