# app/routes/dashboard.py
from flask import Blueprint, render_template, session, redirect, url_for, request, Response, jsonify
from app.models.webhook import WebhookLog
from app.models.user import User
from app import db, bcrypt
import time, json
from datetime import datetime, timezone

bp = Blueprint('dashboard', __name__)
def format_timestamp(ts):
    return ts.replace('T', ' ').rstrip('Z')

@bp.route('/dashboard')
def dashboard():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    webhook_url = f"{request.url_root}webhook"
    
    all_logs = WebhookLog.query.order_by(WebhookLog.timestamp.desc()).all()
    logs = []
    for log in all_logs:
        data = {
            "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),  # Use database timestamp
            "payload": log.payload
        }
        logs.append(json.dumps(data))

    return render_template('dashboard.html', webhook_url=webhook_url, logs=logs)

@bp.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        new_password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')
        user = User.query.get(session['user_id'])
        user.password = new_password
        db.session.commit()
        return redirect(url_for('dashboard.dashboard'))
    return render_template('settings.html')

@bp.route('/users')
def users():
    all_users = User.query.all()
    return render_template('users.html', users=all_users)

@bp.route('/webhook-updates')
def webhook_updates():
    def generate():
        from app import create_app
        app = create_app()
        with app.app_context():
            last_id = -1
            while True:
                try:
                    logs = WebhookLog.query.filter(WebhookLog.id > last_id).order_by(WebhookLog.timestamp.desc()).all()
                    if logs:
                        last_id = max(log.id for log in logs)
                        for log in logs:
                            data = {
                                "timestamp": log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                                "payload": log.payload
                            }
                            yield f"data: {json.dumps(data)}\n\n"
                except Exception as e:
                    print(f"Error in webhook updates: {e}")
                time.sleep(0.5)

    return Response(generate(), mimetype='text/event-stream')

@bp.route('/clear-logs', methods=['POST'])
def clear_logs():
    if not session.get('is_admin'):
        return jsonify({"error": "Unauthorized"}), 403
    
    try:
        WebhookLog.query.delete()
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)})