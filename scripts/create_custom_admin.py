from app import create_app, db
from app.models.user import User, Role
import secrets
import argparse
from flask_security.utils import hash_password
from datetime import datetime, timezone

def create_admin_user(email, username, password):
    """Create or update an admin user with the specified credentials."""
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

        # Check if user with provided email exists
        user = User.query.filter_by(email=email).first()
        if user:
            # Update existing user
            if not user.confirmed_at:
                user.confirmed_at = datetime.now(timezone.utc)
                print("✓ Updated confirmed_at timestamp")
            
            # Ensure user is active
            if not user.active:
                user.active = True
                print("✓ Activated user")
                
            # Verify admin role
            if admin_role not in user.roles:
                user.roles.append(admin_role)
                print("✓ Added admin role")
                
            # Update password
            user.password = hash_password(password)
            print("✓ Updated password")
                
        else:
            # Create new user with confirmed status
            user = User(
                email=email,
                username=username,
                fs_uniquifier=secrets.token_hex(16),
                password=hash_password(password),
                active=True,
                confirmed_at=datetime.now(timezone.utc)
            )
            user.roles.append(admin_role)
            db.session.add(user)
            print(f"✓ Created new admin user: {email}")

        db.session.commit()
        
        # Verify final state
        print("\nFinal user state:")
        print(f"✓ Email: {user.email}")
        print(f"✓ Username: {user.username}")
        print(f"✓ Active: {user.active}")
        print(f"✓ Roles: {[role.name for role in user.roles]}")
        print(f"✓ Confirmed at: {user.confirmed_at}")
        
        return user

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Create an admin user with custom email and password')
    parser.add_argument('--email', required=True, help='Email for the admin user')
    parser.add_argument('--username', help='Username for the admin user (defaults to part of email before @)')
    parser.add_argument('--password', required=True, help='Password for the admin user')
    
    args = parser.parse_args()
    
    # If username not provided, use part of email before @ symbol
    if not args.username:
        args.username = args.email.split('@')[0]
    
    create_admin_user(args.email, args.username, args.password)
