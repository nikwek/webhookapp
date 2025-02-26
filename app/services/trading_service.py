# app/services/trading_service.py
from app.services.coinbase_service import CoinbaseService
from app.models.exchange_credentials import ExchangeCredentials
from app import db
from datetime import datetime, timezone
import logging
import uuid

logger = logging.getLogger(__name__)

class TradingService:
    @staticmethod
    def execute_trade(processed_data):
        """
        Execute a trade based on processed webhook data
        
        Args:
            processed_data (dict): The processed webhook data
            
        Returns:
            tuple: (result, status_code)
        """
        automation_id = processed_data.get('automation_id')
        action = processed_data.get('action')
        symbol = processed_data.get('symbol')
        amount = processed_data.get('amount')
        
        # Get credentials for this automation
        credentials = ExchangeCredentials.query.filter_by(
            automation_id=automation_id,
            exchange='coinbase',
            is_active=True
        ).first()
        
        if not credentials:
            logger.error(f"No Coinbase credentials found for automation: {automation_id}")
            return {"error": "No Coinbase credentials found"}, 400
            
        # Create the order
        try:
            result = CoinbaseService.create_market_order(
                credentials=credentials,
                product_id=symbol,
                side=action,
                size=amount,
                size_in_quote=True  # Assuming amount is in quote currency (e.g., USD)
            )
            
            # Update the last_used timestamp on credentials
            credentials.last_used = datetime.now(timezone.utc)
            db.session.commit()
            
            if not result or not result.get('success'):
                logger.error(f"Order creation failed: {result}")
                return {"error": "Order creation failed", "details": result}, 400
                
            order_id = result.get('success_response', {}).get('order_id')
            
            return {
                "success": True, 
                "order_id": order_id,
                "message": f"Successfully placed {action} order for {amount} of {symbol}"
            }, 200
            
        except Exception as e:
            logger.error(f"Error executing trade: {str(e)}")
            return {"error": f"Error executing trade: {str(e)}"}, 500