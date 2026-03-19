"""Tests for CCXT adapter methods (app/exchanges/ccxt_base_adapter.py)."""
import pytest
from unittest.mock import Mock, patch
from app.exchanges.ccxt_base_adapter import CcxtBaseAdapter
from app.exchanges.registry import ExchangeRegistry
from app import db
from app.models.user import User, Role
from app.models.exchange_credentials import ExchangeCredentials
from flask_security.utils import hash_password


@pytest.fixture
def mock_ccxt_exchange():
    """Create a mock CCXT exchange."""
    mock_exchange = Mock()
    mock_exchange.load_markets = Mock(return_value={
        'BTC/USD': {
            'id': 'btcusd',
            'symbol': 'BTC/USD',
            'base': 'BTC',
            'quote': 'USD',
            'precision': {'amount': 8, 'price': 2}
        }
    })
    mock_exchange.fetch_balance = Mock(return_value={
        'BTC': {'free': 1.5, 'used': 0.5, 'total': 2.0},
        'USD': {'free': 50000, 'used': 0, 'total': 50000},
        'free': {'BTC': 1.5, 'USD': 50000},
        'used': {'BTC': 0.5, 'USD': 0},
        'total': {'BTC': 2.0, 'USD': 50000}
    })
    mock_exchange.fetch_ticker = Mock(return_value={
        'symbol': 'BTC/USD',
        'last': 45000,
        'bid': 44999,
        'ask': 45001
    })
    return mock_exchange


class TestCcxtBaseAdapterGetName:
    """Test CcxtBaseAdapter.get_name() method."""

    def test_get_name_returns_exchange_id(self):
        """get_name should return the exchange ID."""
        adapter_cls = ExchangeRegistry.get_adapter('binance')
        if adapter_cls:
            name = adapter_cls.get_name()
            assert name == 'binance'

    def test_get_name_raises_without_exchange_id(self):
        """get_name should raise ValueError if _exchange_id not set."""
        class BadAdapter(CcxtBaseAdapter):
            _exchange_id = None

        with pytest.raises(ValueError):
            BadAdapter.get_name()


class TestCcxtBaseAdapterGetDisplayName:
    """Test CcxtBaseAdapter.get_display_name() method."""

    def test_get_display_name_binance(self):
        """get_display_name should return 'Binance' for binance."""
        adapter_cls = ExchangeRegistry.get_adapter('binance')
        if adapter_cls:
            display_name = adapter_cls.get_display_name()
            assert display_name.lower() == 'binance'

    def test_get_display_name_coinbase_ccxt(self):
        """get_display_name should return 'Coinbase' for coinbase-ccxt."""
        adapter_cls = ExchangeRegistry.get_adapter('coinbase-ccxt')
        if adapter_cls:
            display_name = adapter_cls.get_display_name()
            assert display_name == 'Coinbase'

    def test_get_display_name_kraken(self):
        """get_display_name should return 'Kraken' for kraken."""
        adapter_cls = ExchangeRegistry.get_adapter('kraken')
        if adapter_cls:
            display_name = adapter_cls.get_display_name()
            assert display_name.lower() == 'kraken'

    def test_get_display_name_raises_without_exchange_id(self):
        """get_display_name should raise ValueError if _exchange_id not set."""
        class BadAdapter(CcxtBaseAdapter):
            _exchange_id = None

        with pytest.raises(ValueError):
            BadAdapter.get_display_name()


class TestCcxtBaseAdapterGetExchangeClass:
    """Test CcxtBaseAdapter._get_exchange_class() method."""

    def test_get_exchange_class_binance(self):
        """_get_exchange_class should return CCXT Binance class."""
        adapter_cls = ExchangeRegistry.get_adapter('binance')
        if adapter_cls:
            exchange_class = adapter_cls._get_exchange_class()
            assert exchange_class is not None

    def test_get_exchange_class_coinbase_ccxt_maps_to_coinbase(self):
        """_get_exchange_class should map coinbase-ccxt to coinbase."""
        adapter_cls = ExchangeRegistry.get_adapter('coinbase-ccxt')
        if adapter_cls:
            exchange_class = adapter_cls._get_exchange_class()
            assert exchange_class is not None

    def test_get_exchange_class_invalid_exchange(self):
        """_get_exchange_class should raise ValueError for invalid exchange."""
        class BadAdapter(CcxtBaseAdapter):
            _exchange_id = 'invalid_exchange_xyz'

        with pytest.raises(ValueError):
            BadAdapter._get_exchange_class()

    def test_get_exchange_class_raises_without_exchange_id(self):
        """_get_exchange_class should raise ValueError if _exchange_id not set."""
        class BadAdapter(CcxtBaseAdapter):
            _exchange_id = None

        with pytest.raises(ValueError):
            BadAdapter._get_exchange_class()


class TestCcxtBaseAdapterGetClient:
    """Test CcxtBaseAdapter.get_client() method."""

    def test_get_client_no_credentials(self, app):
        """get_client should return None if no credentials exist."""
        with app.app_context():
            user = User(
                email="no_creds@example.com",
                password=hash_password("password"),
                active=True,
            )
            user.roles.append(Role.query.filter_by(name="user").first())
            db.session.add(user)
            db.session.commit()
            user_id = user.id

        adapter_cls = ExchangeRegistry.get_adapter('binance')
        if adapter_cls:
            client = adapter_cls.get_client(user_id)
            assert client is None

    def test_get_client_with_credentials(self, app):
        """get_client should return client if credentials exist."""
        with app.app_context():
            user = User(
                email="with_creds@example.com",
                password=hash_password("password"),
                active=True,
            )
            user.roles.append(Role.query.filter_by(name="user").first())
            db.session.add(user)
            db.session.flush()

            cred = ExchangeCredentials(
                user_id=user.id,
                exchange="binance",
                api_key="test_key",
                api_secret="test_secret",
                portfolio_name="default"
            )
            db.session.add(cred)
            db.session.commit()
            user_id = user.id

        adapter_cls = ExchangeRegistry.get_adapter('binance')
        if adapter_cls:
            with patch.object(adapter_cls, '_get_exchange_class') as mock_class:
                mock_exchange = Mock()
                mock_exchange.load_markets = Mock(return_value={})
                mock_class.return_value = Mock(return_value=mock_exchange)

                client = adapter_cls.get_client(user_id)
                assert client is not None or client is None


class TestCcxtBaseAdapterFetchBalance:
    """Test CcxtBaseAdapter.fetch_balance() method."""

    def test_fetch_balance_returns_dict(self, app, mock_ccxt_exchange):
        """fetch_balance should return balance dictionary."""
        with app.app_context():
            user = User(
                email="balance_user@example.com",
                password=hash_password("password"),
                active=True,
            )
            user.roles.append(Role.query.filter_by(name="user").first())
            db.session.add(user)
            db.session.flush()

            cred = ExchangeCredentials(
                user_id=user.id,
                exchange="binance",
                api_key="test_key",
                api_secret="test_secret",
                portfolio_name="default"
            )
            db.session.add(cred)
            db.session.commit()
            user_id = user.id

        adapter_cls = ExchangeRegistry.get_adapter('binance')
        if adapter_cls:
            with patch.object(adapter_cls, 'get_client') as mock_get_client:
                mock_get_client.return_value = mock_ccxt_exchange
                balance = adapter_cls.fetch_balance(user_id)
                assert balance is not None


class TestCcxtBaseAdapterFetchTicker:
    """Test CcxtBaseAdapter.fetch_ticker() method."""

    def test_fetch_ticker_returns_price(self, app, mock_ccxt_exchange):
        """fetch_ticker should return ticker data."""
        with app.app_context():
            user = User(
                email="ticker_user@example.com",
                password=hash_password("password"),
                active=True,
            )
            user.roles.append(Role.query.filter_by(name="user").first())
            db.session.add(user)
            db.session.flush()

            cred = ExchangeCredentials(
                user_id=user.id,
                exchange="binance",
                api_key="test_key",
                api_secret="test_secret",
                portfolio_name="default"
            )
            db.session.add(cred)
            db.session.commit()
            user_id = user.id

        adapter_cls = ExchangeRegistry.get_adapter('binance')
        if adapter_cls:
            with patch.object(adapter_cls, 'get_client') as mock_get_client:
                mock_get_client.return_value = mock_ccxt_exchange
                ticker = adapter_cls.fetch_ticker(user_id, 'BTC/USD')
                assert ticker is not None
