# confirm_user.py
from app import create_app, db
from app.models.user import User
from datetime import datetime, timezone

app = create_app()

with app.app_context():
    user = User.query.filter_by(email='admin@example.com').first()
    if user:
        user.confirmed_at = datetime.now(timezone.utc)
        db.session.commit()
        print("User confirmed!")
    else:
        print("User not found!")