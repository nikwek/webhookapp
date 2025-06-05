# app/exchanges/coinbase_adapter.py

from app.exchanges.base_adapter import ExchangeAdapter
from app.models.exchange_credentials import ExchangeCredentials
from app.models.portfolio import Portfolio
from app.models.account_cache import AccountCache
from app import db
from app.utils.circuit_breaker import circuit_breaker
from coinbase.rest import RESTClient
from typing import Dict, List, Any, Tuple
import traceback
import logging
import math
import time

logger = logging.getLogger(__name__)


class CoinbaseAdapter(ExchangeAdapter):
    """
    Coinbase-specific implementation of the exchange adapter.
    """

    @classmethod
    def get_name(cls) -> str:
        """Return the name of the exchange"""
        return 'coinbase'

    @classmethod
    def get_display_name(cls) -> str:
        """Return the user-facing display name of the exchange"""
        return 'Coinbase'

    @classmethod
    def get_client(cls, user_id: int, portfolio_name: str = 'default'):
        """Get a Coinbase API client instance"""
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

    @classmethod
    def get_portfolios(cls, user_id: int, include_default: bool = False) -> List[str]:
        """
        Get user's Coinbase portfolios

        Args:
            user_id (int): User ID
            include_default (bool): Whether to include the Default portfolio

        Returns:
            list: List of portfolio names, excluding the Default portfolio unless specified
        """
        client = cls.get_client(user_id)
        if not client:
            return []

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
            return []

    @classmethod
    @circuit_breaker('coinbase_api')
    def get_trading_pairs(cls, user_id: int) -> List[Dict[str, Any]]:
        """Get all available trading pairs from Coinbase Advanced Trade API"""
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
            logger.info("Initializing Coinbase REST client")
            client = RESTClient(api_key=api_key, api_secret=api_secret)

            # Fetch products
            logger.info("Calling get_products()")
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
                logger.error("No products found in response")
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
                        display_fmt = "{}/{}" if base_display and quote_display else display_name
                        pair_data = {
                            'id': product_id,
                            'product_id': product_id,
                            'base_currency': base_currency,
                            'quote_currency': quote_currency,
                            'display_name': display_fmt.format(
                                base_display, quote_display) if base_display else display_name
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
            logger.exception(f"Error fetching trading pairs: {str(e)}")
            return []

    @classmethod
    @circuit_breaker('coinbase_api')
    def get_portfolio_value(cls, user_id: int, portfolio_id: int, currency: str = 'USD') -> Dict[str, Any]:
        """
        Get portfolio value from Coinbase
        
        Args:
            user_id: User ID
            portfolio_id: Portfolio ID from the database
            currency: Currency for valuation (default: USD)
            
        Returns:
            Dictionary with portfolio value information
        """
        try:
            # Get the portfolio
            portfolio = Portfolio.query.get(portfolio_id)
            if not portfolio:
                logger.error(f"Portfolio {portfolio_id} not found")
                return {
                    "success": False,
                    "error": "Portfolio not found",
                    "value": 0.0
                }
                
            # Check if portfolio is the right exchange
            if portfolio.exchange != 'coinbase':
                logger.error(f"Portfolio {portfolio_id} is not a Coinbase portfolio")
                return {
                    "success": False,
                    "error": "Not a Coinbase portfolio",
                    "value": 0.0
                }
                
            # Get Coinbase portfolio ID
            coinbase_portfolio_id = portfolio.portfolio_id
                
            # Get credentials for this portfolio
            credentials = ExchangeCredentials.query.filter_by(
                portfolio_id=portfolio_id,
                exchange='coinbase'
            ).first()
                
            if not credentials:
                logger.error(f"No credentials found for portfolio {portfolio_id}")
                return {
                    "success": False,
                    "error": "No credentials found",
                    "value": 0.0
                }
                
            # Get Coinbase client
            client = RESTClient(
                api_key=credentials.api_key,
                api_secret=credentials.decrypt_secret()
            )
                
            # Get portfolio value
            response = client.get_portfolio_breakdown(portfolio_uuid=coinbase_portfolio_id, currency=currency)
                
            # Process response using the structure of GetPortfolioBreakdownResponse
            # 'response' is the GetPortfolioBreakdownResponse object.
            # 'response' is GetPortfolioBreakdownResponse object.
            # 'response.breakdown' is a PortfolioBreakdown object.
            # This object should have 'portfolio_balances', then 'total_balance', then 'value'.
            total_value = "0.0" # Default value
            try:
                portfolio_breakdown_obj = getattr(response, 'breakdown', None)
                if portfolio_breakdown_obj:
                    portfolio_balances_obj = getattr(portfolio_breakdown_obj, 'portfolio_balances', None)
                    if portfolio_balances_obj:
                        total_balance_obj = getattr(portfolio_balances_obj, 'total_balance', None)
                        if total_balance_obj:
                            total_value = getattr(total_balance_obj, 'value', "0.0")
            except AttributeError:
                # Handle cases where the structure might unexpectedly not have these attributes
                logger.warning("Could not find expected attributes in Coinbase portfolio breakdown response.")
                pass # total_value remains "0.0"
                
            # Try to convert value to float if it's a string
            if isinstance(total_value, str):
                try:
                    total_value = float(total_value)
                except (ValueError, TypeError):
                    total_value = 0.0
                    
            return {
                "success": True,
                "value": total_value,
                "currency": currency,
                "portfolio_id": portfolio_id,
                "coinbase_portfolio_id": coinbase_portfolio_id
            }
                
        except Exception as e:
            logger.exception(f"Error getting portfolio value: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "value": 0.0
            }
                
    @classmethod
    def refresh_account_data(cls, user_id: int, portfolio_id: int) -> bool:
        """
        Refresh account data for a portfolio
        
        Args:
            user_id: User ID
            portfolio_id: Portfolio ID
            
        Returns:
            Success status
        """
        try:
            # Get the portfolio
            portfolio = Portfolio.query.get(portfolio_id)
            if not portfolio:
                logger.error(f"Portfolio {portfolio_id} not found")
                return False
                
            # Get credentials for this portfolio
            credentials = ExchangeCredentials.query.filter_by(
                portfolio_id=portfolio_id,
                exchange='coinbase'
            ).first()
                
            if not credentials:
                logger.error(f"No credentials found for portfolio {portfolio_id}")
                return False
                
            # Create Coinbase client
            client = RESTClient(
                api_key=credentials.api_key,
                api_secret=credentials.decrypt_secret()
            )
                
            # Get portfolio details
            try:
                # Get accounts
                accounts_response = client.get_accounts()
                
                # Parse accounts from response
                if hasattr(accounts_response, 'accounts'):
                    accounts = accounts_response.accounts
                elif isinstance(accounts_response, dict) and 'accounts' in accounts_response:
                    accounts = accounts_response['accounts']
                else:
                    raise ValueError("Could not extract accounts from response")
                
                # Delete existing account caches for this portfolio
                AccountCache.query.filter_by(
                    user_id=user_id,
                    portfolio_id=portfolio_id
                ).delete()
                
                # Create new account caches
                for account_data in accounts:
                    # Create account cache from exchange data
                    account_cache = AccountCache.create_from_exchange_account(
                        account_data=account_data,
                        user_id=user_id,
                        portfolio_id=portfolio_id,
                        exchange='coinbase'
                    )
                    
                    if account_cache:
                        db.session.add(account_cache)
                
                # Commit changes
                db.session.commit()
                logger.info(f"Successfully refreshed account data for portfolio {portfolio_id}")
                
                # Reset invalid flag if it was set
                if portfolio.invalid_credentials:
                    portfolio.reset_invalid_flag()
                
                return True
            
            except Exception as e:
                logger.error(f"Error refreshing account data: {str(e)}")
                
                # Mark portfolio as having invalid credentials
                portfolio.invalid_credentials = True
                db.session.commit()
                
                return False
                
        except Exception as e:
            logger.exception(f"Unexpected error in refresh_account_data: {str(e)}")
            return False
    
    @classmethod
    @circuit_breaker('coinbase_api', failure_threshold=3, recovery_timeout=60)
    def execute_trade(cls, credentials: ExchangeCredentials, portfolio: Portfolio, 
                      trading_pair: str, action: str, payload: Dict[str, Any], 
                      client_order_id: str) -> Dict[str, Any]:
        """
        Execute a trade on Coinbase
        
        Args:
            credentials: The ExchangeCredentials object
            portfolio: The Portfolio object
            trading_pair: Trading pair string (e.g. 'BTC-USD')
            action: 'buy' or 'sell'
            payload: Original webhook payload
            client_order_id: Generated UUID for this order
            
        Returns:
            Result of the trade execution
        """
        max_retries = 3
        retry_count = 0
        base_delay = 1  # second
        
        while retry_count < max_retries:
            try:
                logger.info(f"Executing {action} order for {trading_pair} in portfolio {portfolio.name} (attempt {retry_count+1}/{max_retries})")
                
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
                target_currency = quote_currency if action == 'buy' else base_currency
                
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
                        raise ValueError("Failed to extract account information")
                
                accounts = accounts_response.get('accounts', [])
                logger.info(f"Looking for {target_currency} account in portfolio {portfolio_uuid}")
                logger.info(f"Found {len(accounts)} accounts")
                
                # Find account with matching currency
                target_account = None
                target_balance = 0.0
                
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
                                logger.info("Account doesn't match portfolio, using as fallback")
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
                    order_size = math.floor(target_balance)  # coinbase rejects order with decimals
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
                
                # Send order to Coinbase
                logger.info(f"Sending order to Coinbase: client_order_id={client_order_id}, product_id={trading_pair}, side={side}")
                
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
                # product_id = success_response.get('product_id') # Commented out as unused
                side = success_response.get('side')
                message = f"Status: {coinbase_trade} | Order ID: {success_response.get('order_id', 'Unknown')}"
                
                logger.info(f"Order executed. Response: {response_dict}")
                
                # Return successful response
                return {
                    "trade_executed": bool(order_id),
                    "order_id": order_id,
                    "client_order_id": client_order_id,
                    "message": message,
                    "size": order_size,
                    "trading_pair": trading_pair,
                    "trade_status": "success" if success else "error",
                    "raw_response": str(response_dict)
                }
                
            except Exception as e:
                retry_count += 1
                logger.error(f"Error executing trade (attempt {retry_count}/{max_retries}): {str(e)}")
                
                # Only retry if we haven't exceeded max_retries
                if retry_count >= max_retries:
                    return {
                        "trade_executed": False,
                        "message": f"Error executing trade: {str(e)}",
                        "client_order_id": client_order_id,
                        "trade_status": "error",
                        "raw_response": f"Error: {str(e)}"
                    }
                
                # Exponential backoff
                wait_time = base_delay * (2 ** (retry_count - 1))
                time.sleep(wait_time)
    
    @classmethod
    def validate_api_keys(cls, api_key: str, api_secret: str) -> Tuple[bool, str]:
        """
        Validate API keys with Coinbase
        
        Args:
            api_key: API key
            api_secret: API secret
            
        Returns:
            Tuple of (is_valid, message)
        """
        try:
            # Create client with provided credentials
            client = RESTClient(api_key=api_key, api_secret=api_secret)
            
            # Test API call
            client.get_products()  # Test call, response not used
            
            # If we got here, keys are valid
            return True, "API keys validated successfully"
            
        except Exception as e:
            logger.error(f"Error validating API keys: {str(e)}")
            return False, f"Invalid API keys: {str(e)}"
