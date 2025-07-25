import os
import pytest
from cryptography.fernet import Fernet

from app import db
from app.models.trading import TradingStrategy
from app.models.exchange_credentials import ExchangeCredentials
from app.exchanges.registry import ExchangeRegistry


class DummyAdapter:
    """Minimal exchange adapter used solely for route tests."""

    @staticmethod
    def get_trading_pairs(user_id=None):  # noqa: D401, E501
        # Mirror the structure returned by real adapters
        return [{"id": "BTC/USDT"}, {"id": "ETH/USDT"}]

    @staticmethod
    def get_display_name():  # noqa: D401
        return "DummyEx"


@pytest.fixture(autouse=True)
def _set_encryption_key(monkeypatch):
    """Ensure the Fernet key is present so ExchangeCredentials encryption works."""
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("ENCRYPTION_KEY", key)
    yield


@pytest.fixture(scope="function")
def dummy_credential(app, regular_user):
    """Create an ExchangeCredentials object for the dummy exchange."""
    with app.app_context():
        # Re-query user to ensure it's attached to current session
        from app.models.user import User
        user = User.query.filter_by(email="testuser@example.com").first()
        
        cred = ExchangeCredentials(
            user_id=user.id,
            exchange="dummyex",
            portfolio_name="Main",
            api_key="key",
            api_secret="secret",
        )
        db.session.add(cred)
        db.session.commit()
        return cred.id  # Return ID to avoid session issues


@pytest.mark.parametrize(
    "pair, expect_success",
    [
        ("BTC/USDT", True),
        ("BTC-USDT", True),
        ("BTC USDT", True),
        ("BTCUSDT", False),  # missing delimiter
        ("FOO/BAR", False),  # unsupported trading pair
    ],
)
def test_create_trading_strategy(
    auth_client,
    app,
    monkeypatch,
    regular_user,
    dummy_credential,
    pair,
    expect_success,
):
    """Verify trading‐pair parsing and validation logic in the strategy-creation route.

    We use a logged-in client to hit the route. The database may contain seed data
    created during app initialisation, so we compare counts before/after the POST
    instead of assuming an empty table.
    """

    # Always return DummyAdapter for this exchange
    monkeypatch.setattr(ExchangeRegistry, "get_adapter", lambda _id: DummyAdapter)

    with app.app_context():
        initial_count = TradingStrategy.query.count()

    # Use unique strategy name to avoid conflicts between test cases
    unique_strategy_name = f"TestStrat_{pair.replace('/', '_').replace('-', '_').replace(' ', '_')}"
    
    resp = auth_client.post(
        "/exchange/dummyex/strategy/create",
        data={"strategy_name": unique_strategy_name, "trading_pair": pair},
        follow_redirects=False,
    )
    assert resp.status_code == 302  # route redirects back to exchange page

    with app.app_context():
        strategies = TradingStrategy.query.all()
        if expect_success:
            # Check that exactly one strategy with our unique name was created
            assert TradingStrategy.query.filter_by(name=unique_strategy_name).count() == 1, (
                f"{pair} should have created exactly one '{unique_strategy_name}' record"
            )
            # Check that the strategy was created successfully (more robust than count comparison)
            strat = TradingStrategy.query.filter_by(name=unique_strategy_name).first()
            assert strat is not None, f"Strategy '{unique_strategy_name}' should exist"
            # Normalisation check on the newly created record
            assert strat.trading_pair == "BTC/USDT"
        else:
            # No new rows added
            assert TradingStrategy.query.count() == initial_count
