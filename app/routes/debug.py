# app/routes/debug.py
from flask import Blueprint, current_app, jsonify, abort, flash, redirect, url_for
from flask_mail import Message
from flask_security import RegisterForm, current_user, login_required, url_for_security, roles_required
from sqlalchemy import text, inspect
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone
from app import db, scheduler
from app.models.user import User
from app.models.portfolio import Portfolio

debug = Blueprint('debug', __name__)

@debug.route('/test_email')
def test_email():
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

@debug.route("/debug/scheduler/jobs")
@roles_required("admin")
def list_scheduler_jobs():
    """Return basic info on all APScheduler jobs."""
    jobs = [
        {
            "id": j.id,
            "next_run_time": j.next_run_time.isoformat() if j.next_run_time else None,
            "trigger": str(j.trigger)
        }
        for j in scheduler.get_jobs()
    ]
    return jsonify(jobs)


@debug.route("/debug/update-strategy-values")
def update_strategy_values():
    """Manually trigger an update of all strategy values."""
    try:
        from app.services.strategy_value_service import snapshot_all_strategies
        snapshot_all_strategies()
        return jsonify({
            "success": True,
            "message": "Strategy values updated successfully"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Error updating strategy values: {str(e)}"
        }), 500
