# app/routes/auth.py
from flask import Blueprint, render_template, redirect, url_for, request, session, flash
from app.models.user import User
from app import db, bcrypt
from datetime import datetime, timezone
from flask_login import login_user, logout_user, current_user

bp = Blueprint('auth', __name__)

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.dashboard'))
        
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            session['user_id'] = user.id
            session['is_admin'] = user.is_admin
            login_user(user)
            
            if user.require_password_change:
                return redirect(url_for('auth.change_password'))
                
            return redirect(url_for('dashboard.dashboard'))
            
        flash('Invalid username or password')
    return render_template('login.html')

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            return "Error: Username already exists."
        
        user = User(
            username=username,
            is_admin=False,
            require_password_change=False,
            last_activity=datetime.now(timezone.utc)
        )
        user.set_password(password)
        
        try:
            db.session.add(user)
            db.session.commit()
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            return f"Error creating user: {str(e)}"
            
    return render_template('register.html')

@bp.route('/change-password', methods=['GET', 'POST'])
def change_password():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
        
    if request.method == 'POST':
        user = User.query.get(session['user_id'])
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        if new_password != confirm_password:
            return "Passwords do not match"
            
        user.set_password(new_password)
        user.require_password_change = False
        db.session.commit()
        
        return redirect(url_for('dashboard.dashboard'))
        
    return render_template('auth/change_password.html')

@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))

