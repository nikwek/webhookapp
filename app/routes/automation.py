# app/routes/automation.py
from flask import Blueprint, request, jsonify, session, send_from_directory, render_template, redirect, url_for, flash, current_app
from flask_security import current_user, login_required 
from functools import wraps
from app import db
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from app.models.portfolio import Portfolio
from app.models.exchange_credentials import ExchangeCredentials
from app.exchanges.registry import ExchangeRegistry
from app.exchanges.base_adapter import InvalidApiKeyError, TemporaryExchangeError # Ensure these are correct exception classes
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

    portfolio = None
    portfolio_status = 'disconnected' # Default status

    if automation.portfolio_id:
        portfolio = Portfolio.query.get(automation.portfolio_id)

        if portfolio:
            if not portfolio.exchange:
                current_app.logger.error(f"Portfolio {portfolio.id} (automation {automation_id}) is missing an exchange type.")
                portfolio_status = 'error_misconfigured_portfolio'
            else:
                credential = ExchangeCredentials.query.filter_by(
                    user_id=current_user.id,
                    portfolio_id=portfolio.id
                ).first()

                if credential and credential.exchange != portfolio.exchange:
                    current_app.logger.warning(
                        f"Portfolio {portfolio.id} (type {portfolio.exchange}) has credential {credential.id} "
                        f"for a different exchange ({credential.exchange}). Automation: {automation_id}. Treating as misconfigured."
                    )
                    portfolio_status = 'error_misconfigured_credential_mismatch'
                    credential = None

                has_valid_credentials = credential is not None

                if has_valid_credentials:
                    if portfolio.invalid_credentials or (hasattr(credential, 'is_valid') and not credential.is_valid):
                        portfolio_status = 'invalid_known_bad_keys'
                    else:
                        try:
                            adapter = ExchangeRegistry.get_adapter(portfolio.exchange)
                            portfolio_data = adapter.get_portfolio_value(
                                user_id=current_user.id, 
                                portfolio_id=portfolio.id,
                                credential_id=credential.id
                            )
                            
                            portfolio_value_usd = portfolio_data.get('total_value_usd')

                            if portfolio_value_usd is not None:
                                if hasattr(portfolio, 'value'): # Check if attribute exists before setting
                                    portfolio.value = portfolio_value_usd
                                if portfolio_value_usd > 0:
                                    portfolio_status = 'connected'
                                else:
                                    portfolio_status = 'empty'
                            else:
                                current_app.logger.warning(
                                    f"Portfolio data for {portfolio.id} on {portfolio.exchange} (cred: {credential.id}) "
                                    f"missing 'total_value_usd'. Data: {portfolio_data}. Automation: {automation_id}."
                                )
                                portfolio_status = 'error_missing_value_data'

                        except InvalidApiKeyError:
                            current_app.logger.warning(
                                f"Invalid API key for portfolio {portfolio.id} (credential {credential.id}) "
                                f"on exchange {portfolio.exchange}. Automation: {automation_id}."
                            )
                            portfolio_status = 'invalid_api_key'
                            portfolio.invalid_credentials = True
                            if hasattr(credential, 'is_valid'):
                                credential.is_valid = False
                                db.session.add(credential)
                            db.session.commit()
                        except TemporaryExchangeError as e:
                            current_app.logger.error(
                                f"Temporary exchange error for portfolio {portfolio.id} on {portfolio.exchange} "
                                f"(cred: {credential.id}). Automation: {automation_id}. Error: {str(e)}"
                            )
                            portfolio_status = 'error_exchange_down'
                        except Exception as e:
                            current_app.logger.error(
                                f"Error verifying portfolio access for {portfolio.id} on {portfolio.exchange} "
                                f"(cred: {credential.id}). Automation: {automation_id}. Error: {str(e)}", exc_info=True
                            )
                            portfolio_status = 'error_general_verification'
                else:
                    portfolio_status = 'disconnected_no_credentials'
        else:
            current_app.logger.error(f"Portfolio with ID {automation.portfolio_id} not found for automation {automation_id}.")
            portfolio_status = 'error_portfolio_not_found'
    
    webhook_url = None
    if current_app.config.get('APPLICATION_URL'):
        webhook_url = f"{current_app.config['APPLICATION_URL'].rstrip('/')}/webhook?automation_id={automation.automation_id}" if automation else None
    else:
        webhook_url = f"{request.url_root}webhook?automation_id={automation.automation_id}" if automation else None
        
    return render_template(
        'automation.html', 
        automation=automation,
        portfolio=portfolio,
        portfolio_status=portfolio_status,
        webhook_url=webhook_url
    )


@bp.route('/automation/<automation_id>/create-portfolio', methods=['POST'])
@api_login_required
def create_portfolio(automation_id):
    try:
        logger.info(f"Starting portfolio creation for automation {automation_id}")
        data = request.get_json()
        portfolio_name = data.get('name')
        exchange = data.get('exchange', 'coinbase')  # Default to coinbase if not specified
        
        logger.info(f"Portfolio name from request: {portfolio_name}, exchange: {exchange}")
        
        if not portfolio_name:
            logger.error("Missing portfolio name in request")
            return jsonify({"error": "Portfolio name is required"}), 400
            
        if not exchange:
            logger.error("Missing exchange in request")
            return jsonify({"error": "Exchange is required"}), 400
            
        # Try to find existing trading credentials (non-default)
        logger.info(f"Searching for trading credentials for user {current_user.id} for exchange {exchange}")
        trading_creds = ExchangeCredentials.query.filter(
            ExchangeCredentials.user_id == current_user.id,
            ExchangeCredentials.exchange == exchange,
            ExchangeCredentials.portfolio_name != 'default',
            ExchangeCredentials.is_default.is_(False)
        ).first()
        
        # Log credential status
        if trading_creds:
            logger.info(f"Found trading credentials: id={trading_creds.id}, portfolio={trading_creds.portfolio_name}")
        else:
            default_creds = ExchangeCredentials.query.filter(
                ExchangeCredentials.user_id == current_user.id,
                ExchangeCredentials.exchange == exchange,
                ExchangeCredentials.portfolio_name == 'default'
            ).first()
            
            if default_creds:
                logger.info(f"User only has default credentials: id={default_creds.id}")
            else:
                logger.info("User has no credentials at all")
        
        if not trading_creds:
            logger.info("No trading credentials found, will require manual setup")
            # User needs to set up credentials via the Exchange Settings page.
            return jsonify({
                "success": False,
                "needs_manual_setup": True
                # "has_portfolios" key removed as it relied on native Coinbase logic
            }), 200
            
        # If we have trading credentials, attempt to create portfolio
        logger.info(f"Using trading credentials for {trading_creds.portfolio_name} to create portfolio")
        
        # Different API clients for different exchanges
        if exchange == 'coinbase':
            client = RESTClient(api_key=trading_creds.api_key, 
                               api_secret=trading_creds.decrypt_secret())
            
            logger.info(f"Calling Coinbase API to create portfolio: {portfolio_name}")
            response = client.create_portfolio(name=portfolio_name)
            logger.info(f"Create portfolio API response: {response}")
        else:
            # For future exchanges, add their API client code here
            logger.error(f"Exchange {exchange} not supported for portfolio creation yet")
            return jsonify({"error": f"Exchange {exchange} not supported for portfolio creation yet"}), 400
        
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
            exchange=exchange  # Use the dynamic exchange parameter
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

@bp.route('/<automation_id>/save-api-keys', methods=['POST'])
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
        
        # ADD THIS: Reset invalid credentials flag on the portfolio
        if portfolio.invalid_credentials:
            portfolio.reset_invalid_flag()  # This calls the method that resets the flag and commits
        
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
        # Get the automation and verify ownership
        automation = get_user_automation(automation_id)
        if not automation:
            logger.warning(f"Deletion attempt for non-existent automation: {automation_id}")
            return jsonify({"error": "Automation not found", "success": False}), 404
            
        logger.info(f"Deleting automation {automation_id} ({automation.name})")
        
        # 1. Delete related webhook logs first
        logs_count = WebhookLog.query.filter_by(automation_id=automation_id).delete()
        logger.info(f"Deleted {logs_count} webhook logs for automation {automation_id}")
        
        # 2. Delete or update related exchange credentials
        creds = ExchangeCredentials.query.filter_by(automation_id=automation.id).all()
        for cred in creds:
            logger.info(f"Deleting credential {cred.id} for automation {automation_id}")
            db.session.delete(cred)
        
        # 3. Finally delete the automation itself
        db.session.delete(automation)
        db.session.commit()
        
        logger.info(f"Successfully deleted automation {automation_id}")
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error deleting automation {automation_id}: {str(e)}", exc_info=True)
        db.session.rollback()
        return jsonify({"error": str(e), "success": False}), 500
    
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
            # User needs to set up credentials via the Exchange Settings page.
            return jsonify({
                "success": False,
                "needs_manual_setup": True
                # "has_portfolios" key removed as it relied on native Coinbase logic
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

@bp.route('/test-route/<automation_id>')
def test_automation_route(automation_id):
    return f"Automation ID: {automation_id}"