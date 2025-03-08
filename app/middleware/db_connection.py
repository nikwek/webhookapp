from functools import wraps
from flask import current_app, jsonify
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, StatementError
from app import db

def check_db_connection(view_function):
    @wraps(view_function)
    def wrapper(*args, **kwargs):
        try:
            # Verify connection before each request
            db.session.execute(text('SELECT 1'))
            return view_function(*args, **kwargs)
        except (OperationalError, StatementError) as e:
            current_app.logger.error(f"Database connection error: {e}")
            # Try to reconnect
            db.session.remove()
            try:
                db.session.execute(text('SELECT 1'))
                return view_function(*args, **kwargs)
            except Exception as e:
                current_app.logger.error(f"Failed to reconnect to database: {e}")
                return jsonify({
                    'status': 'error',
                    'message': 'Database connection lost'
                }), 500
    return wrapper