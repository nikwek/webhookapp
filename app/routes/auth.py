# app/routes/auth.py
from flask import Blueprint, render_template, redirect, url_for, request, session
from app.models.user import User
from app import db, bcrypt
from datetime import datetime, timezone

bp = Blueprint('auth', __name__)

@bp.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password, password):
            user.last_login = datetime.now(timezone.utc)
            db.session.commit()
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = user.is_admin
            return redirect(url_for('dashboard.dashboard'))
        error = "Invalid username or password"
    return render_template('login.html', error=error)

@bp.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if not username or not password:
            error = "Username and password are required"
        elif User.query.filter_by(username=username).first():
            error = "Username already exists"
        else:
            try:
                user = User(username=username, 
                          password=bcrypt.generate_password_hash(password).decode('utf-8'),
                          is_admin=False)
                db.session.add(user)
                db.session.commit()
                return redirect(url_for('auth.login'))
            except Exception:
                error = "An error occurred. Please try again."
    return render_template('register.html', error=error)

@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))

