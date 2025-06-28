# app/routes/__init__.py

# Create the main blueprint for login redirection
from flask import Blueprint, redirect, url_for
from flask_security import current_user




bp = Blueprint('main', __name__)

@bp.route('/login-redirect')
def login_redirect():
    if current_user.is_authenticated:
        if current_user.has_role('admin'):
            return redirect(url_for('admin.users'))
        return redirect(url_for('dashboard.dashboard'))
    return redirect(url_for('security.login'))

