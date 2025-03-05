# app/routes/auth.py
from flask import Blueprint, redirect, url_for
from flask_security import current_user

bp = Blueprint('auth', __name__)

# Redirect '/login' to the Flask-Security login endpoint
@bp.route('/login')
def login():
    if current_user.is_authenticated:
        if current_user.has_role('admin'):
            return redirect(url_for('admin.users'))
        return redirect(url_for('dashboard.dashboard'))
    return redirect(url_for('security.login'))

# Redirect '/register' to the Flask-Security register endpoint
@bp.route('/register')
def register():
    return redirect(url_for('security.register'))

# Redirect '/change-password' to the Flask-Security change password endpoint
@bp.route('/change-password')
def change_password():
    return redirect(url_for('security.change_password'))

# Redirect '/logout' to the Flask-Security logout endpoint
@bp.route('/logout')
def logout():
    return redirect(url_for('security.logout'))
