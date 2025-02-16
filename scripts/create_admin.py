from scripts import ScriptUtils
import sys

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
        else:
            print("Admin user already exists")

if __name__ == "__main__":
    create_admin_user()