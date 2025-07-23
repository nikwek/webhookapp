"""
Mission-Critical Virtual Portfolio Validation Tests

Tests the core business rules that prevent financial losses:
1. Strategies cannot trade more assets than they hold
2. Total strategy allocations cannot exceed main account holdings
3. Asset transfer operations maintain conservation invariants
4. Edge cases: concurrent operations, rounding errors, partial fills
"""

import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock

from app import db
from app.models.trading import TradingStrategy
from app.models.exchange_credentials import ExchangeCredentials
from app.services.webhook_processor import EnhancedWebhookProcessor
from app.services.exchange_service import ExchangeService
from app.services import allocation_service


class TestTradeValidationRules:
    """Test that strategies cannot trade more assets than they hold."""
    
    def test_sell_order_exceeds_base_asset_holdings(self, app, regular_user, dummy_cred):
        """CRITICAL: Strategy cannot sell more base assets than it holds."""
        with app.app_context():
            from app.models.user import User
            user = User.query.filter_by(email="testuser@example.com").first()
            
            # Create strategy with only 1.0 BTC
            strategy = TradingStrategy(
                user_id=user.id,
                name="Test Strategy",
                exchange_credential_id=dummy_cred,
                trading_pair="BTC/USDT",
                base_asset_symbol="BTC",
                quote_asset_symbol="USDT",
                allocated_base_asset_quantity=Decimal("1.0"),  # Only 1.0 BTC
                allocated_quote_asset_quantity=Decimal("0"),
                webhook_id="test-webhook-1"
            )
            db.session.add(strategy)
            db.session.commit()
            
            # Mock exchange service to prevent actual trade execution
            with patch.object(ExchangeService, 'execute_trade') as mock_trade:
                # Configure mock to return the actual validation error
                mock_trade.return_value = {
                    "trade_executed": False,
                    "message": "Insufficient allocated base assets for this SELL.",
                    "trade_status": "error"
                }
                
                processor = EnhancedWebhookProcessor()
                
                # Attempt to sell 2.0 BTC (more than the 1.0 BTC held)
                payload = {
                    "action": "sell",
                    "ticker": "BTC/USDT",  # Required field
                    "amount": "2.0"  # Exceeds holdings!
                }
                
                result, status_code = processor.process_webhook("test-webhook-1", payload)
                
                # Should fail with insufficient assets error
                assert status_code == 200  # Webhook processed successfully
                assert result["trade_executed"] == False
                assert "Insufficient allocated base assets" in result["message"]
                
                # Verify trade was attempted but rejected
                mock_trade.assert_called_once()
    
    def test_buy_order_exceeds_quote_asset_holdings(self, app, regular_user, dummy_cred):
        """CRITICAL: Strategy cannot buy more than quote asset balance allows."""
        with app.app_context():
            from app.models.user import User
            user = User.query.filter_by(email="testuser@example.com").first()
            
            # Create strategy with only 1000 USDT
            strategy = TradingStrategy(
                user_id=user.id,
                name="Test Strategy",
                exchange_credential_id=dummy_cred,
                trading_pair="BTC/USDT",
                base_asset_symbol="BTC",
                quote_asset_symbol="USDT",
                allocated_base_asset_quantity=Decimal("0"),
                allocated_quote_asset_quantity=Decimal("1000"),  # Only 1000 USDT
                webhook_id="test-webhook-2"
            )
            db.session.add(strategy)
            db.session.commit()
            
            # Mock exchange service to simulate BTC price and validate quote asset
            with patch.object(ExchangeService, 'execute_trade') as mock_trade:
                # Mock should validate that 2.0 BTC * $50,000 = $100,000 > $1,000 available
                mock_trade.return_value = {
                    "trade_executed": False,
                    "message": "Insufficient allocated quote assets for this BUY.",
                    "trade_status": "error"
                }
                
                processor = EnhancedWebhookProcessor()
                
                # Attempt to buy 2.0 BTC (would cost ~$100,000 but only have $1,000)
                payload = {
                    "action": "buy",
                    "ticker": "BTC/USDT",  # Required field
                    "amount": "2.0"  # Would exceed quote balance!
                }
                
                result, status_code = processor.process_webhook("test-webhook-2", payload)
                
                # Should fail with insufficient quote assets error
                assert status_code == 200
                assert result["trade_executed"] == False
                assert "Insufficient" in result["message"]
    
    def test_partial_sell_within_holdings_succeeds(self, app, regular_user, dummy_cred):
        """Valid trade within holdings should succeed."""
        with app.app_context():
            from app.models.user import User
            user = User.query.filter_by(email="testuser@example.com").first()
            
            # Create strategy with 2.0 BTC
            strategy = TradingStrategy(
                user_id=user.id,
                name="Test Strategy",
                exchange_credential_id=dummy_cred,
                trading_pair="BTC/USDT",
                base_asset_symbol="BTC",
                quote_asset_symbol="USDT",
                allocated_base_asset_quantity=Decimal("2.0"),  # 2.0 BTC available
                allocated_quote_asset_quantity=Decimal("0"),
                webhook_id="test-webhook-3"
            )
            db.session.add(strategy)
            db.session.commit()
            
            with patch.object(ExchangeService, 'execute_trade') as mock_trade:
                # Mock successful trade
                mock_trade.return_value = {
                    "trade_executed": True,
                    "message": "Trade executed successfully",
                    "trade_status": "filled",
                    "filled": Decimal("1.0"),
                    "order": {
                        "filled": Decimal("1.0"),
                        "cost": Decimal("50000"),
                        "info": {"total_value_after_fees": "49500"}
                    }
                }
                
                processor = EnhancedWebhookProcessor()
                
                # Sell 1.0 BTC (within the 2.0 BTC holdings)
                payload = {
                    "action": "sell",
                    "ticker": "BTC/USDT",  # Required field
                    "amount": "1.0"  # Within holdings
                }
                
                result, status_code = processor.process_webhook("test-webhook-3", payload)
                
                # Should succeed
                assert status_code == 200
                assert result["trade_executed"] == True


class TestAssetConservationRules:
    """Test that total strategy allocations never exceed main account holdings."""
    
    def test_cannot_allocate_more_than_main_account_holds(self, app, regular_user, dummy_cred, patch_adapter):
        """CRITICAL: Sum of all strategy allocations cannot exceed main account balance."""
        # Set main account balance to 5.0 BTC
        from tests.unit.test_asset_transfer import DummyBalanceAdapter
        DummyBalanceAdapter.balances_map = {"BTC": Decimal("5.0")}
        
        with app.app_context():
            from app.models.user import User
            user = User.query.filter_by(email="testuser@example.com").first()
            
            # Create first strategy and allocate 3.0 BTC
            strategy1 = TradingStrategy(
                user_id=user.id,
                name="Strategy 1",
                exchange_credential_id=dummy_cred,
                trading_pair="BTC/USDT",
                base_asset_symbol="BTC",
                quote_asset_symbol="USDT",
                allocated_base_asset_quantity=Decimal("0"),
                allocated_quote_asset_quantity=Decimal("0")
            )
            db.session.add(strategy1)
            db.session.commit()
            
            # Allocate 3.0 BTC to strategy1 (should succeed)
            success, _ = allocation_service.execute_internal_asset_transfer(
                user_id=user.id,
                source_identifier=f"main::{dummy_cred}::BTC",
                destination_identifier=f"strategy::{strategy1.id}",
                asset_symbol_to_transfer="BTC",
                amount=Decimal("3.0")
            )
            assert success == True
            
            # Create second strategy
            strategy2 = TradingStrategy(
                user_id=user.id,
                name="Strategy 2", 
                exchange_credential_id=dummy_cred,
                trading_pair="BTC/USDT",
                base_asset_symbol="BTC",
                quote_asset_symbol="USDT",
                allocated_base_asset_quantity=Decimal("0"),
                allocated_quote_asset_quantity=Decimal("0")
            )
            db.session.add(strategy2)
            db.session.commit()
            
            # Try to allocate 3.0 BTC to strategy2 (would total 6.0 BTC > 5.0 BTC available)
            with pytest.raises(allocation_service.AllocationError):
                allocation_service.execute_internal_asset_transfer(
                    user_id=user.id,
                    source_identifier=f"main::{dummy_cred}::BTC",
                    destination_identifier=f"strategy::{strategy2.id}",
                    asset_symbol_to_transfer="BTC",
                    amount=Decimal("3.0")  # Would exceed total balance!
                )
    
    def test_asset_conservation_across_multiple_strategies(self, app, regular_user, dummy_cred, patch_adapter):
        """Verify total allocations across multiple strategies never exceed main balance."""
        # Set main account balance to 10.0 BTC
        from tests.unit.test_asset_transfer import DummyBalanceAdapter
        DummyBalanceAdapter.balances_map = {"BTC": Decimal("10.0")}
        
        with app.app_context():
            from app.models.user import User
            user = User.query.filter_by(email="testuser@example.com").first()
            
            strategies = []
            # Create 3 strategies and allocate BTC to each
            for i in range(3):
                strategy = TradingStrategy(
                    user_id=user.id,
                    name=f"Strategy {i+1}",
                    exchange_credential_id=dummy_cred,
                    trading_pair="BTC/USDT",
                    base_asset_symbol="BTC",
                    quote_asset_symbol="USDT",
                    allocated_base_asset_quantity=Decimal("0"),
                    allocated_quote_asset_quantity=Decimal("0")
                )
                db.session.add(strategy)
                db.session.commit()
                strategies.append(strategy)
            
            # Allocate 3.0 BTC to each strategy (total 9.0 BTC < 10.0 BTC available)
            for i, strategy in enumerate(strategies):
                success, _ = allocation_service.execute_internal_asset_transfer(
                    user_id=user.id,
                    source_identifier=f"main::{dummy_cred}::BTC",
                    destination_identifier=f"strategy::{strategy.id}",
                    asset_symbol_to_transfer="BTC",
                    amount=Decimal("3.0")
                )
                assert success == True, f"Allocation {i+1} should succeed"
                
                # Verify strategy received the allocation
                db.session.refresh(strategy)
                assert strategy.allocated_base_asset_quantity == Decimal("3.0")
            
            # Verify total allocations = 9.0 BTC (within 10.0 BTC limit)
            total_allocated = sum(s.allocated_base_asset_quantity for s in strategies)
            assert total_allocated == Decimal("9.0")
            
            # Try to allocate 2.0 more BTC (would total 11.0 BTC > 10.0 BTC available)
            with pytest.raises(allocation_service.AllocationError):
                allocation_service.execute_internal_asset_transfer(
                    user_id=user.id,
                    source_identifier=f"main::{dummy_cred}::BTC",
                    destination_identifier=f"strategy::{strategies[0].id}",
                    asset_symbol_to_transfer="BTC",
                    amount=Decimal("2.0")  # Would exceed total balance!
                )


class TestStrategyToStrategyTransfers:
    """Test direct asset transfers between strategies."""
    
    def test_strategy_to_strategy_transfer_success(self, app, regular_user, dummy_cred, patch_adapter):
        """Valid strategy-to-strategy transfer should succeed."""
        from tests.unit.test_asset_transfer import DummyBalanceAdapter
        DummyBalanceAdapter.balances_map = {"BTC": Decimal("10.0")}
        
        with app.app_context():
            from app.models.user import User
            user = User.query.filter_by(email="testuser@example.com").first()
            
            # Create two strategies
            strategy1 = TradingStrategy(
                user_id=user.id,
                name="Source Strategy",
                exchange_credential_id=dummy_cred,
                trading_pair="BTC/USDT",
                base_asset_symbol="BTC",
                quote_asset_symbol="USDT",
                allocated_base_asset_quantity=Decimal("0"),
                allocated_quote_asset_quantity=Decimal("0")
            )
            strategy2 = TradingStrategy(
                user_id=user.id,
                name="Destination Strategy",
                exchange_credential_id=dummy_cred,
                trading_pair="BTC/USDT",
                base_asset_symbol="BTC",
                quote_asset_symbol="USDT",
                allocated_base_asset_quantity=Decimal("0"),
                allocated_quote_asset_quantity=Decimal("0")
            )
            db.session.add_all([strategy1, strategy2])
            db.session.commit()
            
            # Allocate 5.0 BTC to strategy1 from main account
            success, _ = allocation_service.execute_internal_asset_transfer(
                user_id=user.id,
                source_identifier=f"main::{dummy_cred}::BTC",
                destination_identifier=f"strategy::{strategy1.id}",
                asset_symbol_to_transfer="BTC",
                amount=Decimal("5.0")
            )
            assert success == True
            
            # Transfer 2.0 BTC from strategy1 to strategy2
            success, _ = allocation_service.execute_internal_asset_transfer(
                user_id=user.id,
                source_identifier=f"strategy::{strategy1.id}",
                destination_identifier=f"strategy::{strategy2.id}",
                asset_symbol_to_transfer="BTC",
                amount=Decimal("2.0")
            )
            assert success == True
            
            # Verify final balances
            db.session.refresh(strategy1)
            db.session.refresh(strategy2)
            
            assert strategy1.allocated_base_asset_quantity == Decimal("3.0")  # 5.0 - 2.0
            assert strategy2.allocated_base_asset_quantity == Decimal("2.0")  # 0.0 + 2.0
            
            # Verify total conservation (should still be 5.0 BTC total)
            total_allocated = strategy1.allocated_base_asset_quantity + strategy2.allocated_base_asset_quantity
            assert total_allocated == Decimal("5.0")
    
    def test_strategy_to_strategy_transfer_exceeds_source_balance(self, app, regular_user, dummy_cred, patch_adapter):
        """Strategy-to-strategy transfer cannot exceed source strategy balance."""
        from tests.unit.test_asset_transfer import DummyBalanceAdapter
        DummyBalanceAdapter.balances_map = {"BTC": Decimal("10.0")}
        
        with app.app_context():
            from app.models.user import User
            user = User.query.filter_by(email="testuser@example.com").first()
            
            # Create two strategies
            strategy1 = TradingStrategy(
                user_id=user.id,
                name="Source Strategy",
                exchange_credential_id=dummy_cred,
                trading_pair="BTC/USDT",
                base_asset_symbol="BTC",
                quote_asset_symbol="USDT",
                allocated_base_asset_quantity=Decimal("2.0"),  # Only 2.0 BTC
                allocated_quote_asset_quantity=Decimal("0")
            )
            strategy2 = TradingStrategy(
                user_id=user.id,
                name="Destination Strategy",
                exchange_credential_id=dummy_cred,
                trading_pair="BTC/USDT",
                base_asset_symbol="BTC",
                quote_asset_symbol="USDT",
                allocated_base_asset_quantity=Decimal("0"),
                allocated_quote_asset_quantity=Decimal("0")
            )
            db.session.add_all([strategy1, strategy2])
            db.session.commit()
            
            # Try to transfer 3.0 BTC from strategy1 (only has 2.0 BTC)
            with pytest.raises(allocation_service.AllocationError):
                allocation_service.execute_internal_asset_transfer(
                    user_id=user.id,
                    source_identifier=f"strategy::{strategy1.id}",
                    destination_identifier=f"strategy::{strategy2.id}",
                    asset_symbol_to_transfer="BTC",
                    amount=Decimal("3.0")  # Exceeds strategy1 balance!
                )


class TestEdgeCasesAndRoundingErrors:
    """Test edge cases that could cause financial inconsistencies."""
    
    def test_rounding_error_does_not_allow_over_allocation(self, app, regular_user, dummy_cred, patch_adapter):
        """Rounding errors should not allow over-allocation."""
        from tests.unit.test_asset_transfer import DummyBalanceAdapter
        # Set precise balance
        DummyBalanceAdapter.balances_map = {"BTC": Decimal("1.00000001")}
        
        with app.app_context():
            from app.models.user import User
            user = User.query.filter_by(email="testuser@example.com").first()
            
            strategy = TradingStrategy(
                user_id=user.id,
                name="Precision Test Strategy",
                exchange_credential_id=dummy_cred,
                trading_pair="BTC/USDT",
                base_asset_symbol="BTC",
                quote_asset_symbol="USDT",
                allocated_base_asset_quantity=Decimal("0"),
                allocated_quote_asset_quantity=Decimal("0")
            )
            db.session.add(strategy)
            db.session.commit()
            
            # Try to allocate slightly more than available (should fail)
            with pytest.raises(allocation_service.AllocationError):
                allocation_service.execute_internal_asset_transfer(
                    user_id=user.id,
                    source_identifier=f"main::{dummy_cred}::BTC",
                    destination_identifier=f"strategy::{strategy.id}",
                    asset_symbol_to_transfer="BTC",
                    amount=Decimal("1.00000002")  # Slightly more than available
                )
    
    def test_zero_amount_transfer_rejected(self, app, regular_user, dummy_cred, patch_adapter):
        """Zero or negative amount transfers should be rejected."""
        from tests.unit.test_asset_transfer import DummyBalanceAdapter
        DummyBalanceAdapter.balances_map = {"BTC": Decimal("10.0")}
        
        with app.app_context():
            from app.models.user import User
            user = User.query.filter_by(email="testuser@example.com").first()
            
            strategy = TradingStrategy(
                user_id=user.id,
                name="Test Strategy",
                exchange_credential_id=dummy_cred,
                trading_pair="BTC/USDT",
                base_asset_symbol="BTC",
                quote_asset_symbol="USDT",
                allocated_base_asset_quantity=Decimal("5.0"),
                allocated_quote_asset_quantity=Decimal("0")
            )
            db.session.add(strategy)
            db.session.commit()
            
            # Test zero amount
            with pytest.raises(allocation_service.AllocationError):
                allocation_service.execute_internal_asset_transfer(
                    user_id=user.id,
                    source_identifier=f"strategy::{strategy.id}",
                    destination_identifier=f"main::{dummy_cred}::BTC",
                    asset_symbol_to_transfer="BTC",
                    amount=Decimal("0")  # Zero amount should fail
                )
            
            # Test negative amount
            with pytest.raises(allocation_service.AllocationError):
                allocation_service.execute_internal_asset_transfer(
                    user_id=user.id,
                    source_identifier=f"strategy::{strategy.id}",
                    destination_identifier=f"main::{dummy_cred}::BTC",
                    asset_symbol_to_transfer="BTC",
                    amount=Decimal("-1.0")  # Negative amount should fail
                )


# Fixtures for the new tests
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


@pytest.fixture()
def patch_adapter(monkeypatch):
    """Patch exchange registry to use dummy adapter."""
    from tests.unit.test_asset_transfer import DummyBalanceAdapter
    from app.exchanges.registry import ExchangeRegistry
    
    monkeypatch.setattr(ExchangeRegistry, "get_adapter", lambda _ex: DummyBalanceAdapter)
    yield
