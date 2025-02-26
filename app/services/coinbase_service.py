# app/services/coinbase_service.py
from flask import current_app
from coinbase.rest import RESTClient
import logging

logger = logging.getLogger(__name__)

class CoinbaseService:
    @staticmethod
    def get_client_from_credentials(credentials):
        """Create a Coinbase client from ExchangeCredentials"""
        try:
            client = RESTClient(
                api_key=credentials.api_key,
                api_secret=credentials.secret_key
            )
            return client
        except Exception as e:
            logger.error(f"Error creating Coinbase client: {str(e)}")
            return None
    
    @staticmethod
    def list_portfolios(credentials):
        """List all portfolios for a user"""
        client = CoinbaseService.get_client_from_credentials(credentials)
        if not client:
            return []
            
        try:
            response = client.list_portfolios()
            
            # Filter out deleted portfolios
            portfolios = [p for p in response.get('portfolios', []) 
                        if not p.get('deleted', False)]
            
            return portfolios
        except Exception as e:
            logger.error(f"Error listing portfolios: {str(e)}")
            return []

    @staticmethod
    def get_portfolio(credentials, portfolio_id):
        """Get details for a specific portfolio"""
        client = CoinbaseService.get_client_from_credentials(credentials)
        if not client:
            return None
            
        try:
            response = client.get_portfolio(portfolio_id)
            return response.get('portfolio')
        except Exception as e:
            logger.error(f"Error getting portfolio: {str(e)}")
            return None

    @staticmethod
    def create_portfolio(credentials, name):
        """Create a new portfolio"""
        client = CoinbaseService.get_client_from_credentials(credentials)
        if not client:
            return None
            
        try:
            response = client.create_portfolio(name=name)
            return response.get('portfolio')
        except Exception as e:
            logger.error(f"Error creating portfolio: {str(e)}")
            return None

    @staticmethod
    def get_trading_pairs(credentials):
        """Get all available trading pairs"""
        client = CoinbaseService.get_client_from_credentials(credentials)
        if not client:
            return []
            
        try:
            response = client.list_products()
            
            # Filter only active products
            active_products = [
                product for product in response.get('products', []) 
                if product.get('status') == 'online' and 
                not product.get('trading_disabled') and
                not product.get('is_disabled')
            ]
            
            return active_products
        except Exception as e:
            logger.error(f"Error fetching trading pairs: {str(e)}")
            return []
    
    @staticmethod
    def create_market_order(credentials, product_id, side, size, size_in_quote=True):
        """Create a market order"""
        client = CoinbaseService.get_client_from_credentials(credentials)
        if not client:
            return None
            
        try:
            # Format the order configuration based on size type
            order_config = {}
            if size_in_quote:
                order_config = {
                    'market_market_ioc': {
                        'quote_size': str(size)
                    }
                }
            else:
                order_config = {
                    'market_market_ioc': {
                        'base_size': str(size)
                    }
                }
            
            # Generate a client order ID
            import uuid
            client_order_id = str(uuid.uuid4())
            
            # Create the order
            response = client.create_order(
                client_order_id=client_order_id,
                product_id=product_id,
                side=side.upper(),
                order_configuration=order_config
            )
            
            return response
        except Exception as e:
            logger.error(f"Error creating market order: {str(e)}")
            return None