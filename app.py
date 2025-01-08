from flask import Flask, request, jsonify, render_template, redirect, url_for, session, Response
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from datetime import datetime
import json
import os
import time

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
bcrypt = Bcrypt(app)
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

webhook_log_file = 'webhook.log'

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')
        user = User(username=username, password=password, is_admin=False)
        try:
            db.session.add(user)
            db.session.commit()
            return redirect(url_for('login'))
        except:
            return "Error: Username already exists."
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = user.is_admin
            return redirect(url_for('dashboard'))
        return "Invalid credentials."
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/webhook', methods=['POST'])
def webhook():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {
        'timestamp': timestamp,
        'payload': request.json
    }
    with open(webhook_log_file, 'a') as file:
        file.write(json.dumps(log_entry) + '\n')
    return jsonify({"message": "Webhook received."}), 200

@app.route('/dashboard')
def dashboard():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    webhook_url = f"{request.url_root}webhook"
    with open(webhook_log_file, 'r') as file:
        logs = [line.strip() for line in file.readlines()]
    return render_template('dashboard.html', webhook_url=webhook_url, logs=logs)

@app.route('/webhook-updates')
def webhook_updates():
    def generate():
        try:
            with open(webhook_log_file, 'r') as f:
                f.seek(0, 2)
                while True:
                    line = f.readline()
                    if line:
                        yield f"data: {line}\n\n"
                    time.sleep(0.5)
        except GeneratorExit:
            pass
    return Response(generate(), mimetype='text/event-stream')

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method == 'POST':
        new_password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')
        user = User.query.get(session['user_id'])
        user.password = new_password
        db.session.commit()
        return redirect(url_for('dashboard'))
    return render_template('settings.html')

@app.route('/users')
@admin_required
def users():
    all_users = User.query.all()
    return render_template('users.html', users=all_users)

@app.route('/delete_user/<int:user_id>')
@admin_required
def delete_user(user_id):
    user = User.query.get(user_id)
    if user:
        db.session.delete(user)
        db.session.commit()
    return redirect(url_for('users'))

@app.template_filter('from_json')
def from_json(value):
    return json.loads(value)

def init_db():
    with app.app_context():
        # Create database tables
        db.create_all()
        
        # Create admin user if it doesn't exist
        if not User.query.filter_by(username='admin').first():
            admin_user = User(
                username='admin',
                password=bcrypt.generate_password_hash('fahrvergnuegen').decode('utf-8'),
                is_admin=True
            )
            db.session.add(admin_user)
            db.session.commit()

        # Create webhook log file if it doesn't exist
        if not os.path.exists(webhook_log_file):
            open(webhook_log_file, 'w').close()

if __name__ == '__main__':
    init_db()
    print("Starting Flask application...")
    print("Database initialized")
    print("Attempting to bind to all interfaces on port 5000...")
    app.run(host='0.0.0.0', port=5000, debug=True)
    print("Flask application started")  # This won't print until shutdown
