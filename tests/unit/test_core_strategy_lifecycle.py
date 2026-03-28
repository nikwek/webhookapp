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
                # Run trade synchronously so mock assertions work
                from flask import current_app as _ca
                _app = _ca._get_current_object()
                processor._defer_trade_execution = lambda params: processor._execute_trade_with_context(_app, params)

                # Send webhook to active strategy
                payload = {
                    "action": "sell",
                    "ticker": "BTC/USDT",
                    "amount": "0.5"
                }

                result, status_code = processor.process_webhook("active-webhook-test", payload)

                # Should be accepted immediately
                assert status_code == 200
                assert result.get("received")

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
                assert result.get("received")

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
                assert result.get("received")


class TestCoreStrategyDeletionLogic:
    """Test the core business logic for strategy deletion."""
    
    def test_strategy_deletion_preserves_webhook_logs(self, app, regular_user, dummy_cred):
        """Strategy deletion should preserve webhook logs for audit purposes."""
        with app.app_context():
            from app.models.user import User
            user = User.query.filter_by(email="testuser@example.com").first()

            strategy = TradingStrategy(
                user_id=user.id,
                name="Strategy With Logs",
                exchange_credential_id=dummy_cred,
                trading_pair="BTC/USDT",
                base_asset_symbol="BTC",
                quote_asset_symbol="USDT",
                allocated_base_asset_quantity=Decimal("1.0"),
                allocated_quote_asset_quantity=Decimal("0"),
                webhook_id="logs-preserve-test-webhook",
                is_active=True
            )
            db.session.add(strategy)
            db.session.flush()  # get strategy.id without full commit
            strategy_id = strategy.id

            # Create a webhook log directly — we're testing DB cascade behaviour,
            # not the webhook processor, so no need for the full exchange stack.
            log = WebhookLog(
                strategy_id=strategy_id,
                payload={"action": "sell", "ticker": "BTC/USDT"},
                status="success",
                target_type="strategy",
            )
            db.session.add(log)
            db.session.commit()
            log_id = log.id

            # Delete the strategy
            db.session.delete(strategy)
            db.session.commit()

            # Strategy is gone
            assert db.session.get(TradingStrategy, strategy_id) is None

            # Log record still exists (audit trail must survive strategy deletion)
            preserved_log = db.session.get(WebhookLog, log_id)
            assert preserved_log is not None

            # Clean up the orphaned log so its strategy_id isn't reused by a
            # subsequent test's strategy (SQLite can reuse IDs after deletion).
            db.session.delete(preserved_log)
            db.session.commit()


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
            from flask import current_app as _ca
            _app = _ca._get_current_object()
            processor._defer_trade_execution = lambda params: processor._execute_trade_with_context(_app, params)

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


class TestSynchronousVsDeferredProcessing:
    """Tests for the synchronous/deferred trade execution split introduced to
    support both TradingView webhooks (fast 200 ack) and manual trades (blocking
    execution so the page reflects the outcome on redirect)."""

    def _make_strategy(self, user_id, cred_id, webhook_id):
        strategy = TradingStrategy(
            user_id=user_id,
            name=f"Sync Test {webhook_id}",
            exchange_credential_id=cred_id,
            trading_pair="BTC/USDT",
            base_asset_symbol="BTC",
            quote_asset_symbol="USDT",
            allocated_base_asset_quantity=Decimal("0"),
            allocated_quote_asset_quantity=Decimal("100"),
            webhook_id=webhook_id,
            is_active=True,
        )
        db.session.add(strategy)
        db.session.commit()
        return strategy

    def test_deferred_returns_received_ack_immediately(self, app, regular_user, dummy_cred):
        """synchronous=False (default) must return the fast ack before the trade runs."""
        with app.app_context():
            from app.models.user import User
            user = User.query.filter_by(email="testuser@example.com").first()
            strategy = self._make_strategy(user.id, dummy_cred, "deferred-sync-test")

            processor = EnhancedWebhookProcessor()
            # Prevent the background thread from actually running during this test
            processor._defer_trade_execution = lambda params: None

            payload = {"action": "buy", "ticker": "BTC/USDT"}
            result, status_code = processor._process_for_strategy(strategy, payload, synchronous=False)

            assert status_code == 200
            assert result.get("received") is True
            assert result.get("message") == "Webhook received"

    def test_deferred_spawns_background_trade(self, app, regular_user, dummy_cred):
        """synchronous=False must hand off the trade to _defer_trade_execution."""
        with app.app_context():
            from app.models.user import User
            user = User.query.filter_by(email="testuser@example.com").first()
            strategy = self._make_strategy(user.id, dummy_cred, "deferred-spawn-test")

            processor = EnhancedWebhookProcessor()
            deferred_calls = []
            processor._defer_trade_execution = lambda params: deferred_calls.append(params)

            payload = {"action": "buy", "ticker": "BTC/USDT"}
            processor._process_for_strategy(strategy, payload, synchronous=False)

            assert len(deferred_calls) == 1
            assert deferred_calls[0]["action"] == "buy"
            assert deferred_calls[0]["strategy_id"] == strategy.id

    def test_synchronous_executes_trade_inline(self, app, regular_user, dummy_cred):
        """synchronous=True must call the exchange and return the real trade result."""
        with app.app_context():
            from app.models.user import User
            user = User.query.filter_by(email="testuser@example.com").first()
            strategy = self._make_strategy(user.id, dummy_cred, "sync-inline-test")

            with patch('app.services.webhook_processor.ExchangeService.execute_trade') as mock_trade:
                mock_trade.return_value = {
                    "trade_executed": True,
                    "trade_status": "filled",
                    "message": "Trade executed successfully",
                }

                processor = EnhancedWebhookProcessor()
                payload = {"action": "buy", "ticker": "BTC/USDT"}
                result, status_code = processor._process_for_strategy(strategy, payload, synchronous=True)

            assert status_code == 200
            mock_trade.assert_called_once()
            # Synchronous path must NOT return the fast-ack envelope
            assert result.get("received") is not True

    def test_synchronous_creates_webhook_log(self, app, regular_user, dummy_cred):
        """synchronous=True must persist a WebhookLog before returning."""
        with app.app_context():
            from app.models.user import User
            user = User.query.filter_by(email="testuser@example.com").first()
            strategy = self._make_strategy(user.id, dummy_cred, "sync-log-test")

            with patch('app.services.webhook_processor.ExchangeService.execute_trade') as mock_trade:
                mock_trade.return_value = {
                    "trade_executed": True,
                    "trade_status": "filled",
                    "message": "Trade executed successfully",
                }

                processor = EnhancedWebhookProcessor()
                payload = {"action": "buy", "ticker": "BTC/USDT"}
                processor._process_for_strategy(strategy, payload, synchronous=True)

            log = WebhookLog.query.filter_by(strategy_id=strategy.id).first()
            assert log is not None

    def test_synchronous_does_not_spawn_background_thread(self, app, regular_user, dummy_cred):
        """synchronous=True must not call _defer_trade_execution at all."""
        with app.app_context():
            from app.models.user import User
            user = User.query.filter_by(email="testuser@example.com").first()
            strategy = self._make_strategy(user.id, dummy_cred, "sync-no-defer-test")

            with patch('app.services.webhook_processor.ExchangeService.execute_trade') as mock_trade:
                mock_trade.return_value = {
                    "trade_executed": True,
                    "trade_status": "filled",
                    "message": "Trade executed successfully",
                }

                processor = EnhancedWebhookProcessor()
                deferred_calls = []
                processor._defer_trade_execution = lambda params: deferred_calls.append(params)

                payload = {"action": "buy", "ticker": "BTC/USDT"}
                processor._process_for_strategy(strategy, payload, synchronous=True)

            assert deferred_calls == [], "_defer_trade_execution must not be called in synchronous mode"

    def test_synchronous_propagates_trade_failure(self, app, regular_user, dummy_cred):
        """synchronous=True must surface exchange errors to the caller."""
        with app.app_context():
            from app.models.user import User
            user = User.query.filter_by(email="testuser@example.com").first()
            strategy = self._make_strategy(user.id, dummy_cred, "sync-fail-test")

            with patch('app.services.webhook_processor.ExchangeService.execute_trade') as mock_trade:
                mock_trade.side_effect = Exception("Exchange unavailable")

                processor = EnhancedWebhookProcessor()
                payload = {"action": "buy", "ticker": "BTC/USDT"}
                result, status_code = processor._process_for_strategy(strategy, payload, synchronous=True)

            assert status_code == 500
            assert "error" in result.get("message", "").lower() or not result.get("success", True)


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
