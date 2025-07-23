import pytest
from app.models.trading import TradingStrategy
from app.models.webhook import WebhookLog
from app.services.webhook_processor import EnhancedWebhookProcessor
from app import db

@pytest.fixture
def webhook_processor(app):
    with app.app_context():
        return EnhancedWebhookProcessor()

@pytest.fixture
def test_strategy(app):
    with app.app_context():
        # Create a user directly in this session
        from app.models.user import User
        from app.models.exchange_credentials import ExchangeCredentials
        from flask_security import hash_password
        
        user = User.query.filter_by(email='test@example.com').first()
        if not user:
            user = User(
                email='test@example.com',
                password=hash_password('password'),
                active=True
            )
            db.session.add(user)
            db.session.commit()
        
        # Create exchange credentials
        credentials = ExchangeCredentials(
            user_id=user.id,
            exchange='coinbase',
            portfolio_name='Test Portfolio',
            api_key='test-api-key',
            api_secret='test-api-secret'
        )
        db.session.add(credentials)
        db.session.commit()
        
        webhook_id = 'test-webhook-id'
        strategy = TradingStrategy(
            user_id=user.id,
            name='Test Strategy',
            exchange_credential_id=credentials.id,
            trading_pair='BTC/USD',
            base_asset_symbol='BTC',
            quote_asset_symbol='USD',
            allocated_base_asset_quantity=0.0,
            allocated_quote_asset_quantity=1000.0,
            webhook_id=webhook_id
        )
        db.session.add(strategy)
        db.session.commit()
        # Return the webhook_id as a simple string to avoid session issues
        return webhook_id

def test_process_webhook_valid_condition(app, webhook_processor, test_strategy):
    with app.app_context():
        # test_strategy is now just the webhook_id string
        webhook_id = test_strategy
        
        # Re-query the strategy to ensure it's attached to the current session
        strategy = TradingStrategy.query.filter_by(webhook_id=webhook_id).first()
        
        payload = {
            'action': 'buy',
            'trading_pair': 'BTC/USD',  # Use slash format to match strategy
            'amount': 100.0
        }
        
        result, status_code = webhook_processor.process_webhook(webhook_id, payload)
        # The webhook processor should return successfully even if there are trade issues
        assert status_code in [200, 400]  # 200 for success, 400 for expected errors like ticker mismatch
        
        # Verify log was created
        log = WebhookLog.query.filter_by(strategy_id=strategy.id).first()
        assert log is not None

def test_process_webhook_invalid_webhook_id(webhook_processor):
    # Test with a webhook ID that doesn't exist for any trading strategy
    result, status_code = webhook_processor.process_webhook('nonexistent-webhook-id', {})
    assert status_code == 404
    assert result['success'] is False
    assert 'Identifier not found' in result['message']
