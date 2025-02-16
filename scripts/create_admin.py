#!/usr/bin/env python
# scripts/create_admin.py
import os
import sys

# Ensure the project root is in the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))  # scripts directory
project_root = os.path.dirname(current_dir)               # project root
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Now we can import from the scripts package
from scripts import ScriptUtils

def create_admin_user():
    """Create the admin user if it doesn't exist."""
    ScriptUtils.setup_project_path()
    
    from app import create_app, db
    from app.models.user import User
    
    app = create_app()
    
    with app.app_context():
        admin_user = User.query.filter_by(username='admin').first()
        if not admin_user:
            admin_user = User(
                username='admin',
                is_admin=True,
                require_password_change=True
            )
            admin_user.set_password('admin')
            db.session.add(admin_user)
            db.session.commit()
            print("Admin user created successfully")
            print("Login with:")
            print("  username: admin")
            print("  password: admin")
            print("You will be prompted to change your password on first login.")
        else:
            print("Admin user already exists")

if __name__ == "__main__":
    create_admin_user()