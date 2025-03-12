# app/services/webhook_processor.py

from app.models.automation import Automation
from app.models.exchange_credentials import ExchangeCredentials
from app.models.webhook import WebhookLog
from app.models.portfolio import Portfolio
from app.services.coinbase_service import CoinbaseService
from app.services.account_service import AccountService
from datetime import datetime, timezone
from app import db
from flask import current_app
from coinbase.rest import RESTClient
import logging
import uuid
import math
import json

logger = logging.getLogger(__name__)

class WebhookProcessor:
    def process_webhook(self, automation_id, payload):
        """Process an incoming webhook for an automation"""
        try:
            # Generate client_order_id at the start
            client_order_id = str(uuid.uuid4())
            logger.info(f"Processing webhook with client_order_id: {client_order_id}")
            
            # Get the automation
            automation = Automation.query.filter_by(automation_id=automation_id).first()
            
            if not automation:
                logger.error(f"No automation found with id: {automation_id}")
                return {
                    "success": True,  # Webhook received successfully
                    "trade_executed": False,
                    "client_order_id": client_order_id,
                    "message": f"No automation found with id: {automation_id}"
                }
            
            # Create a log entry for this webhook immediately
            log_entry = WebhookLog(
                automation_id=automation_id,
                payload=payload,
                timestamp=datetime.now(timezone.utc),
                trading_pair=automation.trading_pair,
                client_order_id=client_order_id  # Add client_order_id to log
            )
            db.session.add(log_entry)
            db.session.commit()
            
            # Check if automation has a trading pair configured
            if not automation.trading_pair:
                logger.warning(f"Automation {automation_id} does not have a trading pair configured")
                return {
                    "success": False,
                    "message": "Trading pair not configured for this automation"
                }
            
            # Check if portfolio is connected
            if not automation.portfolio_id:
                logger.error(f"No portfolio connected to automation: {automation_id}")
                return {
                    "success": False, 
                    "message": "No portfolio connected to this automation"
                }
            
            # Get portfolio details
            portfolio = Portfolio.query.get(automation.portfolio_id)
            if not portfolio:
                logger.error(f"Portfolio not found for automation {automation_id}")
                return {
                    "success": False,
                    "message": "Portfolio not found"
                }
            
            # Get the API credentials for this automation
            credentials = ExchangeCredentials.query.filter_by(
                portfolio_id=automation.portfolio_id,
                exchange='coinbase'
            ).first()
            
            if not credentials:
                logger.error(f"No API credentials found for automation: {automation_id}")
                return {
                    "success": False,
                    "message": "API credentials not found"
                }
            
            # Process the webhook payload
            # Use action from payload, ignore any trading pair in the webhook
            action = payload.get('action', '').lower()
            
            # Validate action
            if action not in ['buy', 'sell']:
                logger.error(f"Invalid action in payload: {action}")
                return {
                    "success": False,
                    "message": f"Invalid action: {action}. Must be 'buy' or 'sell'."
                }
            
            # Always use the trading pair defined in the automation
            trading_pair = automation.trading_pair
            logger.info(f"Using trading pair from automation: {trading_pair}")
            
            # Extract base and quote currencies from trading pair
            try:
                base_currency, quote_currency = trading_pair.split('-')
                logger.info(f"Base currency: {base_currency}, Quote currency: {quote_currency}")
            except ValueError:
                logger.error(f"Invalid trading pair format: {trading_pair}")
                return {
                    "success": False,
                    "message": f"Invalid trading pair format: {trading_pair}. Expected format: BTC-USD"
                }
            
            # Execute the trade with Coinbase API
            trade_result = self.execute_trade(
                credentials=credentials,
                portfolio=portfolio,
                trading_pair=trading_pair,
                action=action,
                payload=payload,
                client_order_id=client_order_id  # Pass client_order_id to execute_trade
            )
            
            # Update the log entry with the trade result
            try:
                log_entry.status = trade_result.get('trade_status', 'error')
                log_entry.message = trade_result.get('message', '')
                log_entry.order_id = trade_result.get('order_id', '')
                log_entry.raw_response = trade_result.get('raw_response', '')
                db.session.commit()
                logger.info(f"Updated webhook log {log_entry.id} with trade result")
            except Exception as e:
                logger.error(f"Error updating webhook log: {str(e)}")
            
            # Return combined result
            return {
                "success": True,  # Webhook was received and processed
                "trade_executed": trade_result.get('trade_executed', False),
                "client_order_id": client_order_id,
                "order_id": trade_result.get('order_id'),
                "message": trade_result.get('message'),
                "trading_pair": trading_pair,
                "action": action,
                "size": trade_result.get('size'),
                "raw_response": trade_result.get('raw_response')
            }
            
        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
            return {
                "success": True,  # Webhook received, but processing failed
                "trade_executed": False,
                "client_order_id": client_order_id,
                "message": f"Error processing webhook: {str(e)}"
            }
    
    def execute_trade(self, credentials, portfolio, trading_pair, action, payload, client_order_id):
        """
        Execute a trade on Coinbase
        
        Args:
            credentials: The ExchangeCredentials object
            portfolio: The Portfolio object
            trading_pair: Trading pair string (e.g. 'BTC-USD')
            action: 'buy' or 'sell'
            payload: Original webhook payload
            
        Returns:
            dict: Result of the trade execution
        """
        try:  # Main try block
            logger.info(f"Executing {action} order for {trading_pair} in portfolio {portfolio.name}")
            
            # Create Coinbase client
            client = RESTClient(
                api_key=credentials.api_key,
                api_secret=credentials.decrypt_secret()
            )
            
            if not client:
                logger.error("Failed to create Coinbase client")
                return {
                    "success": False,
                    "message": "Failed to create Coinbase client",
                    "client_order_id": client_order_id
                }
            
            # Get the portfolio UUID and split trading pair
            portfolio_uuid = portfolio.portfolio_id
            base_currency, quote_currency = trading_pair.split('-')
            # client_order_id = str(uuid.uuid4())
            target_currency = quote_currency if action == 'buy' else base_currency
            
            try:  # Account retrieval try block
                # Get accounts from Coinbase API
                accounts_response = client.get_accounts()
                
                # Convert response to dictionary
                if hasattr(accounts_response, "to_dict"):
                    accounts_response = accounts_response.to_dict()
                else:
                    if hasattr(accounts_response, 'accounts'):
                        accounts = accounts_response.accounts
                    elif isinstance(accounts_response, dict) and 'accounts' in accounts_response:
                        accounts = accounts_response['accounts']
                    else:
                        logger.error("Cannot extract accounts from response")
                        return {
                            "success": False,
                            "message": "Failed to extract account information"
                        }
                
                accounts = accounts_response.get('accounts', [])
                logger.info(f"Looking for {target_currency} account in portfolio {portfolio_uuid}")
                logger.info(f"Found {len(accounts)} accounts")
                
            except Exception as e:
                logger.error(f"Error getting accounts: {str(e)}", exc_info=True)
                return {
                    "success": False,
                    "message": f"Error retrieving account information: {str(e)}"
                }
                
            try:  # Balance processing try block
                target_account = None
                target_balance = 0.0
                
                # Find account with matching currency
                for account in accounts:
                    currency = account.get('currency')
                    if currency == target_currency:
                        account_uuid = account.get('uuid')
                        account_portfolio = account.get('retail_portfolio_id')
                        available_balance = account.get('available_balance', {})
                        balance_str = available_balance.get('value', '0')
                        
                        try:
                            balance = float(balance_str)
                            logger.info(f"Found {currency} account: {account_uuid} with balance: {balance}")
                            
                            if account_portfolio == portfolio_uuid:
                                target_account = account_uuid
                                target_balance = balance
                                logger.info(f"Account matches portfolio {portfolio_uuid}")
                                break
                            elif target_account is None:
                                target_account = account_uuid
                                target_balance = balance
                                logger.info(f"Account doesn't match portfolio, using as fallback")
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Could not convert balance '{balance_str}' to float: {e}")
                
                if not target_account:
                    return {
                        "success": False,
                        "message": f"No {target_currency} account found"
                    }
                
                if target_balance <= 0:
                    return {
                        "success": False,
                        "message": f"Insufficient balance ({target_balance} {target_currency}) for {action} order"
                    }
                
                # Determine order size and configuration
                if action == 'buy':
                    order_size = math.floor(target_balance) # coinbase rejects order with decimals
                    order_configuration = {
                        "market_market_ioc": {
                            "quote_size": str(order_size)
                        }
                    }
                    side = "BUY"
                else:
                    order_size = target_balance
                    order_configuration = {
                        "market_market_ioc": {
                            "base_size": str(order_size)
                        }
                    }
                    side = "SELL"
                    
            except Exception as e:
                logger.error(f"Error processing balance: {str(e)}", exc_info=True)
                return {
                    "success": False,
                    "message": f"Error processing balance: {str(e)}"
                }

            try:  # Order execution try block
                logger.info(f"Sending order to Coinbase: client_order_id={client_order_id}, product_id={trading_pair}, side={side}, order_config={order_configuration}")
                portfolio = Portfolio.query.filter_by(portfolio_id=portfolio_uuid).first()
                automation = Automation.query.filter_by(portfolio_id=portfolio.id).first()

                order_response = client.create_order(
                    client_order_id=client_order_id,
                    product_id=trading_pair,
                    side=side,
                    order_configuration=order_configuration
                )
                
                # Better response parsing
                response_dict = (
                    order_response.to_dict() 
                    if hasattr(order_response, 'to_dict') 
                    else order_response if isinstance(order_response, dict) 
                    else {}
                )
                
                # Extract success info from response
                success_response = response_dict.get('success_response', {})
                success = response_dict.get('success', False)
                coinbase_trade = "Filled" if success else "Rejected"
                order_id = success_response.get('order_id')
                product_id = success_response.get('product_id')
                side = success_response.get('side')
                message = f"Status: {coinbase_trade} | Order ID: {success_response.get('order_id', 'Unknown')}"
                
                logger.info(f"Order executed. Response: {response_dict}")
                
            except Exception as e:
                logger.error(f"Error executing trade: {str(e)}", exc_info=True)
                response_dict = {}
                success = False
                coinbase_trade = "Error"
                order_id = None
                product_id = trading_pair
                message = "Something went wrong"
                
                if hasattr(e, 'response'):
                    try:
                        error_response = e.response.json()
                        message = error_response.get('message', message)
                        response_dict = error_response
                    except:
                        response_dict = {"error": str(e)}

            # Create webhook log entry (moved outside try/except)
            try:
                current_time = datetime.now(timezone.utc)
                log_entry = WebhookLog(
                    automation_id=automation.automation_id,
                    payload={
                        "action": side,
                        "ticker": product_id,
                        "timestamp": current_time.isoformat(),
                        "message": message
                    },
                    timestamp=current_time,
                    trading_pair=product_id,
                    status=coinbase_trade,
                    message=message,
                    order_id=order_id,
                    client_order_id=client_order_id,
                    raw_response=str(response_dict)
                )
                db.session.add(log_entry)
                db.session.commit()
            except Exception as log_error:
                logger.error(f"Error creating webhook log: {str(log_error)}")

            # Return response (moved outside try/except)
            return {
                "trade_executed": bool(order_id),
                "order_id": order_id,
                "client_order_id": client_order_id,
                "message": message,
                "size": order_size,
                "trading_pair": trading_pair,
                "trade_status": "success" if order_id else "error",
                "raw_response": str(response_dict)
            }
                
        except Exception as e:  # Main exception handler
            logger.error(f"Error in execute_trade: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": f"Error in execute_trade: {str(e)}"
            }
