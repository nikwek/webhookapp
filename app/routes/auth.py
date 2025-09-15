# app/routes/auth.py
from flask import Blueprint, redirect, url_for, request, flash
from flask_security import current_user
from app.routes.webhook import limiter

bp = Blueprint('auth', __name__)

# Post-login redirect handler
@bp.route('/login-redirect')
def login_redirect():
    if current_user.is_authenticated:
        if current_user.has_role('admin'):
            return redirect(url_for('admin.users'))
        return redirect(url_for('dashboard.dashboard'))
    return redirect(url_for('security.login'))

# Redirect '/login' to the Flask-Security login endpoint
@bp.route('/login')
def login():
    if current_user.is_authenticated:
        if current_user.has_role('admin'):
            return redirect(url_for('admin.users'))
        return redirect(url_for('dashboard.dashboard'))
    return redirect(url_for('security.login'))

# Rate-limited registration endpoint
@bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("3 per minute", key_func=lambda: request.remote_addr)
@limiter.limit("10 per hour", key_func=lambda: request.remote_addr)
def register():
    if request.method == 'POST':
        # Additional bot detection - check for suspicious patterns
        user_agent = request.headers.get('User-Agent', '').lower()
        if any(bot in user_agent for bot in ['bot', 'crawler', 'spider', 'scraper']):
            flash('Registration temporarily unavailable. Please try again later.', 'error')
            return redirect(url_for('security.register'))
    
    return redirect(url_for('security.register'))

# Redirect '/change-password' to the Flask-Security change password endpoint
@bp.route('/change-password')
def change_password():
    return redirect(url_for('security.change_password'))

# Redirect '/logout' to the Flask-Security logout endpoint
@bp.route('/logout')
def logout():
    return redirect(url_for('security.logout'))
