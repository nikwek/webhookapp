# app/routes/debug.py
from flask import Blueprint, current_app, jsonify, abort, flash, redirect, url_for
from flask_mail import Message
from flask_security import RegisterForm, current_user, login_required, url_for_security, roles_required
from sqlalchemy import text, inspect, func
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone, timedelta
from app import db, scheduler
from app.models.user import User
from app.models.portfolio import Portfolio
from app.models.trading import StrategyValueHistory
from app.models.webhook import WebhookLog

debug = Blueprint('debug', __name__)

@debug.route('/test_email')
def test_email():
    """Send a test email to confirm that Flask-Mail is configured and working."""
    try:
        # Get mail from current_app instead of importing it
        from flask_mail import Mail
        mail = Mail(current_app)
        
        msg = Message(
            "Test Email from Flask App",
            recipients=["nik@wekwerth.net"]  # Replace with your email
        )
        msg.body = "This is a test email from your Flask application."
        mail.send(msg)
        return "Email sent successfully!"
    except Exception as e:
        return f"Error sending email: {str(e)}"
    

@debug.route('/debug/register_form')
@roles_required("admin")
def debug_register_form():
    """Debug the registration form fields"""
    # Get the register form class
    register_form_class = current_app.security._register_form
    # Create an instance
    form = register_form_class()
    # Get all field names
    fields = [f.name for f in form]
    return f"Registration form fields: {fields}"

@debug.route('/debug/db-test')
@roles_required("admin")
def test_db():
    """Test database connectivity and user table"""
    try:
        # Test raw connection with proper text() wrapper
        result = db.session.execute(text('SELECT 1'))
        connection_ok = result.scalar() == 1
        
        # Test user table
        users = User.query.all()
        
        return jsonify({
            'status': 'success',
            'connection': 'OK' if connection_ok else 'Failed',
            'user_count': len(users),
            'first_user_email': users[0].email if users else None
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
    
@debug.route('/health')
@roles_required("admin")
def health_check():
    """General health check endpoint"""
    return jsonify({'status': 'healthy'})

@debug.route('/health/db')
@roles_required("admin")
def db_health_check():
    """Database-specific health check endpoint"""
    try:
        # Test database connection and critical tables
        db.session.execute(text('SELECT 1 FROM users'))
        db.session.execute(text('SELECT 1 FROM roles'))
        
        # Get database statistics
        inspector = inspect(db.engine)
        table_names = inspector.get_table_names()
        
        return jsonify({
            'status': 'healthy',
            'message': 'Database connection is working',
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'tables': table_names,
            'database_url': current_app.config['SQLALCHEMY_DATABASE_URI'].split('///')[0] + '///*****'
        })
    except SQLAlchemyError as e:
        current_app.logger.error(f"Database health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'message': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }), 500
    
@debug.route('/debug/db-tables')
@roles_required("admin")
def db_tables():
    """List all database tables and their columns"""
    try:
        inspector = inspect(db.engine)
        tables = {}
        for table_name in inspector.get_table_names():
            columns = []
            for column in inspector.get_columns(table_name):
                columns.append({
                    'name': column['name'],
                    'type': str(column['type']),
                    'nullable': column['nullable']
                })
            tables[table_name] = columns
            
        return jsonify({
            'status': 'success',
            'tables': tables,
            'database_url': current_app.config['SQLALCHEMY_DATABASE_URI'].split('///')[0] + '///*****'
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500




@debug.route('/debug/check-suspension/<int:user_id>')
@roles_required("admin")
@login_required
def check_suspension(user_id):
    """Debug endpoint to verify user suspension status"""
    
    # Only allow admins to check suspension status
    if not current_user.is_admin:
        return jsonify({
            'status': 'error',
            'message': 'Admin access required'
        }), 403
        
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({
                'status': 'error',
                'message': f'User with ID {user_id} not found'
            }), 404
            
        return jsonify({
            'status': 'success',
            'user': {
                'id': user.id,
                'email': user.email,
                'is_suspended': user.is_suspended,
                'active': user.active,
                'last_activity': user.last_activity.isoformat() if user.last_activity else None
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Error checking user suspension: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
    
@debug.route('/flash-test')
def flash_test():
    """Generate sample flash messages (error & info) then redirect to the login page to verify flash rendering."""
    flash("This is a test error message", "error")
    flash("This is a test info message", "info")
    return redirect(url_for_security('login'))

@debug.route('/debug/session')
def debug_session():
    """Debug the current session and flash messages"""
    from flask import session, get_flashed_messages
    
    # Check what's in the session
    session_data = {k: v for k, v in session.items() if k != '_csrf_token'}
    
    # Get all flashed messages (but this will consume them!)
    flashed_messages = get_flashed_messages(with_categories=True)
    
    # Add the messages back to the session
    for category, message in flashed_messages:
        flash(message, category)
    
    return jsonify({
        'session_data': session_data,
        'has_flashes': len(flashed_messages) > 0,
        'flash_messages': flashed_messages
    })

@debug.route('/debug/login-test')
def login_test():
    """Trigger flash messages for all common categories and redirect to login for visual inspection."""
    
    
    # Flash messages with different categories to test display
    flash("Test error message", "error")
    flash("Test info message", "info")
    flash("Test danger message", "danger")
    flash("Test warning message", "warning")
    flash("Test success message", "success")
    
    # Log that we've sent flash messages
    current_app.logger.info("Sent test flash messages with various categories")
    
    return redirect(url_for_security('login'))

@debug.route('/debug/versions')
def debug_versions():
    """Return the current versions of Flask and Flask-Security the app is running with."""
    import flask_security
    import flask
    from flask import jsonify
    
    return jsonify({
        'flask_version': flask.__version__,
        'flask_security_version': flask_security.__version__
    })

@debug.route('/debug/security-messages')
@roles_required("admin")
def security_messages():
    """Check Flask-Security message configuration"""
    
    
    # Get Flask-Security configuration
    security_config = {}
    for key in current_app.config:
        if key.startswith('SECURITY_MSG_'):
            security_config[key] = current_app.config[key]
    
    # Check if flashes are enabled
    flash_enabled = current_app.config.get('SECURITY_FLASH_MESSAGES', False)
    
    return jsonify({
        'flash_enabled': flash_enabled,
        'security_messages': security_config
    })

@debug.route('/debug/login-process')
@roles_required("admin")
def debug_login_process():
    """Debug the login process"""
    from flask import current_app, render_template_string, request
    from flask_security import _security
    
    # Get the login form
    login_form = _security.login_form()
    
    # Check form details
    form_info = {
        'form_fields': [field.name for field in login_form],
        'csrf_enabled': login_form.meta.csrf,
        'security_flash_messages': current_app.config.get('SECURITY_FLASH_MESSAGES', False)
    }
    
    # Render a simple template with form info
    template = '''
    <h2>Login Form Debug</h2>
    <pre>{{ form_info|tojson(indent=2) }}</pre>
    <h3>Flash Messages Handling</h3>
    <p>Flash messages enabled: {{ security_flash_messages }}</p>
    '''
    
    return render_template_string(
        template, 
        form_info=form_info,
        security_flash_messages=current_app.config.get('SECURITY_FLASH_MESSAGES', False)
    )

@debug.route('/debug/flash-categories')
def flash_categories():
    """Test various flash message categories"""
    
    
    # Test with common Flask-Security categories
    flash("This is an error message", "error")
    flash("This is a danger message", "danger")
    
    # Use your URL pattern instead of url_for_security
    return redirect(url_for('security.login'))

@debug.route('/debug/registration-config')
@roles_required("admin")
def registration_config():
    """Show registration configuration"""
    
    
    # Get registration-related configuration
    config = {
        'SECURITY_REGISTERABLE': current_app.config.get('SECURITY_REGISTERABLE', False),
        'SECURITY_CONFIRMABLE': current_app.config.get('SECURITY_CONFIRMABLE', False),
        'SECURITY_POST_REGISTER_VIEW': current_app.config.get('SECURITY_POST_REGISTER_VIEW', 'None'),
        'SECURITY_FLASH_MESSAGES': current_app.config.get('SECURITY_FLASH_MESSAGES', False),
        'WTF_CSRF_CHECK_DEFAULT': current_app.config.get('WTF_CSRF_CHECK_DEFAULT', True),
        'MAIL_SERVER': current_app.config.get('MAIL_SERVER', 'None')
    }
    
    return jsonify(config)

@debug.route('/debug/try-register')
def try_register():
    """Debug registration process"""
    
    
    # Add a flash message to test if they appear on the registration page
    flash("This is a test error message for registration", "error")
    
    # Redirect to the registration page
    return redirect(url_for('security.register'))

@debug.route("/debug/scheduler")
@roles_required("admin")
def scheduler_debug():
    """Comprehensive scheduler debug information."""
    try:
        # Get scheduler instance
        sched_ext = current_app.extensions.get("apscheduler")
        if sched_ext:
            sched = sched_ext.scheduler
            scheduler_active = sched.running
        else:
            sched = scheduler
            scheduler_active = sched.running if hasattr(sched, 'running') else None
        
        # Get all jobs
        all_jobs = [
            {
                "id": j.id,
                "next_run_time": j.next_run_time.isoformat() if j.next_run_time else None,
                "trigger": str(j.trigger),
                "func_name": j.func.__name__ if hasattr(j.func, '__name__') else str(j.func)
            }
            for j in sched.get_jobs()
        ]
        
        # Get specific daily snapshot job info
        snapshot_job = sched.get_job("daily_strategy_snapshot")
        
        # Get last snapshot timestamp and check for source info in logs
        last_snapshot = (
            db.session.query(func.max(StrategyValueHistory.timestamp)).scalar()
        )
        
        # Try to determine what triggered the last snapshot by checking recent logs
        # This is a best-effort attempt - we can't always determine the exact trigger
        last_trigger_source = "unknown"
        if last_snapshot:
            # Check if there was a manual trigger around the same time
            # (This is approximate since we don't store trigger source with snapshots)
            time_window = timedelta(minutes=5)
            recent_manual_logs = db.session.query(WebhookLog).filter(
                WebhookLog.timestamp >= last_snapshot - time_window,
                WebhookLog.timestamp <= last_snapshot + time_window,
                WebhookLog.message.like('%manual%')
            ).first()
            
            if recent_manual_logs:
                last_trigger_source = "likely_manual"
            elif snapshot_job and snapshot_job.next_run_time:
                # Check if last snapshot was close to a scheduled time
                # Convert both to UTC for comparison to avoid timezone issues
                try:
                    # Ensure last_snapshot is timezone-aware (assume UTC if naive)
                    if last_snapshot.tzinfo is None:
                        last_snapshot_utc = last_snapshot.replace(tzinfo=timezone.utc)
                    else:
                        last_snapshot_utc = last_snapshot.astimezone(timezone.utc)
                    
                    # Convert next_run_time to UTC and calculate expected previous run
                    next_run_utc = snapshot_job.next_run_time.astimezone(timezone.utc)
                    expected_time = next_run_utc.replace(
                        year=last_snapshot_utc.year,
                        month=last_snapshot_utc.month, 
                        day=last_snapshot_utc.day
                    ) - timedelta(days=1)  # Previous day's scheduled time
                    
                    if abs((last_snapshot_utc - expected_time).total_seconds()) < 3600:  # Within 1 hour
                        last_trigger_source = "likely_scheduler"
                except Exception:
                    # If timezone conversion fails, just leave as unknown
                    pass
        
        return jsonify({
            "scheduler_active": scheduler_active,
            "total_jobs": len(all_jobs),
            "all_jobs": all_jobs,
            "daily_snapshot_job": {
                "id": snapshot_job.id if snapshot_job else "daily_strategy_snapshot",
                "next_run_time": snapshot_job.next_run_time.isoformat() if snapshot_job and snapshot_job.next_run_time else None,
                "trigger": str(snapshot_job.trigger) if snapshot_job else "not_found",
                "last_snapshot": last_snapshot.isoformat() if last_snapshot else None,
                "last_trigger_source": last_trigger_source
            }
        })
        
    except Exception as e:
        return jsonify({
            "error": f"Failed to get scheduler info: {str(e)}",
            "scheduler_active": None
        }), 500


@debug.route("/debug/update-strategy-values")
@roles_required("admin")
def update_strategy_values():
    """Manually trigger an update of all strategy values."""
    try:
        from app.services.strategy_value_service import snapshot_all_strategies
        snapshot_all_strategies(source="manual_debug_endpoint")
        return jsonify({
            "success": True,
            "message": "Strategy values updated successfully"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error updating strategy values: {str(e)}"
        }), 500

@debug.route("/twrr/debug/<int:strategy_id>")
@roles_required("admin")
def twrr_debug(strategy_id: int):
    """Debug TWRR calculation for a specific strategy."""
    from app.models.trading import TradingStrategy, AssetTransferLog
    from app.services.price_service import PriceService
    from sqlalchemy import asc
    
    # Get strategy and snapshots
    strategy = TradingStrategy.query.get_or_404(strategy_id)
    snaps = (
        StrategyValueHistory.query
        .filter_by(strategy_id=strategy_id)
        .order_by(asc(StrategyValueHistory.timestamp))
        .all()
    )
    
    if len(snaps) < 2:
        return jsonify({"error": "Need at least 2 snapshots for TWRR calculation"})
    
    # Get all transfers for this strategy
    transfers = (
        AssetTransferLog.query
        .filter(
            (AssetTransferLog.strategy_id_from == strategy_id)
            | (AssetTransferLog.strategy_id_to == strategy_id)
        )
        .order_by(asc(AssetTransferLog.timestamp))
        .all()
    )
    
    # Build debug info
    debug_data = {
        "strategy_id": strategy_id,
        "strategy_name": strategy.name,
        "snapshots": [
            {
                "timestamp": snap.timestamp.isoformat(),
                "value_usd": float(snap.value_usd)
            }
            for snap in snaps
        ],
        "transfers": [
            {
                "timestamp": tr.timestamp.isoformat(),
                "asset_symbol": tr.asset_symbol,
                "amount": float(tr.amount),
                "strategy_id_from": tr.strategy_id_from,
                "strategy_id_to": tr.strategy_id_to,
                "direction": "inflow" if tr.strategy_id_to == strategy_id else "outflow"
            }
            for tr in transfers
        ],
        "intervals": []
    }
    
    # Calculate interval flows like the main TWRR function does
    first_snap_ts = snaps[0].timestamp
    relevant_transfers = [tr for tr in transfers if tr.timestamp > first_snap_ts]
    
    interval_flows = {i: 0.0 for i in range(1, len(snaps))}
    for tr in relevant_transfers:
        # Determine sign
        if tr.strategy_id_to == strategy_id:
            sign = 1
        elif tr.strategy_id_from == strategy_id:
            sign = -1
        else:
            continue
            
        try:
            price_usd = PriceService.get_price_usd(tr.asset_symbol)
        except Exception:
            price_usd = 0.0
        usd_amount = float(tr.amount) * price_usd * sign
        
        # Find which interval this transfer belongs to
        for idx in range(1, len(snaps)):
            if snaps[idx - 1].timestamp < tr.timestamp < snaps[idx].timestamp:
                interval_flows[idx] += usd_amount
                break
    
    # Add interval analysis
    for i in range(1, len(snaps)):
        prev_val = float(snaps[i - 1].value_usd)
        curr_val = float(snaps[i].value_usd)
        flow = interval_flows.get(i, 0.0)
        
        # Apply the same logic as the main function
        if abs(curr_val - prev_val) < 1e-6:
            flow_adjusted = 0.0
        else:
            flow_adjusted = flow
            
        if prev_val > 0:
            sub_return = (curr_val - flow_adjusted) / prev_val - 1.0
        else:
            sub_return = 0.0
            
        debug_data["intervals"].append({
            "interval": i,
            "prev_timestamp": snaps[i - 1].timestamp.isoformat(),
            "curr_timestamp": snaps[i].timestamp.isoformat(),
            "prev_value": prev_val,
            "curr_value": curr_val,
            "raw_flow": flow,
            "adjusted_flow": flow_adjusted,
            "sub_return": round(sub_return, 6),
            "sub_return_pct": round(sub_return * 100, 2)
        })
    
    return jsonify(debug_data)