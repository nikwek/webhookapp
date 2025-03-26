# app/services/coinbase_service.py

from flask import current_app
from app.models.exchange_credentials import ExchangeCredentials
from app.models.portfolio import Portfolio
from coinbase.rest import RESTClient
from app.utils.circuit_breaker import circuit_breaker
import traceback
import logging
from app import db

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
            
            # Get portfolio breakdown
            breakdown = client.get_portfolio_breakdown(portfolio_uuid=portfolio_uuid, currency=currency)
            
            # Extract the value from the response
            raw_response = str(breakdown)
            if "'total_balance': {'value': '" in raw_response:
                start_idx = raw_response.find("'total_balance': {'value': '") + len("'total_balance': {'value': '")
                end_idx = raw_response.find("'", start_idx)
                if start_idx > 0 and end_idx > start_idx:
                    total_value_str = raw_response[start_idx:end_idx]
                    try:
                        return float(total_value_str)
                    except (ValueError, TypeError):
                        logger.error(f"Could not convert total value to float: {total_value_str}")

            logger.warning(f"Could not extract total balance from portfolio breakdown")
            return 0.0
        except Exception as e:
            logger.error(f"Error getting portfolio value from breakdown: {str(e)}", exc_info=True)
            return 0.0

    @staticmethod
    @circuit_breaker('coinbase_api')
    def get_client_from_credentials(credentials):
        """
        Get a Coinbase client instance from credentials with immediate validation
        
        Args:
            credentials: ExchangeCredentials object
            
        Returns:
            RESTClient or None: Validated Coinbase client or None if credentials invalid
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
            
            # Immediately validate with a simple API call
            try:
                # Use a lightweight API call to validate credentials
                client.get_accounts()
                
                # If we get here, the credentials are valid
                logger.debug(f"Successfully validated Coinbase API credentials for portfolio {credentials.portfolio_id}")
                return client
                
            except Exception as e:
                error_str = str(e).lower()
                
                # Check specifically for auth errors (401/403)
                if 'unauthorized' in error_str or '401' in error_str or '403' in error_str:
                    logger.warning(f"Invalid Coinbase API credentials detected for portfolio {credentials.portfolio_id}: {str(e)}")
                    
                    # Delete the invalid credentials
                    try:
                        # Get portfolio name for better logging
                        portfolio = Portfolio.query.get(credentials.portfolio_id)
                        portfolio_name = portfolio.name if portfolio else "Unknown"
                        
                        logger.info(f"Deleting invalid credentials for portfolio '{portfolio_name}' (ID: {credentials.portfolio_id})")
                        db.session.delete(credentials)
                        db.session.commit()
                        
                        # You could add a notification here if you have a notification system
                        # notify_user(credentials.user_id, f"Your Coinbase API credentials for portfolio '{portfolio_name}' are no longer valid and have been removed.")
                        
                    except Exception as del_err:
                        logger.error(f"Error deleting invalid credentials: {str(del_err)}")
                        db.session.rollback()
                    
                    return None
                
                # For other types of errors (network issues, rate limits, etc.),
                # log but don't delete credentials as they might be temporary
                logger.error(f"Error validating Coinbase credentials (non-auth): {str(e)}")
                raise  # Let caller handle non-auth errors
                
        except Exception as e:
            logger.error(f"Error creating Coinbase client from credentials: {str(e)}", exc_info=True)
            return None
