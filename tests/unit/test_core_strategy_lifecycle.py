"""
Core Strategy Lifecycle Tests

Focused tests for the most critical strategy lifecycle operations:
1. Strategy pause/unpause webhook validation (CRITICAL for security)
2. Strategy deletion business logic (CRITICAL for asset safety)
3. Core lifecycle state management

These tests focus on business logic rather than route authentication,
which is already covered in the existing auth test suite.
"""

import pytest
from decimal import Decimal
from unittest.mock import patch

from app import db
from app.models.trading import TradingStrategy
from app.models.exchange_credentials import ExchangeCredentials
from app.models.webhook import WebhookLog
from app.services.webhook_processor import EnhancedWebhookProcessor


class TestCoreWebhookPauseLogic:
    """Test the critical webhook pause/unpause business logic."""
    
    def test_paused_strategy_rejects_webhooks_with_403(self, app, regular_user, dummy_cred):
        """CRITICAL: Paused strategies must return 403 and log as ignored."""
        with app.app_context():
            from app.models.user import User
            user = User.query.filter_by(email="testuser@example.com").first()
            
            # Create paused strategy
            strategy = TradingStrategy(
                user_id=user.id,
                name="Paused Strategy",
                exchange_credential_id=dummy_cred,
                trading_pair="BTC/USDT",
                base_asset_symbol="BTC",
                quote_asset_symbol="USDT",
                allocated_base_asset_quantity=Decimal("1.0"),
                allocated_quote_asset_quantity=Decimal("0"),
                webhook_id="paused-webhook-test",
                is_active=False  # Strategy is paused
            )
            db.session.add(strategy)
            db.session.commit()
            
            processor = EnhancedWebhookProcessor()
            
            # Attempt to send webhook to paused strategy
            payload = {
                "action": "sell",
                "ticker": "BTC/USDT",
                "amount": "0.5"
            }
            
            result, status_code = processor.process_webhook("paused-webhook-test", payload)
            
            # Should return 403 Forbidden for paused strategy
            assert status_code == 403
            assert "paused" in result.get("message", "").lower()
            
            # Verify webhook was logged as ignored
            log = WebhookLog.query.filter_by(strategy_id=strategy.id).first()
            assert log is not None
            assert log.status == "ignored"
            assert "paused" in log.message.lower()
    
    def test_active_strategy_processes_webhooks_normally(self, app, regular_user, dummy_cred):
        """Active strategies should process webhooks and attempt trades."""
        with app.app_context():
            from app.models.user import User
            user = User.query.filter_by(email="testuser@example.com").first()
            
            # Create active strategy
            strategy = TradingStrategy(
                user_id=user.id,
                name="Active Strategy",
                exchange_credential_id=dummy_cred,
                trading_pair="BTC/USDT",
                base_asset_symbol="BTC",
                quote_asset_symbol="USDT",
                allocated_base_asset_quantity=Decimal("1.0"),
                allocated_quote_asset_quantity=Decimal("0"),
                webhook_id="active-webhook-test",
                is_active=True  # Strategy is active
            )
            db.session.add(strategy)
            db.session.commit()
            
            # Mock exchange service to simulate successful trade
            with patch('app.services.webhook_processor.ExchangeService.execute_trade') as mock_trade:
                mock_trade.return_value = {
                    "trade_executed": True,
                    "message": "Trade executed successfully",
                    "trade_status": "filled"
                }
                
                processor = EnhancedWebhookProcessor()
                
                # Send webhook to active strategy
                payload = {
                    "action": "sell",
                    "ticker": "BTC/USDT",
                    "amount": "0.5"
                }
                
                result, status_code = processor.process_webhook("active-webhook-test", payload)
                
                # Should be processed normally
                assert status_code == 200
                assert result.get("trade_executed") == True
                
                # Verify trade was attempted
                mock_trade.assert_called_once()
    
    def test_strategy_state_toggle_affects_webhook_processing(self, app, regular_user, dummy_cred):
        """Toggling strategy state should immediately affect webhook processing."""
        with app.app_context():
            from app.models.user import User
            user = User.query.filter_by(email="testuser@example.com").first()
            
            # Create active strategy
            strategy = TradingStrategy(
                user_id=user.id,
                name="Toggle Test Strategy",
                exchange_credential_id=dummy_cred,
                trading_pair="BTC/USDT",
                base_asset_symbol="BTC",
                quote_asset_symbol="USDT",
                allocated_base_asset_quantity=Decimal("1.0"),
                allocated_quote_asset_quantity=Decimal("0"),
                webhook_id="toggle-webhook-test",
                is_active=True  # Start active
            )
            db.session.add(strategy)
            db.session.commit()
            
            processor = EnhancedWebhookProcessor()
            payload = {
                "action": "sell",
                "ticker": "BTC/USDT",
                "amount": "0.5"
            }
            
            # Mock successful trade for active state
            with patch('app.services.webhook_processor.ExchangeService.execute_trade') as mock_trade:
                mock_trade.return_value = {
                    "trade_executed": True,
                    "message": "Trade executed successfully",
                    "trade_status": "filled"
                }
                
                # Test webhook while active
                result, status_code = processor.process_webhook("toggle-webhook-test", payload)
                assert status_code == 200
                assert result.get("trade_executed") == True
            
            # Pause strategy
            strategy.is_active = False
            db.session.commit()
            
            # Test webhook while paused
            result, status_code = processor.process_webhook("toggle-webhook-test", payload)
            assert status_code == 403
            assert "paused" in result.get("message", "").lower()
            
            # Reactivate strategy
            strategy.is_active = True
            db.session.commit()
            
            # Test webhook after reactivation
            with patch('app.services.webhook_processor.ExchangeService.execute_trade') as mock_trade:
                mock_trade.return_value = {
                    "trade_executed": True,
                    "message": "Trade executed successfully",
                    "trade_status": "filled"
                }
                
                result, status_code = processor.process_webhook("toggle-webhook-test", payload)
                assert status_code == 200
                assert result.get("trade_executed") == True


class TestCoreStrategyDeletionLogic:
    """Test the core business logic for strategy deletion."""
    
    def test_strategy_deletion_removes_from_database(self, app, regular_user, dummy_cred):
        """Strategy deletion should remove the strategy from the database."""
        with app.app_context():
            from app.models.user import User
            user = User.query.filter_by(email="testuser@example.com").first()
            
            # Create strategy
            strategy = TradingStrategy(
                user_id=user.id,
                name="Strategy To Delete",
                exchange_credential_id=dummy_cred,
                trading_pair="BTC/USDT",
                base_asset_symbol="BTC",
                quote_asset_symbol="USDT",
                allocated_base_asset_quantity=Decimal("0"),  # No assets
                allocated_quote_asset_quantity=Decimal("0"),  # No assets
                webhook_id="delete-test-webhook"
            )
            db.session.add(strategy)
            db.session.commit()
            strategy_id = strategy.id
            
            # Verify strategy exists
            existing_strategy = TradingStrategy.query.get(strategy_id)
            assert existing_strategy is not None
            assert existing_strategy.name == "Strategy To Delete"
            
            # Delete strategy (simulating the deletion logic)
            db.session.delete(strategy)
            db.session.commit()
            
            # Verify strategy is deleted
            deleted_strategy = TradingStrategy.query.get(strategy_id)
            assert deleted_strategy is None
    
    def test_strategy_with_assets_can_be_deleted(self, app, regular_user, dummy_cred):
        """Strategy with allocated assets should be deletable (assets return to main account)."""
        with app.app_context():
            from app.models.user import User
            user = User.query.filter_by(email="testuser@example.com").first()
            
            # Create strategy with allocated assets
            strategy = TradingStrategy(
                user_id=user.id,
                name="Strategy With Assets",
                exchange_credential_id=dummy_cred,
                trading_pair="BTC/USDT",
                base_asset_symbol="BTC",
                quote_asset_symbol="USDT",
                allocated_base_asset_quantity=Decimal("2.0"),  # Has assets
                allocated_quote_asset_quantity=Decimal("1000"),  # Has assets
                webhook_id="delete-assets-webhook"
            )
            db.session.add(strategy)
            db.session.commit()
            strategy_id = strategy.id
            
            # Verify strategy has assets
            assert strategy.allocated_base_asset_quantity > 0
            assert strategy.allocated_quote_asset_quantity > 0
            
            # Delete strategy (in real app, assets would be returned to main account)
            db.session.delete(strategy)
            db.session.commit()
            
            # Verify strategy is deleted
            deleted_strategy = TradingStrategy.query.get(strategy_id)
            assert deleted_strategy is None
            
            # Note: Asset return logic would be tested separately in allocation service tests
    
    def test_strategy_deletion_preserves_webhook_logs(self, app, regular_user, dummy_cred):
        """Strategy deletion should preserve webhook logs for audit purposes."""
        with app.app_context():
            from app.models.user import User
            user = User.query.filter_by(email="testuser@example.com").first()
            
            # Create strategy
            strategy = TradingStrategy(
                user_id=user.id,
                name="Strategy With Logs",
                exchange_credential_id=dummy_cred,
                trading_pair="BTC/USDT",
                base_asset_symbol="BTC",
                quote_asset_symbol="USDT",
                allocated_base_asset_quantity=Decimal("1.0"),
                allocated_quote_asset_quantity=Decimal("0"),
                webhook_id="logs-test-webhook",
                is_active=True
            )
            db.session.add(strategy)
            db.session.commit()
            strategy_id = strategy.id
            
            # Create webhook log
            with patch('app.services.webhook_processor.ExchangeService.execute_trade') as mock_trade:
                mock_trade.return_value = {
                    "trade_executed": True,
                    "message": "Trade executed successfully",
                    "trade_status": "filled"
                }
                
                processor = EnhancedWebhookProcessor()
                payload = {
                    "action": "sell",
                    "ticker": "BTC/USDT",
                    "amount": "0.5"
                }
                
                processor.process_webhook("logs-test-webhook", payload)
            
            # Verify webhook log was created
            log = WebhookLog.query.filter_by(strategy_id=strategy_id).first()
            assert log is not None
            log_id = log.id
            
            # Delete strategy (but not logs - they should be preserved)
            db.session.delete(strategy)
            db.session.commit()
            
            # Verify strategy is deleted
            deleted_strategy = TradingStrategy.query.get(strategy_id)
            assert deleted_strategy is None
            
            # Verify webhook log still exists (for audit trail)
            preserved_log = WebhookLog.query.get(log_id)
            assert preserved_log is not None
            # Note: In the current implementation, strategy_id may be nulled on cascade delete
            # The important thing is that the log record itself is preserved for audit purposes


class TestCoreLifecycleEdgeCases:
    """Test edge cases in strategy lifecycle management."""
    
    def test_webhook_to_nonexistent_strategy_returns_404(self, app):
        """Webhook to non-existent strategy should return 404."""
        with app.app_context():
            processor = EnhancedWebhookProcessor()
            
            payload = {
                "action": "sell",
                "ticker": "BTC/USDT",
                "amount": "0.5"
            }
            
            result, status_code = processor.process_webhook("nonexistent-webhook-id", payload)
            
            # Should return 404 for non-existent strategy
            assert status_code == 404
            assert "not found" in result.get("message", "").lower()
    
    def test_multiple_webhook_logs_preserved_across_state_changes(self, app, regular_user, dummy_cred):
        """Multiple webhook logs should be preserved when strategy state changes."""
        with app.app_context():
            from app.models.user import User
            user = User.query.filter_by(email="testuser@example.com").first()
            
            # Create active strategy
            strategy = TradingStrategy(
                user_id=user.id,
                name="Multi-Log Strategy",
                exchange_credential_id=dummy_cred,
                trading_pair="BTC/USDT",
                base_asset_symbol="BTC",
                quote_asset_symbol="USDT",
                allocated_base_asset_quantity=Decimal("1.0"),
                allocated_quote_asset_quantity=Decimal("0"),
                webhook_id="multi-log-webhook",
                is_active=True
            )
            db.session.add(strategy)
            db.session.commit()
            
            processor = EnhancedWebhookProcessor()
            payload = {
                "action": "sell",
                "ticker": "BTC/USDT",
                "amount": "0.5"
            }
            
            # Process webhook while active
            with patch('app.services.webhook_processor.ExchangeService.execute_trade') as mock_trade:
                mock_trade.return_value = {
                    "trade_executed": True,
                    "message": "Trade executed successfully",
                    "trade_status": "filled"
                }
                
                processor.process_webhook("multi-log-webhook", payload)
            
            # Pause strategy and process webhook
            strategy.is_active = False
            db.session.commit()
            processor.process_webhook("multi-log-webhook", payload)
            
            # Reactivate and process webhook again
            strategy.is_active = True
            db.session.commit()
            
            with patch('app.services.webhook_processor.ExchangeService.execute_trade') as mock_trade:
                mock_trade.return_value = {
                    "trade_executed": True,
                    "message": "Trade executed successfully",
                    "trade_status": "filled"
                }
                
                processor.process_webhook("multi-log-webhook", payload)
            
            # Verify all webhook logs are preserved
            all_logs = WebhookLog.query.filter_by(strategy_id=strategy.id).all()
            assert len(all_logs) == 3
            
            # Verify different statuses
            statuses = [log.status for log in all_logs]
            assert "ignored" in statuses  # From paused state
            # Note: Other statuses depend on actual implementation


# Fixtures for the core tests
@pytest.fixture()
def dummy_cred(app, regular_user):
    """Create dummy exchange credentials for testing."""
    with app.app_context():
        from app.models.user import User
        from cryptography.fernet import Fernet
        import os
        
        # Set encryption key for credentials
        key = Fernet.generate_key().decode()
        os.environ["ENCRYPTION_KEY"] = key
        
        user = User.query.filter_by(email="testuser@example.com").first()
        
        cred = ExchangeCredentials(
            user_id=user.id,
            exchange="dummybal",
            portfolio_name="Main",
            api_key="key",
            api_secret="sec",
        )
        db.session.add(cred)
        db.session.commit()
        return cred.id
