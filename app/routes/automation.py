# app/routes/automation.py
from flask import Blueprint, request, jsonify, session, send_from_directory, render_template, redirect, url_for, flash, current_app
from flask_security import current_user, login_required 
from functools import wraps
from app import db
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from app.models.portfolio import Portfolio
from app.models.exchange_credentials import ExchangeCredentials
from app.forms.portfolio_api_key_form import PortfolioAPIKeyForm
from app.services.account_service import AccountService
from app.services.coinbase_service import CoinbaseService
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
        if not auth_header and not current_user.is_authenticated:
            # Check if the request prefers HTML (browser request)
            if request.accept_mimetypes.accept_html:
                # Use a special category for session expiration
                flash("Your session has expired. Please log in again.", "auth_expired")
                return redirect(url_for('security.login', next=request.path))
            else:
                # API request, return JSON response
                return jsonify({"error": "Unauthorized"}), 403
        return f(*args, **kwargs)
    return decorated_function


def get_user_automation(automation_id):
    """Helper function to get an automation for the current user"""
    return Automation.query.filter_by(
        automation_id=automation_id,
        user_id=current_user.id  # Use current_user.id instead of session
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
            
            # Skip deleted portfolios
            if deleted:
                continue

            # Log but include Default portfolio - we'll filter it at display time
            if portfolio_name and portfolio_name.lower() == 'default':
                logger.info(f"Found Default portfolio with ID: {portfolio_id}")
                # We don't continue here because we want to include it in the DB for completeness
                
            if not portfolio_id or not portfolio_name:
                continue
                
            # Check if portfolio exists in database
            db_portfolio = Portfolio.query.filter_by(
                user_id=user_id,
                portfolio_id=portfolio_id
            ).first()
            
            if not db_portfolio:
                # Create new portfolio
                db_portfolio = Portfolio(
                    portfolio_id=portfolio_id,
                    name=portfolio_name,
                    user_id=user_id
                )
                db.session.add(db_portfolio)
                db.session.commit()
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

# @bp.route('/static/js/components/WebhookLogs.jsx')
# def serve_component(filename):
#     root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
#     static_dir = os.path.join(root_dir, 'static', 'js', 'components')
#     return send_from_directory(static_dir, filename, mimetype='text/jsx')

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
        
        # Check if portfolio has valid credentials
        has_valid_credentials = False
        if portfolio:
            credentials = ExchangeCredentials.query.filter_by(
                portfolio_id=portfolio.id,
                exchange='coinbase'
            ).first()
            has_valid_credentials = credentials is not None
            portfolio.has_valid_credentials = has_valid_credentials
            
            # Only try to get portfolio value if credentials exist
            if has_valid_credentials:
                portfolio.value = AccountService.get_portfolio_value(current_user.id, portfolio.id)
    
    # For portfolio selection - only needed if no portfolio is connected yet
    portfolios = []
    selected_portfolio = None
    show_api_form = False
    
    if not portfolio:
        # Fetch portfolios from Coinbase
        portfolios = get_coinbase_portfolios(current_user.id)
        
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
    
    # Generate webhook URL using APPLICATION_URL if available
    webhook_url = None
    if current_app.config.get('APPLICATION_URL'):
        webhook_url = f"{current_app.config['APPLICATION_URL'].rstrip('/')}/webhook?automation_id={automation.automation_id}" if automation else None
    else:
        webhook_url = f"{request.url_root}webhook?automation_id={automation.automation_id}" if automation else None

    return render_template(
        'automation.html', 
        automation=automation,
        portfolio=portfolio,
        portfolios=portfolios,
        selected_portfolio=selected_portfolio,
        show_api_form=show_api_form,
        webhook_url=webhook_url 
    )


@bp.route('/automation/<automation_id>/create-portfolio', methods=['POST'])
@api_login_required
def create_portfolio(automation_id):
    try:
        logger.info(f"Starting portfolio creation for automation {automation_id}")
        data = request.get_json()
        portfolio_name = data.get('name')
        
        logger.info(f"Portfolio name from request: {portfolio_name}")
        
        if not portfolio_name:
            logger.error("Missing portfolio name in request")
            return jsonify({"error": "Portfolio name is required"}), 400
            
        # Try to find existing trading credentials (non-default)
        logger.info(f"Searching for trading credentials for user {current_user.id}")
        trading_creds = ExchangeCredentials.query.filter(
            ExchangeCredentials.user_id == current_user.id,
            ExchangeCredentials.exchange == 'coinbase',
            ExchangeCredentials.portfolio_name != 'default',
            ExchangeCredentials.is_default.is_(False)
        ).first()
        
        # Log credential status
        if trading_creds:
            logger.info(f"Found trading credentials: id={trading_creds.id}, portfolio={trading_creds.portfolio_name}")
        else:
            default_creds = ExchangeCredentials.query.filter(
                ExchangeCredentials.user_id == current_user.id,
                ExchangeCredentials.exchange == 'coinbase',
                ExchangeCredentials.portfolio_name == 'default'
            ).first()
            
            if default_creds:
                logger.info(f"User only has default credentials: id={default_creds.id}")
            else:
                logger.info("User has no credentials at all")
        
        if not trading_creds:
            logger.info("No trading credentials found, will require manual setup")
            # Check if user has non-default portfolios
            portfolios = get_coinbase_portfolios(current_user.id)
            # Filter out any portfolios named "Default"
            non_default_portfolios = [p for p in portfolios if p.get('name', '').lower() != 'default']
            has_portfolios = len(non_default_portfolios) > 0
            
            return jsonify({
                "success": False,
                "needs_manual_setup": True,
                "has_portfolios": has_portfolios
            }), 200
            
        # If we have trading credentials, attempt to create portfolio
        logger.info(f"Using trading credentials for {trading_creds.portfolio_name} to create portfolio")
        client = RESTClient(api_key=trading_creds.api_key, 
                          api_secret=trading_creds.decrypt_secret())
        
        logger.info(f"Calling Coinbase API to create portfolio: {portfolio_name}")
        response = client.create_portfolio(name=portfolio_name)
        logger.info(f"Create portfolio API response: {response}")
        
        # Handle the response correctly based on its structure
        portfolio_uuid = None
        
        # If response is a dictionary with a 'portfolio' key
        if isinstance(response, dict) and 'portfolio' in response:
            logger.info("Response is a dictionary with 'portfolio' key")
            portfolio_uuid = response['portfolio'].get('uuid')
            
        # If response is an object with a 'portfolio' attribute
        elif hasattr(response, 'portfolio'):
            logger.info("Response is an object with 'portfolio' attribute")
            portfolio_data = response.portfolio
            
            # Check if portfolio is a dict or object
            if isinstance(portfolio_data, dict):
                portfolio_uuid = portfolio_data.get('uuid')
            elif hasattr(portfolio_data, 'uuid'):
                portfolio_uuid = portfolio_data.uuid
                
        # Last resort - try to check if 'uuid' is directly in the response
        elif hasattr(response, 'uuid'):
            logger.info("Response has 'uuid' attribute directly")
            portfolio_uuid = response.uuid
            
        # Convert to dict as last resort
        else:
            try:
                response_dict = vars(response)
                logger.info(f"Converted response to dict: {response_dict}")
                
                if 'portfolio' in response_dict:
                    portfolio_data = response_dict['portfolio']
                    
                    if isinstance(portfolio_data, dict):
                        portfolio_uuid = portfolio_data.get('uuid')
                    elif hasattr(portfolio_data, 'uuid'):
                        portfolio_uuid = portfolio_data.uuid
            except:
                # Final attempt - try to access attributes directly
                try:
                    all_attrs = {attr: getattr(response, attr) for attr in dir(response) 
                               if not attr.startswith('_') and not callable(getattr(response, attr))}
                    logger.info(f"Response attributes: {all_attrs}")
                except Exception as e:
                    logger.error(f"Failed to inspect response attributes: {str(e)}")
        
        if not portfolio_uuid:
            logger.error("Failed to extract UUID from response")
            return jsonify({"error": "Could not extract portfolio UUID from response"}), 500
            
        logger.info(f"Successfully extracted portfolio UUID: {portfolio_uuid}")
        
        # Create portfolio record in database
        portfolio = Portfolio(
            portfolio_id=portfolio_uuid,
            name=portfolio_name,
            user_id=current_user.id,
            exchange='coinbase'
        )
        db.session.add(portfolio)
        db.session.commit()
        logger.info(f"Created portfolio record in database with ID: {portfolio.id}")
        
        return jsonify({
            "success": True,
            "portfolio": {
                "id": portfolio.id,
                "name": portfolio.name,
                "portfolio_id": portfolio.portfolio_id
            }
        })
            
    except Exception as e:
        logger.error(f"Error creating portfolio: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


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
            user_id=current_user.id,
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
        user_id=current_user.id,
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
            user_id=current_user.id,
            # Add trading pair if provided
            trading_pair=data.get('trading_pair')
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
            "template": template,
            "trading_pair": automation.trading_pair
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
        
        # Add handling for trading_pair updates
        if 'trading_pair' in data:
            automation.trading_pair = data['trading_pair']
            logger.info(f"Updated trading pair to {data['trading_pair']} for automation {automation_id}")
            
        db.session.commit()
        return jsonify({
            "success": True,
            "automation": {
                "id": automation.id,
                "name": automation.name,
                "trading_pair": automation.trading_pair
            }
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating automation: {e}")
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
    """Get webhook logs for a specific automation with pagination."""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        # Verify user has access to this automation
        automation = get_user_automation(automation_id)
        if not automation:
            return jsonify({"error": "Automation not found"}), 404
        
        # Get logs with pagination
        pagination = WebhookLog.query.filter_by(
            automation_id=automation_id
        ).order_by(WebhookLog.timestamp.desc()).paginate(page=page, per_page=per_page, error_out=False)
        
        return jsonify({
            'logs': [log.to_dict() for log in pagination.items],
            'pagination': {
                'page': pagination.page,
                'per_page': pagination.per_page,
                'total': pagination.total,
                'pages': pagination.pages,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev,
                'next_num': pagination.next_num,
                'prev_num': pagination.prev_num
            }
        })
    except Exception as e:
        logger.error(f"Error fetching automation logs: {e}")
        return jsonify({"error": str(e)}), 500

@bp.route('/debug/set-default-credentials')
@api_login_required
def set_default_credentials():
    try:
        # Find the credentials with portfolio_name='default'
        default_creds = ExchangeCredentials.query.filter_by(
            user_id=current_user.id,
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

@bp.route('/automation/<automation_id>/check-trading-credentials')
@api_login_required
def check_trading_credentials(automation_id):
    """Check if user has trading credentials before showing portfolio creation modal"""
    try:
        logger.info(f"Checking trading credentials for user {current_user.id}")
        
        # Try to find existing trading credentials that are:
        # 1. Not named 'default'
        # 2. is_default flag is False
        # 3. Has the necessary permissions for trading (implied by the above)
        trading_creds = ExchangeCredentials.query.filter(
            ExchangeCredentials.user_id == current_user.id,
            ExchangeCredentials.exchange == 'coinbase',
            ExchangeCredentials.portfolio_name != 'default',
            ExchangeCredentials.is_default.is_(False)
        ).first()
        
        # Check if user has default credentials (for viewing)
        default_creds = ExchangeCredentials.query.filter(
            ExchangeCredentials.user_id == current_user.id,
            ExchangeCredentials.exchange == 'coinbase',
            ExchangeCredentials.portfolio_name == 'default'
        ).first()
        
        # Log the credential status
        if trading_creds:
            logger.info(f"Found trading credentials: id={trading_creds.id}, portfolio_name={trading_creds.portfolio_name}")
        elif default_creds:
            logger.info("User only has default credentials, needs to create trading credentials")
        else:
            logger.info("User has no credentials at all")
        
        # If no trading credentials, guide user through setup
        if not trading_creds:
            logger.info("No trading credentials found, returning setup instructions")
            
            # Check if user has non-default portfolios
            portfolios = get_coinbase_portfolios(current_user.id)
            # Filter out any portfolios named "Default"
            non_default_portfolios = [p for p in portfolios if p.get('name', '').lower() != 'default']
            has_portfolios = len(non_default_portfolios) > 0
            
            return jsonify({
                "success": False,
                "needs_manual_setup": True,
                "has_portfolios": has_portfolios
            }), 200

        logger.info("Trading credentials found, user can create portfolio")
        return jsonify({
            "success": True,
            "has_trading_credentials": True
        }), 200

    except Exception as e:
        logger.error(f"Error checking trading credentials: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500


@bp.route('/automation/<automation_id>/trading-pair', methods=['POST'])
@api_login_required
def set_trading_pair(automation_id):
    try:
        automation = get_user_automation(automation_id)
        if not automation:
            return jsonify({"error": "Automation not found"}), 404
            
        data = request.get_json()
        if not data or 'trading_pair' not in data:
            return jsonify({"error": "Missing required field: trading_pair"}), 400
            
        trading_pair = data['trading_pair']
        
        # Validate trading pair format (optional) - simple validation
        if not isinstance(trading_pair, str) or '-' not in trading_pair:
            return jsonify({
                "error": "Invalid trading pair format. Expected format: BTC-USD"
            }), 400
            
        # Update the automation with the trading pair
        automation.trading_pair = trading_pair
        db.session.commit()
        
        logger.info(f"Set trading pair to {trading_pair} for automation {automation_id}")
        
        return jsonify({
            "success": True,
            "message": f"Trading pair updated to {trading_pair}",
            "automation": {
                "id": automation.id,
                "name": automation.name,
                "trading_pair": automation.trading_pair
            }
        })
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error setting trading pair: {e}")
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
            user_id=current_user.id
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
            user_id=current_user.id
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
                user_id=current_user.id,
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
    
@bp.route('/debug/account-data/<portfolio_id>')
@api_login_required
def debug_account_data(portfolio_id):
    """Debug endpoint to check account data for a portfolio"""
    try:
        # Convert portfolio_id to integer if it's a string
        if isinstance(portfolio_id, str) and portfolio_id.isdigit():
            portfolio_id = int(portfolio_id)
            
        # Get the Portfolio object for reference
        portfolio = Portfolio.query.get(portfolio_id)
        
        # Get accounts from AccountService
        accounts = AccountService.get_accounts(
            user_id=current_user.id,
            portfolio_id=portfolio_id,
            force_refresh=True  # Force refresh to get latest data
        )
        
        # Prepare account information for display
        account_data = []
        for acct in accounts:
            account_data.append({
                'id': acct.id,
                'account_id': acct.account_id,
                'name': acct.name,
                'currency_code': acct.currency_code,
                'balance_amount': acct.balance_amount,
                'available_amount': acct.available_amount,
                'hold_amount': acct.hold_amount,
                'last_cached_at': acct.last_cached_at.isoformat() if acct.last_cached_at else None
            })
        
        # Calculate portfolio value
        portfolio_value = AccountService.get_portfolio_value(
            user_id=current_user.id,
            portfolio_id=portfolio_id
        )
        
        # Return debug information
        return jsonify({
            'portfolio': {
                'id': portfolio.id if portfolio else None,
                'name': portfolio.name if portfolio else None, 
                'portfolio_id': portfolio.portfolio_id if portfolio else None
            },
            'portfolio_value': portfolio_value,
            'account_count': len(accounts),
            'accounts': account_data
        })
    except Exception as e:
        logger.error(f"Error debugging account data: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@bp.route('/debug/direct-balance/<portfolio_uuid>')
@api_login_required
def debug_direct_balance(portfolio_uuid):
    """Debug endpoint to check direct account balance for a portfolio"""
    try:
        # Try to find portfolio by UUID first
        portfolio = Portfolio.query.filter_by(
            portfolio_id=portfolio_uuid,
            user_id=current_user.id
        ).first()
        
        if not portfolio:
            return jsonify({
                "error": f"Portfolio with UUID {portfolio_uuid} not found"
            }), 404
            
        # Now we have the database ID to use
        portfolio_id = portfolio.id
        
        # Get appropriate credentials
        creds = ExchangeCredentials.query.filter_by(
            user_id=current_user.id,
            portfolio_id=portfolio_id,
            exchange='coinbase'
        ).first()
        
        if not creds:
            return jsonify({
                "error": "No credentials found for this portfolio",
                "portfolio": {
                    "id": portfolio.id,
                    "name": portfolio.name,
                    "portfolio_id": portfolio.portfolio_id
                }
            })
        
        logger.info(f"Using credentials: id={creds.id}, portfolio_name={creds.portfolio_name}")
        
        # Get direct balance
        balance = CoinbaseService.get_portfolio_balance(
            user_id=current_user.id,
            portfolio_id=portfolio_id
        )
        
        # Return debug information
        return jsonify({
            'portfolio': {
                'id': portfolio.id,
                'name': portfolio.name, 
                'portfolio_id': portfolio.portfolio_id
            },
            'credentials': {
                'id': creds.id,
                'portfolio_name': creds.portfolio_name,
                'has_api_key': bool(creds.api_key),
                'has_api_secret': bool(creds.api_secret)
            },
            'direct_balance': balance
        })
    except Exception as e:
        logger.error(f"Error getting direct balance: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500
    
@bp.route('/debug/portfolio-value/<portfolio_uuid>')
@api_login_required
def debug_portfolio_value(portfolio_uuid):
    """Debug endpoint to check portfolio value using the breakdown API"""
    try:
        # Find portfolio by UUID
        portfolio = Portfolio.query.filter_by(
            portfolio_id=portfolio_uuid,
            user_id=current_user.id
        ).first()
        
        if not portfolio:
            return jsonify({
                "error": f"Portfolio with UUID {portfolio_uuid} not found"
            }), 404
            
        # Find credentials specifically for this portfolio
        creds = ExchangeCredentials.query.filter_by(
            user_id=current_user.id,
            portfolio_id=portfolio.id,
            exchange='coinbase'
        ).first()
        
        if not creds:
            return jsonify({
                "error": "No credentials found for this portfolio",
                "portfolio": {
                    "id": portfolio.id,
                    "name": portfolio.name,
                    "portfolio_id": portfolio.portfolio_id
                }
            })
        
        # Create client with these specific credentials
        client = CoinbaseService.get_client_from_credentials(creds)
        if not client:
            return jsonify({"error": "Failed to create Coinbase client"})
        
        # Get portfolio breakdown
        try:
            breakdown = client.get_portfolio_breakdown(portfolio_uuid=portfolio_uuid)
            
            # Try to extract total value
            total_value = 0.0
            
            if hasattr(breakdown, 'breakdown') and hasattr(breakdown.breakdown, 'portfolio_balances'):
                balances = breakdown.breakdown.portfolio_balances
                if hasattr(balances, 'total_balance') and hasattr(balances.total_balance, 'value'):
                    total_value_str = balances.total_balance.value
                    total_value = float(total_value_str)
            elif isinstance(breakdown, dict) and 'breakdown' in breakdown:
                breakdown_data = breakdown['breakdown']
                if 'portfolio_balances' in breakdown_data:
                    balances = breakdown_data['portfolio_balances']
                    if 'total_balance' in balances and 'value' in balances['total_balance']:
                        total_value_str = balances['total_balance']['value']
                        total_value = float(total_value_str)
            
            return jsonify({
                'portfolio': {
                    'id': portfolio.id,
                    'name': portfolio.name, 
                    'portfolio_id': portfolio.portfolio_id
                },
                'credentials_used': {
                    'id': creds.id,
                    'portfolio_name': creds.portfolio_name
                },
                'portfolio_value': total_value,
                'raw_response': str(breakdown)[:1000]  # Truncate for readability
            })
        except Exception as e:
            return jsonify({
                "error": f"Error calling get_portfolio_breakdown: {str(e)}",
                "portfolio_uuid": portfolio_uuid,
                "credentials_used": {
                    'id': creds.id,
                    'portfolio_name': creds.portfolio_name
                }
            })
    except Exception as e:
        logger.error(f"Error getting portfolio value: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500

    
@bp.route('/debug/portfolio-breakdown/<portfolio_uuid>')
@api_login_required
def debug_portfolio_breakdown(portfolio_uuid):
    """Debug endpoint to show the raw portfolio breakdown response"""
    try:
        # Get credentials for this user
        creds = ExchangeCredentials.query.filter_by(
            user_id=current_user.id,
            exchange='coinbase'
        ).first()
        
        if not creds:
            return jsonify({"error": "No API credentials found"})
        
        # Create client
        client = CoinbaseService.get_client_from_credentials(creds)
        if not client:
            return jsonify({"error": "Failed to create Coinbase client"})
        
        # Get portfolio breakdown
        try:
            breakdown = client.get_portfolio_breakdown(portfolio_uuid=portfolio_uuid)
            
            # Inspect the response
            response_info = {
                "type": str(type(breakdown)),
                "attrs": dir(breakdown) if hasattr(breakdown, "__dir__") else None,
                "dict": vars(breakdown) if hasattr(breakdown, "__dict__") else None
            }
            
            # Try to extract the breakdown data
            breakdown_data = None
            if hasattr(breakdown, 'breakdown'):
                breakdown_data = breakdown.breakdown
                response_info["extraction_method"] = "breakdown attribute"
            elif isinstance(breakdown, dict) and 'breakdown' in breakdown:
                breakdown_data = breakdown['breakdown']
                response_info["extraction_method"] = "breakdown dict key"
            
            # Convert breakdown_data to a serializable form
            serializable_breakdown = None
            if breakdown_data:
                if isinstance(breakdown_data, dict):
                    serializable_breakdown = breakdown_data
                else:
                    try:
                        # Try to convert to dict
                        serializable_breakdown = vars(breakdown_data)
                    except:
                        # If that fails, try a custom approach
                        try:
                            serializable_breakdown = {
                                "portfolio": {
                                    "name": getattr(breakdown_data, "name", None),
                                    "uuid": getattr(breakdown_data, "uuid", None),
                                    "type": getattr(breakdown_data, "type", None),
                                    "deleted": getattr(breakdown_data, "deleted", None)
                                }
                            }
                            
                            # Try to extract portfolio_balances
                            balances = getattr(breakdown_data, "portfolio_balances", None)
                            if balances:
                                serializable_breakdown["portfolio_balances"] = {}
                                
                                # Extract total_balance
                                total_balance = getattr(balances, "total_balance", None)
                                if total_balance:
                                    serializable_breakdown["portfolio_balances"]["total_balance"] = {
                                        "value": getattr(total_balance, "value", None),
                                        "currency": getattr(total_balance, "currency", None)
                                    }
                        except Exception as e:
                            response_info["custom_extraction_error"] = str(e)
            
            return jsonify({
                "portfolio_uuid": portfolio_uuid,
                "response_info": response_info,
                "breakdown": serializable_breakdown
            })
        except Exception as e:
            return jsonify({
                "error": f"Error calling get_portfolio_breakdown: {str(e)}",
                "portfolio_uuid": portfolio_uuid
            })
            
    except Exception as e:
        logger.error(f"Error in debug_portfolio_breakdown: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500
    
@bp.route('/test-route/<automation_id>')
def test_automation_route(automation_id):
    return f"Automation ID: {automation_id}"