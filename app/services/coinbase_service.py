# app/services/coinbase_service.py

from flask import current_app
from app.models.exchange_credentials import ExchangeCredentials
from app.models.portfolio import Portfolio
from coinbase.rest import RESTClient
from app.utils.circuit_breaker import circuit_breaker
import traceback
import logging
from app import db
import time

logger = logging.getLogger(__name__)

class CoinbaseService:
    """Service for interacting with Coinbase API"""
    
    @staticmethod
    def get_client(user_id, portfolio_name='default'):
        """Get a Coinbase API client instance"""
        from coinbase.rest import RESTClient
        
        credentials = ExchangeCredentials.query.filter_by(
            user_id=user_id,
            exchange='coinbase',
            portfolio_name=portfolio_name
        ).first()
        
        if not credentials:
            logger.warning(f"No Coinbase credentials found for user {user_id}")
            return None

        try:
            # Decrypt the API secret
            api_secret = credentials.decrypt_secret()
            
            # Create client with credentials
            client = RESTClient(
                api_key=credentials.api_key,
                api_secret=api_secret
            )
            logger.info(f"Successfully created Coinbase REST client for user {user_id}")
            return client
        except Exception as e:
            logger.error(f"Error creating Coinbase client: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def format_response_data(data):
        """Standardize API response data format"""
        if isinstance(data, dict):
            return {k: v for k, v in data.items()}
        elif isinstance(data, list):
            return [
                item if isinstance(item, (dict, list, str, int, float, bool)) 
                else item.__dict__ for item in data
            ]
        else:
            return data

    @staticmethod
    def get_portfolios(user_id, include_default=False):
        """
        Get user's Coinbase portfolios
        
        Args:
            user_id (int): User ID
            include_default (bool): Whether to include the Default portfolio
            
        Returns:
            list: List of portfolio names, excluding the Default portfolio unless specified
        """
        client = CoinbaseService.get_client(user_id)
        if not client:
            return None
        
        try:
            response = client.get_portfolios()
            logger.info("Successfully retrieved portfolio info")
            portfolios = response['portfolios']
            
            # Filter out the Default portfolio and extract names
            portfolio_names = [
                portfolio['name'] 
                for portfolio in portfolios 
                if include_default or (
                    portfolio['name'] != 'Default' and 
                    portfolio['type'] != 'DEFAULT'
                )
            ]
            
            logger.info(f"Portfolio names (excluding Default): {portfolio_names}")
            return portfolio_names
        except Exception as e:
            logger.error(f"Error getting portfolio info: {e}")
            return None

    @staticmethod
    @circuit_breaker('coinbase_api')
    def get_trading_pairs(user_id):
        """Get all available trading pairs from Coinbase Advanced Trade API"""
        from coinbase.rest import RESTClient
        
        try:
            logger.info(f"Starting get_trading_pairs for user {user_id}")
            
            # Get credentials
            credentials = ExchangeCredentials.query.filter_by(
                user_id=user_id,
                exchange='coinbase',
                portfolio_name='default',
                is_default=True
            ).first()
            
            if not credentials:
                logger.error(f"Could not find credentials for user {user_id}")
                return []
                    
            # Decrypt API secret
            api_secret = credentials.decrypt_secret()
            api_key = credentials.api_key
            
            # Create Coinbase client
            logger.info(f"Initializing Coinbase REST client")
            client = RESTClient(api_key=api_key, api_secret=api_secret)
            
            # Fetch products
            logger.info(f"Calling get_products()")
            response = client.get_products()
            
            # Process response
            products = []
            if isinstance(response, dict) and 'products' in response:
                products = response['products']
                logger.info(f"Found {len(products)} products in dictionary response")
            elif hasattr(response, 'products'):
                products = response.products
                logger.info(f"Found {len(products)} products using .products attribute")
            
            if not products:
                logger.error(f"No products found in response")
                return []
            
            # Format trading pairs
            trading_pairs = []
            
            # Process each product - handle BOTH dict and object types
            for product in products:
                try:
                    # First try to access as attributes (object)
                    if hasattr(product, 'status') and hasattr(product, 'product_id'):
                        status = getattr(product, 'status', None)
                        product_id = getattr(product, 'product_id', None)
                        base_currency = getattr(product, 'base_currency_id', None)
                        quote_currency = getattr(product, 'quote_currency_id', None)
                        base_display = getattr(product, 'base_display_symbol', None)
                        quote_display = getattr(product, 'quote_display_symbol', None)
                        display_name = getattr(product, 'display_name', None)
                    # Then try as dictionary keys
                    elif isinstance(product, dict):
                        status = product.get('status')
                        product_id = product.get('product_id')
                        base_currency = product.get('base_currency_id')
                        quote_currency = product.get('quote_currency_id')
                        base_display = product.get('base_display_symbol')
                        quote_display = product.get('quote_display_symbol')
                        display_name = product.get('display_name')
                    else:
                        # Skip if neither object nor dict
                        logger.warning(f"Skipping product of type {type(product)}")
                        continue
                    
                    # Only include online products
                    if status == 'online' and product_id:
                        pair_data = {
                            'id': product_id,
                            'product_id': product_id,
                            'base_currency': base_currency,
                            'quote_currency': quote_currency,
                            'display_name': f"{base_display}/{quote_display}" if base_display and quote_display else display_name
                        }
                        trading_pairs.append(pair_data)
                except Exception as e:
                    logger.exception(f"Error processing product: {str(e)}")
                    # Continue with next product
                    continue
            
            trading_pairs.sort(key=lambda x: x['display_name'])
            logger.info(f"Successfully processed {len(trading_pairs)} trading pairs")
            
            return trading_pairs
            
        except Exception as e:
            logger.exception(f"Unexpected error in get_trading_pairs: {str(e)}")
            return []

        
    @staticmethod
    @circuit_breaker('coinbase_api')
    def get_portfolio_value_from_breakdown(user_id, portfolio_id, currency='USD'):
        """
        Get portfolio value using the get_portfolio_breakdown API endpoint
        
        Args:
            user_id (int): User ID
            portfolio_id (int): Portfolio ID in our database
            currency (str): Currency code for the value (default: USD)
            
        Returns:
            float: Total portfolio value
        """
        try:
            # Get the portfolio record to find the UUID
            portfolio = Portfolio.query.get(portfolio_id)
            if not portfolio:
                logger.warning(f"Portfolio not found for ID {portfolio_id}")
                return 0.0
                
            # Get the portfolio UUID
            portfolio_uuid = portfolio.portfolio_id
            
            # Get credentials specifically for this portfolio
            creds = ExchangeCredentials.query.filter_by(
                user_id=user_id,
                portfolio_id=portfolio_id,
                exchange='coinbase'
            ).first()
            
            if not creds:
                logger.warning(f"No API credentials found for portfolio_id={portfolio_id}")
                return 0.0
            
            # Create client with these specific credentials
            client = CoinbaseService.get_client_from_credentials(creds)
            if not client:
                logger.error("Failed to create Coinbase client")
                return 0.0
            
            try:
                # Get portfolio breakdown
                breakdown = client.get_portfolio_breakdown(portfolio_uuid=portfolio_uuid, currency=currency)
                
                # Extract the value using proper object traversal, not string parsing
                portfolio_value = 0.0
                
                # If breakdown is a dictionary
                if isinstance(breakdown, dict):
                    logger.debug(f"Breakdown is a dictionary with keys: {list(breakdown.keys())}")
                    
                    if 'breakdown' in breakdown:
                        breakdown_data = breakdown['breakdown']
                        
                        if isinstance(breakdown_data, dict) and 'portfolio_balances' in breakdown_data:
                            balances = breakdown_data['portfolio_balances']
                            
                            if isinstance(balances, dict) and 'total_balance' in balances:
                                total_balance = balances['total_balance']
                                
                                if isinstance(total_balance, dict) and 'value' in total_balance:
                                    try:
                                        portfolio_value = float(total_balance['value'])
                                        logger.info(f"Extracted portfolio value (dict): {portfolio_value}")
                                        return portfolio_value
                                    except (ValueError, TypeError) as e:
                                        logger.error(f"Error converting portfolio value to float: {e}")
                
                # If breakdown is an object
                elif hasattr(breakdown, 'breakdown'):
                    logger.debug("Breakdown has a 'breakdown' attribute")
                    breakdown_data = breakdown.breakdown
                    
                    if hasattr(breakdown_data, 'portfolio_balances'):
                        balances = breakdown_data.portfolio_balances
                        
                        if hasattr(balances, 'total_balance'):
                            total_balance = balances.total_balance
                            
                            if hasattr(total_balance, 'value'):
                                try:
                                    portfolio_value = float(total_balance.value)
                                    logger.info(f"Extracted portfolio value (object): {portfolio_value}")
                                    return portfolio_value
                                except (ValueError, TypeError) as e:
                                    logger.error(f"Error converting portfolio value to float: {e}")
                
                # Last resort - try string parsing but with better detection
                raw_response = str(breakdown)
                logger.debug(f"Attempting string parsing from: {raw_response[:200]}...")
                
                # More targeted string extraction
                value_patterns = [
                    "'total_balance': {'value': '",
                    '"total_balance": {"value": "',
                    "value='",
                    'value="'
                ]
                
                for pattern in value_patterns:
                    if pattern in raw_response:
                        start_idx = raw_response.find(pattern) + len(pattern)
                        end_idx = raw_response.find("'", start_idx) if "'" in pattern else raw_response.find('"', start_idx)
                        
                        if start_idx > 0 and end_idx > start_idx:
                            total_value_str = raw_response[start_idx:end_idx]
                            try:
                                portfolio_value = float(total_value_str)
                                logger.info(f"Extracted portfolio value (string): {portfolio_value}")
                                return portfolio_value
                            except (ValueError, TypeError) as e:
                                logger.error(f"Error converting string value to float: {total_value_str}")
                
                logger.warning(f"Could not extract total balance from portfolio breakdown")
                
                # Additional debug info
                if hasattr(breakdown, '__dict__'):
                    logger.debug(f"Breakdown __dict__: {breakdown.__dict__}")
                
                return 0.0
                
            except Exception as e:
                error_message = str(e).lower()
                
                # Check for specific permission errors
                if 'permission_denied' in error_message or 'access to portfolio' in error_message or any(str(code) in error_message for code in ['403', '401']):
                    logger.warning(f"Access denied to portfolio {portfolio_uuid} ({portfolio.name}). The portfolio may have been deleted or permissions revoked.")
                    
                    # Flag the credential as invalid
                    if creds:
                        try:
                            logger.info(f"Removing invalid credentials for portfolio {portfolio.name} (ID: {portfolio_id})")
                            db.session.delete(creds)
                            db.session.commit()
                        except Exception as del_err:
                            logger.error(f"Error deleting invalid credentials: {str(del_err)}")
                            db.session.rollback()
                    
                    # Update portfolio status if needed
                    try:
                        portfolio.invalid_credentials = True
                        db.session.commit()
                    except:
                        db.session.rollback()
                    
                    return 0.0
                
                # Re-raise other errors
                raise
                
        except Exception as e:
            logger.error(f"Error getting portfolio value from breakdown: {str(e)}", exc_info=True)
            return 0.0

    # Mthod to check and clean up portfolios
    @staticmethod
    def verify_portfolio_access(user_id, portfolio_id):
        """
        Verify if a portfolio is still accessible with current credentials
        
        Args:
            user_id (int): User ID
            portfolio_id (int): Portfolio ID in our database
            
        Returns:
            bool: True if portfolio is accessible, False otherwise
        """
        try:
            # Get portfolio info
            portfolio = Portfolio.query.get(portfolio_id)
            if not portfolio:
                return False
                
            # Get credentials
            creds = ExchangeCredentials.query.filter_by(
                user_id=user_id,
                portfolio_id=portfolio_id,
                exchange='coinbase'
            ).first()
            
            if not creds:
                return False
                
            # Try to create client
            client = CoinbaseService.get_client_from_credentials(creds)
            if not client:
                return False
                
            # Test access with a lightweight call
            client.get_portfolio_breakdown(portfolio_uuid=portfolio.portfolio_id)
            
            # If we get here, the portfolio is accessible
            return True
            
        except Exception as e:
            error_message = str(e).lower()
            
            # Check for specific permission errors
            if 'permission_denied' in error_message or 'access to portfolio' in error_message or any(str(code) in error_message for code in ['403', '401']):
                logger.warning(f"Access denied to portfolio {portfolio.portfolio_id} ({portfolio.name}). The portfolio may have been deleted or permissions revoked.")
                
                # Clean up invalid credentials
                if creds:
                    try:
                        logger.info(f"Removing invalid credentials for portfolio {portfolio.name} (ID: {portfolio_id})")
                        db.session.delete(creds)
                        db.session.commit()
                    except Exception as del_err:
                        logger.error(f"Error deleting invalid credentials: {str(del_err)}")
                        db.session.rollback()
                
                return False
                
            # For other types of errors, log but don't delete credentials
            logger.error(f"Error verifying portfolio access: {str(e)}")
            return False

    @staticmethod
    @circuit_breaker('coinbase_api')
    def get_client_from_credentials(credentials):
        """
        Get a Coinbase client instance from credentials with retry mechanism
        """
        try:
            if not credentials:
                logger.warning("No credentials provided to get_client_from_credentials")
                return None
                    
            # Create Coinbase client
            from coinbase.rest import RESTClient
            from app.models.portfolio import Portfolio
            
            api_key = credentials.api_key
            api_secret = credentials.decrypt_secret()
            
            client = RESTClient(api_key=api_key, api_secret=api_secret)
            
            # Retry configuration
            max_retries = 3
            retry_delay = 1  # seconds
            
            # Try validation with retries
            for attempt in range(max_retries):
                try:
                    # Use a lightweight API call to validate credentials
                    client.get_accounts()
                    
                    # If successful, check if portfolio was previously marked invalid and reset
                    if credentials.portfolio_id:
                        portfolio = Portfolio.query.get(credentials.portfolio_id)
                        if portfolio and portfolio.invalid_credentials:
                            portfolio.invalid_credentials = False
                            db.session.commit()
                            logger.info(f"Reset invalid flag for portfolio {portfolio.id} after successful validation")
                    
                    logger.debug(f"Successfully validated Coinbase API credentials on attempt {attempt+1}")
                    return client
                    
                except Exception as e:
                    error_str = str(e).lower()
                    
                    # Check specifically for auth errors (401/403)
                    if 'unauthorized' in error_str or '401' in error_str or '403' in error_str or 'invalid signature' in error_str:
                        logger.warning(f"Invalid Coinbase API credentials detected: {str(e)}")
                        
                        # Handle invalid credentials
                        if credentials.portfolio_id:
                            portfolio = Portfolio.query.get(credentials.portfolio_id)
                            if portfolio:
                                portfolio.invalid_credentials = True
                                db.session.commit()
                        
                        return None
                    
                    # For other errors, retry if we have attempts left
                    if attempt < max_retries - 1:
                        logger.warning(f"API validation attempt {attempt+1} failed, retrying in {retry_delay}s: {str(e)}")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        logger.error(f"API validation failed after {max_retries} attempts: {str(e)}")
                        # For non-auth errors after all retries, return the client anyway
                        # This allows operations to continue despite temporary API issues
                        return client
                    
        except Exception as e:
            logger.error(f"Error creating Coinbase client from credentials: {str(e)}", exc_info=True)
            return None
