# app/routes/__init__.py

# Create the main blueprint for login redirection
from flask import Blueprint, redirect, url_for, render_template
from flask_security import current_user




bp = Blueprint('main', __name__)


@bp.route('/')
def index():
    """Public landing page at root path.

    If the user is already authenticated redirect them straight to the
    dashboard; otherwise show a simple marketing/landing page.
    """
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))
    return render_template('landing.html')

@bp.route('/login-redirect')
def login_redirect():
    if current_user.is_authenticated:
        if current_user.has_role('admin'):
            return redirect(url_for('admin.users'))
        return redirect(url_for('dashboard.dashboard'))
    return redirect(url_for('security.login'))

