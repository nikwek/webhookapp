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
    def get_trading_pairs(user_id):
        """Get all available trading pairs from Coinbase"""
        client = CoinbaseService.get_client(user_id)
        if not client:
            logger.error(f"Could not get Coinbase client for user {user_id}")
            return []
            
        try:
            logger.info(f"Fetching trading pairs for user {user_id}")
            response = client.get_products()
            
            # Log raw response for debugging
            logger.debug(f"Raw response type: {type(response)}")
            logger.debug(f"Raw response: {response}")
            
            # Initialize trading_pairs list
            trading_pairs = []
            
            # Get products from the response
            products = None
            if isinstance(response, dict) and 'products' in response:
                products = response['products']
                logger.info(f"Found {len(products)} products in response dictionary")
            elif hasattr(response, 'products'):
                products = response.products
                logger.info(f"Found {len(products)} products using .products attribute")
            else:
                try:
                    response_dict = vars(response)
                    if 'products' in response_dict:
                        products = response_dict['products']
                        logger.info(f"Found {len(products)} products using vars(response)")
                except Exception as e:
                    logger.error(f"Could not extract products from response: {e}")
                    return []
            
            if not products:
                logger.warning("No products found in response")
                return []
                
            # Sample logging for first few products
            logger.debug("First 3 products structure:")
            for i, product in enumerate(products[:3]):
                logger.debug(f"Product {i}: {product}")
                
            # Process each product
            for product in products:
                if isinstance(product, dict):
                    product_id = product.get('product_id')
                    base_currency = product.get('base_currency')
                    quote_currency = product.get('quote_currency')
                    status = product.get('status')
                    logger.debug(f"Dict product: {product_id}, {base_currency}-{quote_currency}, {status}")
                else:
                    product_id = getattr(product, 'product_id', None)
                    base_currency = getattr(product, 'base_currency', None)
                    quote_currency = getattr(product, 'quote_currency', None)
                    status = getattr(product, 'status', None)
                    logger.debug(f"Object product: {product_id}, {base_currency}-{quote_currency}, {status}")
                
                if product_id and status == 'online':
                    pair_data = {
                        'product_id': product_id,
                        'base_currency': base_currency,
                        'quote_currency': quote_currency,
                        'display_name': f"{base_currency}-{quote_currency}"
                    }
                    trading_pairs.append(pair_data)
                    logger.debug(f"Added trading pair: {pair_data}")
            
            trading_pairs.sort(key=lambda x: x['product_id'])
            logger.info(f"Returning {len(trading_pairs)} trading pairs")
            logger.debug("First 3 trading pairs in final result:")
            for pair in trading_pairs[:3]:
                logger.debug(f"Trading pair: {pair}")
            
            return trading_pairs
            
        except Exception as e:
            logger.error(f"Error getting trading pairs: {str(e)}", exc_info=True)
            return []