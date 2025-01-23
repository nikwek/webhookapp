from flask import (
    Blueprint, render_template, jsonify, session,
    redirect, url_for, Response, request
)
from flask_login import login_required, current_user
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from app import db
import time

bp = Blueprint('dashboard', __name__)


@bp.route('/dashboard')
@login_required
def dashboard():
    """Render the dashboard page for non-admin users."""
    if session.get('is_admin'):
        return redirect(url_for('admin.users'))

    user_id = current_user.id
    automations = Automation.query.filter_by(user_id=user_id).all()

    # Generate webhook URLs for each automation
    base_url = request.url_root.rstrip('/')
    for automation in automations:
        automation.webhook_url = f"{base_url}/webhook?automation_id={automation.automation_id}"

    return render_template('dashboard.html', automations=automations)


@bp.route('/api/logs/stream')
@login_required
def stream_logs():
    def generate():
        last_id = 0
        while True:
            try:
                # Create a new session for each query
                with db.session.begin():
                    logs = WebhookLog.query.join(Automation).filter(
                        Automation.user_id == current_user.id
                    ).order_by(WebhookLog.timestamp.desc()).limit(100).all()
                    
                    # Convert to dict before closing session
                    log_data = [log.to_dict() for log in logs]
                    
                    if logs and logs[0].id != last_id:
                        last_id = logs[0].id
                        yield f"data: {json.dumps(log_data)}\n\n"
                
                db.session.remove()  # Explicitly remove the session
                time.sleep(5)  # Update every 5 seconds
                
            except Exception as e:
                print(f"Error in stream_logs: {e}")
                db.session.remove()  # Ensure session is removed on error
                yield f"data: {json.dumps([])}\n\n"
                time.sleep(5)  # Wait before retrying

    return Response(generate(), mimetype='text/event-stream')



@bp.route('/clear-logs', methods=['POST'])
@login_required
def clear_logs():
    """Clear webhook logs for the current user."""
    try:
        user_id = current_user.id
        WebhookLog.query.join(Automation).filter(
            Automation.user_id == user_id
        ).delete(synchronize_session=False)

        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        print(f"Error clearing logs: {e}")
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@bp.route('/settings')
@login_required
def settings():
    """Render the settings page."""
    return render_template('settings.html')