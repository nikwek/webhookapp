import os
from decimal import Decimal

import pytest
from cryptography.fernet import Fernet

from app import db
from app.models.trading import TradingStrategy
from app.models.exchange_credentials import ExchangeCredentials
from app.exchanges.registry import ExchangeRegistry
from app.services import allocation_service


class DummyBalanceAdapter:
    """Stub adapter returning a canned balance payload compatible with get_unallocated_balance."""

    # Balances dict will be injected by monkeypatch per‐test
    balances_map = {}

    @classmethod
    def get_portfolio_value(cls, user_id=None, portfolio_id=None, target_currency="USD"):
        balances = [
            {"asset": sym, "total": str(total), "available": str(total), "usd_value": 0}
            for sym, total in cls.balances_map.items()
        ]
        return {"success": True, "balances": balances}

    @staticmethod
    def get_display_name():
        return "DummyBalEx"


@pytest.fixture(autouse=True)
def _set_encryption_key(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    yield


@pytest.fixture()
def dummy_cred(app, regular_user):
    with app.app_context():
        # Re-query user to ensure it's attached to current session
        from app.models.user import User
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
        # Return the ID to avoid session issues
        return cred.id


@pytest.fixture()
def dummy_strategy(app, regular_user, dummy_cred):
    with app.app_context():
        # Re-query user to ensure it's attached to current session
        from app.models.user import User
        user = User.query.filter_by(email="testuser@example.com").first()
        
        strat = TradingStrategy(
            user_id=user.id,
            name="Strat",
            exchange_credential_id=dummy_cred,  # dummy_cred now returns ID
            trading_pair="BTC/USDT",
            base_asset_symbol="BTC",
            quote_asset_symbol="USDT",
        )
        db.session.add(strat)
        db.session.commit()
        # Return the ID to avoid session issues
        return strat.id


@pytest.fixture()
def patch_adapter(monkeypatch):
    # Replace registry lookup with our dummy adapter
    monkeypatch.setattr(ExchangeRegistry, "get_adapter", lambda _ex: DummyBalanceAdapter)
    yield


class TestAssetTransfer:
    def test_main_to_strategy_success(self, app, regular_user, dummy_cred, dummy_strategy, patch_adapter):
        # Provide 5 BTC balance on main account
        DummyBalanceAdapter.balances_map = {"BTC": Decimal("5")}

        with app.app_context():
            # Re-query user to ensure it's attached to current session
            from app.models.user import User
            user = User.query.filter_by(email="testuser@example.com").first()
            
            success, msg = allocation_service.execute_internal_asset_transfer(
                user_id=user.id,
                source_identifier=f"main::{dummy_cred}::BTC",  # dummy_cred is now ID
                destination_identifier=f"strategy::{dummy_strategy}",  # dummy_strategy is now ID
                asset_symbol_to_transfer="BTC",
                amount=Decimal("2.5"),
            )
            assert success is True
            # Query the strategy to check the result
            strategy = TradingStrategy.query.get(dummy_strategy)
            assert strategy.allocated_base_asset_quantity == Decimal("2.5")

    def test_cannot_over_allocate(self, app, regular_user, dummy_cred, dummy_strategy, patch_adapter):
        # Only 1 BTC balance on main account -> transfer 2 should fail
        DummyBalanceAdapter.balances_map = {"BTC": Decimal("1")}

        with app.app_context():
            # Re-query user to ensure it's attached to current session
            from app.models.user import User
            user = User.query.filter_by(email="testuser@example.com").first()
            
            with pytest.raises(allocation_service.AllocationError):
                allocation_service.execute_internal_asset_transfer(
                    user_id=user.id,
                    source_identifier=f"main::{dummy_cred}::BTC",  # dummy_cred is now ID
                    destination_identifier=f"strategy::{dummy_strategy}",  # dummy_strategy is now ID
                    asset_symbol_to_transfer="BTC",
                    amount=Decimal("2"),
                )

    def test_strategy_to_main_success(self, app, regular_user, dummy_cred, dummy_strategy, patch_adapter):
        DummyBalanceAdapter.balances_map = {"BTC": Decimal("10")}

        with app.app_context():
            # Re-query user to ensure it's attached to current session
            from app.models.user import User
            user = User.query.filter_by(email="testuser@example.com").first()
            
            # preload strategy with 3 BTC
            strategy = TradingStrategy.query.get(dummy_strategy)
            strategy.allocated_base_asset_quantity = Decimal("3")
            db.session.commit()
            # transfer 1 back
            success, _ = allocation_service.execute_internal_asset_transfer(
                user_id=user.id,
                source_identifier=f"strategy::{dummy_strategy}",  # dummy_strategy is now ID
                destination_identifier=f"main::{dummy_cred}::BTC",  # dummy_cred is now ID
                asset_symbol_to_transfer="BTC",
                amount=Decimal("1"),
            )
            assert success is True
            # Re-query the strategy to check the result
            strategy = TradingStrategy.query.get(dummy_strategy)
            assert strategy.allocated_base_asset_quantity == Decimal("2")
