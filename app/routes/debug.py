# app/routes/debug.py
from flask import Blueprint, current_app, jsonify
from flask_mail import Message
from flask_security import RegisterForm
from flask import current_app
from sqlalchemy import text, inspect
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime, timezone
from app import db
from app.models.user import User
from app.models.automation import Automation
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
def health_check():
    """General health check endpoint"""
    return jsonify({'status': 'healthy'})

@debug.route('/health/db')
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
    
@debug.route('/debug/automation/portfolio/<string:coinbase_portfolio_id>')
def get_automation_by_portfolio(coinbase_portfolio_id):
    """Debug endpoint to find automation by Coinbase portfolio UUID"""
    try:
        portfolio = Portfolio.query.filter_by(portfolio_id=coinbase_portfolio_id).first()
        
        if not portfolio:
            return jsonify({
                'status': 'not_found',
                'message': f'No portfolio found with Coinbase UUID: {coinbase_portfolio_id}'
            }), 404
        
        current_app.logger.info(f"Found portfolio - ID: {portfolio.id}, Name: {portfolio.name}, Coinbase UUID: {portfolio.portfolio_id}")
        
        automation = Automation.query.filter_by(portfolio_id=portfolio.id).first()
        
        if not automation:
            return jsonify({
                'status': 'not_found',
                'message': f'Portfolio exists but has no automation',
                'portfolio': {
                    'id': portfolio.id,
                    'portfolio_id': portfolio.portfolio_id,
                    'name': portfolio.name
                }
            }), 404
            
        current_app.logger.info(f"Found automation - ID: {automation.id}, Name: {automation.name}, Portfolio ID: {automation.portfolio_id}")
            
        return jsonify({
            'status': 'success',
            'automation': {
                'id': automation.id,
                'automation_id': automation.automation_id,
                'name': automation.name,
                'portfolio_id': automation.portfolio_id,
                'trading_pair': automation.trading_pair,
                'is_active': automation.is_active,
                'created_at': automation.created_at.isoformat() if automation.created_at else None
            },
            'portfolio': {
                'id': portfolio.id,
                'portfolio_id': portfolio.portfolio_id,
                'name': portfolio.name
            }
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500