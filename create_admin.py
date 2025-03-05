# Run this once to create the admin role
from app import create_app, db
from app.models.user import User, Role

app = create_app()

with app.app_context():
    # Create admin role if it doesn't exist
    admin_role = Role.query.filter_by(name='admin').first()
    if not admin_role:
        admin_role = Role(name='admin', description='Administrator')
        db.session.add(admin_role)
        db.session.commit()
        print("Created admin role")
    
    # Assign admin role to your user
    user = User.query.filter_by(email='admin@example.com').first()
    if user:
        if admin_role not in user.roles:
            user.roles.append(admin_role)
            db.session.commit()
            print("Added admin role to user")
        else:
            print("User already has admin role")
    else:
        print("User not found")