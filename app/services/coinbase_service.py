# app/services/coinbase_service.py

from flask import current_app
from app.models.exchange_credentials import ExchangeCredentials
from coinbase.rest import RESTClient
import traceback
import logging

logger = logging.getLogger(__name__)

class CoinbaseService:
    """Service for interacting with Coinbase API"""
    
    @staticmethod
    def get_client(user_id, portfolio_name='default'):
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
            logger.info(f"Successfully created Coinbase client for user {user_id}")
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
    def get_market_data(user_id, product_id='BTC-USD'):
        client = CoinbaseService.get_client(user_id)
        if not client:
            return None
        
        try:
            # Get product details and ticker
            product = client.get_product(product_id)
            ticker = client.get_product_ticker(product_id)
            
            # Format the market data for JSON serialization
            market_data = {
                'product': CoinbaseService.format_response_data(product),
                'ticker': CoinbaseService.format_response_data(ticker)
            }
            return market_data
        except Exception as e:
            logger.error(f"Error getting Coinbase market data: {str(e)}")
            logger.error(traceback.format_exc())
            return None

    @staticmethod
    def get_account_info(user_id):
        client = CoinbaseService.get_client(user_id)
        if not client:
            return None

        try:
            response = client.get_accounts()
            logger.info("Successfully retrieved account info")
            accounts = response.accounts
            logger.info(f"Accounts list: {accounts}")
            # Format the accounts data for JSON serialization
            return CoinbaseService.format_response_data(accounts)
        except Exception as e:
            logger.error(f"Error getting account info: {e}")
            return None