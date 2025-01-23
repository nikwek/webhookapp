# app/services/webhook_processor.py

from app.models.automation import Automation
from app.models.webhook_log import WebhookLog
from app import db
class WebhookProcessor:
    def process_webhook(self, automation_id, payload):
        automation = Automation.query.filter_by(automation_id=automation_id).first()

        if not automation:
            raise ValueError(f"No automation found with id: {automation_id}")

        if not automation.is_active:
            # Log attempt to process inactive automation
            current_app.logger.warning(f"Attempt to process webhook for inactive automation: {automation_id}")
            return None

        # Process the webhook and create a log entry
        log_entry = WebhookLog(
            automation_id=automation.id,
            payload=payload
        )
        db.session.add(log_entry)
        db.session.commit()

        # Additional processing logic here
        return payload