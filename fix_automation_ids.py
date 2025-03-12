# fix_automation_ids.py
from app import create_app, db
from app.models.automation import Automation
import uuid

app = create_app()

with app.app_context():
    # Find automations with NULL automation_id values
    null_automations = Automation.query.filter(Automation.automation_id.is_(None)).all()
    
    print(f"Found {len(null_automations)} automations with NULL IDs")
    
    for automation in null_automations:
        # Generate a new UUID
        new_id = Automation.generate_automation_id()
        print(f"Updating automation '{automation.name}' (ID: {automation.id}) with new automation_id: {new_id}")
        automation.automation_id = new_id
    
    # Save changes
    db.session.commit()
    print("Database updated successfully!")