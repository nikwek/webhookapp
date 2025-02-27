# app/routes/automation.py
from flask import Blueprint, request, jsonify, session, send_from_directory, render_template, redirect, url_for, flash
from flask_login import current_user, login_required
from functools import wraps
from app import db
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from app.models.portfolio import Portfolio
from app.models.exchange_credentials import ExchangeCredentials
from app.forms.portfolio_api_key_form import PortfolioAPIKeyForm
from coinbase.rest import RESTClient
from sqlalchemy import inspect
import os
import logging

logger = logging.getLogger(__name__)
bp = Blueprint('automation', __name__)

def api_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.environ.get('HTTP_AUTHORIZATION')
        if not auth_header and not session.get('user_id'):
            return jsonify({"error": "Unauthorized"}), 403
        return f(*args, **kwargs)
    return decorated_function

def get_user_automation(automation_id):
    """Helper function to get an automation for the current user"""
    return Automation.query.filter_by(
        automation_id=automation_id,
        user_id=session['user_id']
    ).first()

def get_coinbase_portfolios(user_id):
    """Helper function to get portfolios directly from Coinbase using the SDK"""
    portfolios = []
    
    logger.info(f"Getting portfolios for user {user_id}")
    
    # Try to get any credentials for this user instead of just default ones
    default_creds = ExchangeCredentials.query.filter_by(
        user_id=user_id,
        exchange='coinbase'
    ).first()
    
    if not default_creds:
        logger.warning(f"No API credentials found for user {user_id}")
        flash("No API credentials found. Please set up your Coinbase API credentials first.", "warning")
        return portfolios
    
    logger.info(f"Found credentials for user {user_id}: portfolio_name={default_creds.portfolio_name}, is_default={default_creds.is_default}")
    
    try:
        # Get the API key and secret
        api_key = default_creds.api_key
        logger.info(f"Got API key: {api_key[:5]}...{api_key[-5:] if len(api_key) > 10 else ''}")
        
        api_secret = default_creds.decrypt_secret()
        logger.info(f"Successfully decrypted API secret")
        
        # Initialize REST client
        logger.info(f"Initializing Coinbase REST client")
        client = RESTClient(api_key=api_key, api_secret=api_secret)
        
        # Get portfolios from Coinbase
        logger.info(f"Fetching portfolios from Coinbase API")
        response = client.get_portfolios()
        
        # Log the response type and structure
        logger.info(f"API Response type: {type(response)}")
        
        # Handle the ListPortfoliosResponse object
        if hasattr(response, 'portfolios'):
            # If it's an object with a portfolios attribute
            portfolios_list = response.portfolios
            logger.info(f"Found {len(portfolios_list)} portfolios using .portfolios attribute")
        elif isinstance(response, dict) and 'portfolios' in response:
            # If it's a dictionary with portfolios key
            portfolios_list = response['portfolios']
            logger.info(f"Found {len(portfolios_list)} portfolios from response dictionary")
        else:
            # Try to convert the response to a dict if it's a custom object
            try:
                response_dict = vars(response)
                if 'portfolios' in response_dict:
                    portfolios_list = response_dict['portfolios']
                    logger.info(f"Found {len(portfolios_list)} portfolios using vars(response)")
                else:
                    logger.warning(f"Could not find portfolios in response: {response_dict}")
                    return portfolios
            except Exception as e:
                logger.warning(f"Error converting response to dict: {str(e)}")
                if hasattr(response, '__dict__'):
                    logger.info(f"Response __dict__: {response.__dict__}")
                # Last resort: try to iterate over the response object directly
                try:
                    portfolios_list = list(response)
                    logger.info(f"Treating response as iterable, found {len(portfolios_list)} items")
                except Exception as e:
                    logger.warning(f"Cannot iterate over response: {str(e)}")
                    return portfolios
        
        # Process each portfolio
        for p in portfolios_list:
            logger.info(f"Processing portfolio item: {p}")
            
            # Check if p is a dict or an object
            if isinstance(p, dict):
                portfolio_id = p.get('uuid')
                portfolio_name = p.get('name')
                deleted = p.get('deleted', False)
            else:
                # Try to access attributes
                portfolio_id = getattr(p, 'uuid', None)
                portfolio_name = getattr(p, 'name', None)
                deleted = getattr(p, 'deleted', False)
            
            # Skip deleted portfolios and Default portfolio
            if deleted or portfolio_name == 'Default':
                logger.info(f"Skipping portfolio {portfolio_name} (deleted={deleted})")
                continue
                
            if not portfolio_id or not portfolio_name:
                logger.warning(f"Missing portfolio ID or name in portfolio object")
                continue
                
            logger.info(f"Processing portfolio: {portfolio_name} ({portfolio_id})")
                
            # Check if portfolio exists in database
            db_portfolio = Portfolio.query.filter_by(
                user_id=user_id,
                portfolio_id=portfolio_id
            ).first()
            
            if not db_portfolio:
                # Create new portfolio
                logger.info(f"Creating new portfolio record for {portfolio_name}")
                db_portfolio = Portfolio(
                    portfolio_id=portfolio_id,
                    name=portfolio_name,
                    user_id=user_id
                )
                db.session.add(db_portfolio)
                db.session.commit()
                logger.info(f"Created portfolio with ID: {db_portfolio.id}")
            else:
                logger.info(f"Found existing portfolio record with ID: {db_portfolio.id}")
            
            portfolios.append({
                'id': db_portfolio.id,
                'name': db_portfolio.name
            })
            
        logger.info(f"Returning {len(portfolios)} portfolios")
                
    except Exception as e:
        logger.error(f"Error fetching portfolios from Coinbase: {str(e)}", exc_info=True)
        flash(f"Error fetching portfolios: {str(e)}", "danger")
    
    return portfolios

@bp.route('/static/js/components/WebhookLogs.jsx')
def serve_component(filename):
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_dir = os.path.join(root_dir, 'static', 'js', 'components')
    return send_from_directory(static_dir, filename, mimetype='text/jsx')

# UI Routes
@bp.route('/automation/new', methods=['GET'])
@api_login_required
def new_automation():
    return render_template('automation.html', automation=None)

@bp.route('/automation/<automation_id>', methods=['GET'])
@api_login_required
def view_automation(automation_id):
    automation = get_user_automation(automation_id)
    if not automation:
        return render_template('404.html'), 404
    
    # Get portfolio information if connected
    portfolio = None
    if automation.portfolio_id:
        portfolio = Portfolio.query.get(automation.portfolio_id)
    
    # For portfolio selection - only needed if no portfolio is connected yet
    portfolios = []
    selected_portfolio = None
    show_api_form = False
    
    if not portfolio:
        # Fetch portfolios from Coinbase
        portfolios = get_coinbase_portfolios(session['user_id'])
        
        # Check if portfolio was just selected
        if 'selected_portfolio_id' in session:
            portfolio_id = session.pop('selected_portfolio_id')
            try:
                portfolio_id = int(portfolio_id)  # Convert to int for comparison
                for p in portfolios:
                    if p['id'] == portfolio_id:
                        selected_portfolio = p
                        show_api_form = True
                        break
            except (ValueError, TypeError):
                pass
    
    return render_template(
        'automation.html', 
        automation=automation,
        portfolio=portfolio,
        portfolios=portfolios,
        selected_portfolio=selected_portfolio,
        show_api_form=show_api_form
    )

@bp.route('/automation/<automation_id>/select-portfolio', methods=['POST'])
@api_login_required
def select_portfolio(automation_id):
    automation = get_user_automation(automation_id)
    if not automation:
        return render_template('404.html'), 404
    
    portfolio_id = request.form.get('portfolio_id')
    if not portfolio_id:
        flash("Please select a portfolio", "warning")
        return redirect(url_for('automation.view_automation', automation_id=automation_id))
    
    # Store selected portfolio in session
    session['selected_portfolio_id'] = portfolio_id
    
    return redirect(url_for('automation.view_automation', automation_id=automation_id))

@bp.route('/automation/<automation_id>/save-api-keys', methods=['POST'])
@api_login_required
def save_api_keys(automation_id):
    automation = get_user_automation(automation_id)
    if not automation:
        return render_template('404.html'), 404
    
    portfolio_id = request.form.get('portfolio_id')
    portfolio_name = request.form.get('portfolio_name')
    api_key = request.form.get('api_key')
    api_secret = request.form.get('api_secret')
    
    if not all([portfolio_id, portfolio_name, api_key, api_secret]):
        flash("All fields are required", "danger")
        return redirect(url_for('automation.view_automation', automation_id=automation_id))
    
    try:
        # Get the Portfolio object
        portfolio = Portfolio.query.get(portfolio_id)
        if not portfolio:
            flash("Portfolio not found", "danger")
            return redirect(url_for('automation.view_automation', automation_id=automation_id))
        
        # Validate the API keys by making a test request
        client = RESTClient(api_key=api_key, api_secret=api_secret)
        test_response = client.get_accounts()
        
        # Create the credentials entry
        credentials = ExchangeCredentials(
            user_id=session['user_id'],
            exchange='coinbase',
            portfolio_name=portfolio.name,
            api_key=api_key,
            api_secret=api_secret,
            automation_id=automation.id,
            portfolio_id=portfolio.id
        )
        
        db.session.add(credentials)
        
        # Update automation to link to portfolio
        automation.portfolio_id = portfolio.id
        
        db.session.commit()
        
        flash(f"Successfully connected automation to portfolio {portfolio.name}", "success")
        return redirect(url_for('automation.view_automation', automation_id=automation_id))
        
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error saving API keys: {str(e)}")
        flash(f"Error saving API keys: {str(e)}", "danger")
        return redirect(url_for('automation.view_automation', automation_id=automation_id))

@bp.route('/automation/<automation_id>/disconnect-portfolio', methods=['POST'])
@api_login_required
def disconnect_portfolio(automation_id):
    automation = get_user_automation(automation_id)
    if not automation:
        return render_template('404.html'), 404
    
    # Remove credentials associated with this automation
    credentials = ExchangeCredentials.query.filter_by(
        user_id=session['user_id'],
        automation_id=automation.id
    ).all()
    
    for cred in credentials:
        db.session.delete(cred)
    
    # Unlink portfolio from automation
    automation.portfolio_id = None
    
    db.session.commit()
    
    flash("Portfolio disconnected successfully", "success")
    return redirect(url_for('automation.view_automation', automation_id=automation_id))

# API Routes
@bp.route('/automation', methods=['POST'])
@api_login_required
def create_automation():
    try:
        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({"error": "Missing required field: name"}), 400
            
        automation = Automation(
            automation_id=Automation.generate_automation_id(),
            name=data.get('name'),
            user_id=session['user_id']
        )
        db.session.add(automation)
        
        template = {
            "action": "{{strategy.order.action}}",
            "ticker": "{{ticker}}",
            "order_size": "100%",
            "position_size": "{{strategy.position_size}}",
            "schema": "2",
            "timestamp": "{{time}}"
        }
        
        automation.template = template
        db.session.commit()
        
        return jsonify({
            "automation_id": automation.automation_id,
            "webhook_url": f"{request.url_root}webhook?automation_id={automation.automation_id}",
            "template": template
        })
    except Exception as e:
        logger.error(f"Error creating automation: {e}")
        db.session.rollback()
        return jsonify({"error": "Failed to create automation"}), 500

@bp.route('/automation/<automation_id>', methods=['PUT'])
@api_login_required
def update_automation(automation_id):
    try:
        automation = get_user_automation(automation_id)
        if not automation:
            return jsonify({"error": "Automation not found"}), 404
            
        data = request.get_json()
        if 'name' in data:
            automation.name = data['name']
            
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@bp.route('/automation/<automation_id>/status', methods=['PUT'])
@api_login_required
def update_automation_status(automation_id):
    try:
        automation = get_user_automation(automation_id)
        if not automation:
            return jsonify({"error": "Automation not found"}), 404
            
        data = request.get_json()
        if 'is_active' in data:
            automation.is_active = data['is_active']
            
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@bp.route('/automation/<automation_id>', methods=['DELETE'])
@api_login_required
def delete_automation(automation_id):
    try:
        automation = get_user_automation(automation_id)
        if not automation:
            return jsonify({"error": "Automation not found"}), 404
            
        db.session.delete(automation)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
    
@bp.route('/automation/<automation_id>/logs')
@api_login_required
def get_automation_logs(automation_id):
    """Get webhook logs for a specific automation."""
    try:
        # Verify user has access to this automation
        automation = get_user_automation(automation_id)
        if not automation:
            return jsonify({"error": "Automation not found"}), 404
        
        logs = WebhookLog.query.filter_by(
            automation_id=automation_id
        ).order_by(WebhookLog.timestamp.desc()).limit(100).all()
        
        return jsonify([log.to_dict() for log in logs])
    except Exception as e:
        logger.error(f"Error fetching automation logs: {e}")
        return jsonify({"error": str(e)}), 500

# Debug Routes
@bp.route('/debug/schema')
@api_login_required
def debug_schema():
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
            
        return jsonify(tables)
    except Exception as e:
        logger.error(f"Error in debug_schema: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)})

@bp.route('/debug/credentials')
@api_login_required
def debug_credentials():
    try:
        credentials = ExchangeCredentials.query.filter_by(
            user_id=session['user_id']
        ).all()
        
        creds_list = []
        for cred in credentials:
            creds_list.append({
                'id': cred.id,
                'portfolio_name': cred.portfolio_name,
                'is_default': cred.is_default,
                'automation_id': cred.automation_id,
                'portfolio_id': cred.portfolio_id,
                'api_key_preview': f"{cred.api_key[:5]}...{cred.api_key[-5:] if len(cred.api_key) > 10 else ''}"
            })
            
        return jsonify(creds_list)
    except Exception as e:
        logger.error(f"Error in debug_credentials: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)})

@bp.route('/debug/portfolios')
@api_login_required
def debug_portfolios():
    try:
        # Get all portfolios in the database
        db_portfolios = Portfolio.query.filter_by(
            user_id=session['user_id']
        ).all()
        
        portfolio_list = []
        for p in db_portfolios:
            portfolio_list.append({
                'id': p.id,
                'portfolio_id': p.portfolio_id,
                'name': p.name,
                'exchange': p.exchange
            })
        
        # Try to fetch portfolios directly from Coinbase
        portfolios_from_coinbase = []
        api_response_info = {}
        
        try:
            # Try to get any credentials
            cred = ExchangeCredentials.query.filter_by(
                user_id=session['user_id'],
                exchange='coinbase'
            ).first()
            
            if cred:
                api_key = cred.api_key
                api_secret = cred.decrypt_secret()
                
                client = RESTClient(api_key=api_key, api_secret=api_secret)
                response = client.get_portfolios()
                
                # Store information about the response
                api_response_info['type'] = str(type(response))
                api_response_info['dir'] = dir(response)
                
                if hasattr(response, 'portfolios'):
                    # It's an object with a portfolios attribute
                    portfolio_objects = response.portfolios
                    api_response_info['access_method'] = 'attribute'
                elif isinstance(response, dict) and 'portfolios' in response:
                    # It's a dictionary with portfolios key
                    portfolio_objects = response['portfolios']
                    api_response_info['access_method'] = 'dict_key'
                else:
                    # Try to convert to dict
                    try:
                        response_dict = vars(response)
                        api_response_info['vars'] = response_dict
                        if 'portfolios' in response_dict:
                            portfolio_objects = response_dict['portfolios']
                            api_response_info['access_method'] = 'vars'
                        else:
                            portfolio_objects = []
                            api_response_info['error'] = 'No portfolios in vars(response)'
                    except:
                        # Try to iterate
                        try:
                            portfolio_objects = list(response)
                            api_response_info['access_method'] = 'iterate'
                        except:
                            portfolio_objects = []
                            api_response_info['error'] = 'Cannot iterate over response'
                
                # Try to convert each portfolio to a dict
                for p in portfolio_objects:
                    if isinstance(p, dict):
                        portfolios_from_coinbase.append(p)
                    else:
                        try:
                            # Try to get all attributes
                            p_dict = {attr: getattr(p, attr) for attr in dir(p) 
                                     if not callable(getattr(p, attr)) and not attr.startswith('_')}
                            portfolios_from_coinbase.append(p_dict)
                        except Exception as e:
                            portfolios_from_coinbase.append({
                                'object': str(p),
                                'error': str(e)
                            })
        except Exception as e:
            api_response_info['error'] = str(e)
            
        return jsonify({
            'database_portfolios': portfolio_list,
            'coinbase_portfolios': portfolios_from_coinbase,
            'api_response_info': api_response_info
        })
    except Exception as e:
        logger.error(f"Error in debug_portfolios: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)})

@bp.route('/debug/set-default-credentials')
@api_login_required
def set_default_credentials():
    try:
        # Find the credentials with portfolio_name='default'
        default_creds = ExchangeCredentials.query.filter_by(
            user_id=session['user_id'],
            exchange='coinbase',
            portfolio_name='default'
        ).first()
        
        if default_creds:
            # Set is_default to True
            default_creds.is_default = True
            db.session.commit()
            return jsonify({"success": True, "message": "Default credentials updated"})
        else:
            return jsonify({"success": False, "message": "No default credentials found"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)})
