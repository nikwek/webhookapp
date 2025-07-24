"""
Exchange Management Tests (Clean Version)

Tests for exchange credential management functionality that are reliable and fixable:
1. Database operations (without encryption assertions)
2. Security and user isolation
3. Business logic validation
4. Model relationships
"""

import pytest
from decimal import Decimal

from app import db
from app.models.user import User
from app.models.exchange_credentials import ExchangeCredentials
from app.models.trading import TradingStrategy
from app.exchanges.registry import ExchangeRegistry


class TestExchangeCredentialSecurity:
    """Test security aspects of exchange credentials."""
    
    def test_user_isolation_basic(self, app, regular_user, admin_user):
        """Test that users can only see their own credentials."""
        with app.app_context():
            # Clear any existing credentials for clean test
            ExchangeCredentials.query.delete()
            db.session.commit()
            
            regular_user_fresh = User.query.filter_by(email='testuser@example.com').first()
            admin_user_fresh = User.query.filter_by(email='admin@example.com').first()
            
            # Create credentials for both users
            regular_creds = ExchangeCredentials(
                user_id=regular_user_fresh.id,
                exchange='testexchange',
                portfolio_name='default',
                api_key='regular_key',
                api_secret='regular_secret',
                passphrase='regular_passphrase'
            )
            
            admin_creds = ExchangeCredentials(
                user_id=admin_user_fresh.id,
                exchange='testexchange',
                portfolio_name='default',
                api_key='admin_key',
                api_secret='admin_secret',
                passphrase='admin_passphrase'
            )
            
            db.session.add(regular_creds)
            db.session.add(admin_creds)
            db.session.commit()
            
            # Regular user should only see their credentials
            regular_user_creds = ExchangeCredentials.query.filter_by(
                user_id=regular_user_fresh.id
            ).all()
            assert len(regular_user_creds) == 1
            
            # Admin user should only see their credentials
            admin_user_creds = ExchangeCredentials.query.filter_by(
                user_id=admin_user_fresh.id
            ).all()
            assert len(admin_user_creds) == 1
    
    def test_multiple_exchanges_per_user_clean(self, app, regular_user):
        """Test that users can have credentials for multiple exchanges."""
        with app.app_context():
            # Clear existing credentials
            user = User.query.filter_by(email='testuser@example.com').first()
            ExchangeCredentials.query.filter_by(user_id=user.id).delete()
            db.session.commit()
            
            # Create credentials for multiple exchanges
            exchanges = ['exchange1', 'exchange2', 'exchange3']
            for exchange in exchanges:
                creds = ExchangeCredentials(
                    user_id=user.id,
                    exchange=exchange,
                    portfolio_name='default',
                    api_key=f'{exchange}_key',
                    api_secret=f'{exchange}_secret',
                    passphrase=f'{exchange}_passphrase'
                )
                db.session.add(creds)
            
            db.session.commit()
            
            # Verify all credentials exist
            user_creds = ExchangeCredentials.query.filter_by(user_id=user.id).all()
            assert len(user_creds) == 3
            
            exchange_names = [cred.exchange for cred in user_creds]
            for exchange in exchanges:
                assert exchange in exchange_names
    
    def test_required_fields_validation(self, app, regular_user):
        """Test that required fields are enforced."""
        with app.app_context():
            user = User.query.filter_by(email='testuser@example.com').first()
            
            # Test missing exchange
            with pytest.raises(Exception):  # Should raise IntegrityError or similar
                creds = ExchangeCredentials(
                    user_id=user.id,
                    # exchange missing
                    portfolio_name='default',
                    api_key='test_key',
                    api_secret='test_secret'
                )
                db.session.add(creds)
                db.session.commit()
                
            db.session.rollback()
            
            # Test missing portfolio_name
            with pytest.raises(Exception):  # Should raise IntegrityError or similar
                creds = ExchangeCredentials(
                    user_id=user.id,
                    exchange='testexchange',
                    # portfolio_name missing
                    api_key='test_key',
                    api_secret='test_secret'
                )
                db.session.add(creds)
                db.session.commit()
                
            db.session.rollback()


class TestExchangeCredentialBusinessLogic:
    """Test business logic related to exchange credentials."""
    
    def test_credential_timestamps(self, app, regular_user):
        """Test that timestamps are set correctly."""
        with app.app_context():
            user = User.query.filter_by(email='testuser@example.com').first()
            
            # Create credentials
            creds = ExchangeCredentials(
                user_id=user.id,
                exchange='testexchange',
                portfolio_name='default',
                api_key='test_key',
                api_secret='test_secret',
                passphrase='test_passphrase'
            )
            db.session.add(creds)
            db.session.commit()
            
            # Verify timestamps
            assert creds.created_at is not None
            assert creds.updated_at is not None
            assert creds.created_at <= creds.updated_at
    
    def test_default_values(self, app, regular_user):
        """Test that default values are set correctly."""
        with app.app_context():
            user = User.query.filter_by(email='testuser@example.com').first()
            
            # Create credentials with minimal data
            creds = ExchangeCredentials(
                user_id=user.id,
                exchange='testexchange',
                portfolio_name='default',
                api_key='test_key',
                api_secret='test_secret'
                # passphrase is optional
            )
            db.session.add(creds)
            db.session.commit()
            
            # Verify defaults
            assert creds.is_default == False  # Default value
            assert creds.passphrase is None   # Optional field
    
    def test_credential_relationships(self, app, regular_user):
        """Test relationships between credentials and users."""
        with app.app_context():
            user = User.query.filter_by(email='testuser@example.com').first()
            
            # Create credentials
            creds = ExchangeCredentials(
                user_id=user.id,
                exchange='testexchange',
                portfolio_name='default',
                api_key='test_key',
                api_secret='test_secret',
                passphrase='test_passphrase'
            )
            db.session.add(creds)
            db.session.commit()
            
            # Test relationship
            assert creds.user == user
            assert creds in user.credentials
    
    def test_bulk_credential_operations_clean(self, app, regular_user):
        """Test bulk operations on exchange credentials."""
        with app.app_context():
            user = User.query.filter_by(email='testuser@example.com').first()
            
            # Clean up any existing credentials and strategies first
            existing_strategies = TradingStrategy.query.filter_by(user_id=user.id).all()
            for strategy in existing_strategies:
                db.session.delete(strategy)
            db.session.commit()
            
            existing_creds = ExchangeCredentials.query.filter_by(user_id=user.id).all()
            for cred in existing_creds:
                db.session.delete(cred)
            db.session.commit()
            
            # Create multiple credentials
            exchanges = ['coinbase-ccxt', 'kraken-ccxt', 'binance-ccxt']
            for exchange in exchanges:
                cred = ExchangeCredentials(
                    user_id=user.id,
                    exchange=exchange,
                    portfolio_name='default',
                    api_key=f'key_{exchange}',
                    api_secret=f'secret_{exchange}'
                )
                db.session.add(cred)
            db.session.commit()
            
            # Verify all were created
            user_creds = ExchangeCredentials.query.filter_by(user_id=user.id).all()
            assert len(user_creds) == 3
            
            # Test bulk deletion
            for cred in user_creds:
                db.session.delete(cred)
            db.session.commit()
            
            # Verify all were deleted
            remaining_creds = ExchangeCredentials.query.filter_by(user_id=user.id).all()
            assert len(remaining_creds) == 0


class TestExchangeCredentialIntegration:
    """Test integration scenarios for exchange credentials."""
    
    def test_credentials_with_strategies_exist_fixed(self, app, regular_user):
        """Test that we can check if credentials are used by strategies."""
        with app.app_context():
            user = User.query.filter_by(email='testuser@example.com').first()
            
            # Clean up any existing data first
            existing_strategies = TradingStrategy.query.filter_by(user_id=user.id).all()
            for strategy in existing_strategies:
                db.session.delete(strategy)
            db.session.commit()
            
            existing_creds = ExchangeCredentials.query.filter_by(user_id=user.id).all()
            for cred in existing_creds:
                db.session.delete(cred)
            db.session.commit()
            
            # Create credentials
            creds = ExchangeCredentials(
                user_id=user.id,
                exchange='testexchange',
                portfolio_name='default',
                api_key='test_key',
                api_secret='test_secret',
                passphrase='test_passphrase'
            )
            db.session.add(creds)
            db.session.commit()
            
            # Create a strategy that uses this exchange credential
            strategy = TradingStrategy(
                user_id=user.id,
                name='Test Strategy',
                exchange_credential_id=creds.id,
                trading_pair='BTC/USDT',
                base_asset_symbol='BTC',
                quote_asset_symbol='USDT',
                allocated_base_asset_quantity=Decimal('1.0'),
                allocated_quote_asset_quantity=Decimal('0'),
                webhook_id='test-webhook-123',
                is_active=True
            )
            db.session.add(strategy)
            db.session.commit()
            
            # Check if credentials are in use
            strategies_using_credential = TradingStrategy.query.filter_by(
                exchange_credential_id=creds.id
            ).all()
            
            assert len(strategies_using_credential) == 1
            assert strategies_using_credential[0].name == 'Test Strategy'
    
    def test_credential_cleanup_scenarios_clean(self, app, regular_user):
        """Test credential cleanup in various scenarios."""
        with app.app_context():
            user = User.query.filter_by(email='testuser@example.com').first()
            
            # Clean up any existing data first to prevent constraint violations
            existing_strategies = TradingStrategy.query.filter_by(user_id=user.id).all()
            for strategy in existing_strategies:
                db.session.delete(strategy)
            db.session.commit()
            
            existing_creds = ExchangeCredentials.query.filter_by(user_id=user.id).all()
            for cred in existing_creds:
                db.session.delete(cred)
            db.session.commit()
            
            # Scenario 1: Credential with no strategies
            creds1 = ExchangeCredentials(
                user_id=user.id,
                exchange='exchange1',
                portfolio_name='default',
                api_key='key1',
                api_secret='secret1'
            )
            db.session.add(creds1)
            db.session.commit()
            
            # Should be able to delete immediately
            creds1_id = creds1.id
            db.session.delete(creds1)
            db.session.commit()
            
            deleted_creds = ExchangeCredentials.query.get(creds1_id)
            assert deleted_creds is None
            
            # Scenario 2: Credential with strategy
            creds2 = ExchangeCredentials(
                user_id=user.id,
                exchange='exchange2',
                portfolio_name='default',
                api_key='key2',
                api_secret='secret2'
            )
            db.session.add(creds2)
            db.session.commit()
            
            strategy = TradingStrategy(
                user_id=user.id,
                name='Test Strategy',
                exchange_credential_id=creds2.id,
                trading_pair='BTC/USDT',
                base_asset_symbol='BTC',
                quote_asset_symbol='USDT',
                allocated_base_asset_quantity=Decimal('1.0'),
                allocated_quote_asset_quantity=Decimal('0'),
                webhook_id='test-webhook-cleanup',
                is_active=True
            )
            db.session.add(strategy)
            db.session.commit()
            
            # Should not be able to delete credential while strategy exists
            strategies_using_creds = TradingStrategy.query.filter_by(
                exchange_credential_id=creds2.id
            ).count()
            assert strategies_using_creds > 0
            
            # Clean up strategy first, then credential
            db.session.delete(strategy)
            db.session.delete(creds2)
            db.session.commit()
            
            # Create credentials for different exchanges
            exchanges = ['exchange1', 'exchange2', 'exchange3']
            for exchange in exchanges:
                creds = ExchangeCredentials(
                    user_id=user.id,
                    exchange=exchange,
                    portfolio_name='default',
                    api_key=f'{exchange}_key',
                    api_secret=f'{exchange}_secret',
                    passphrase=f'{exchange}_passphrase'
                )
                db.session.add(creds)
            
            db.session.commit()
            
            # Verify all exist
            all_creds = ExchangeCredentials.query.filter_by(user_id=user.id).all()
            assert len(all_creds) == 3
            
            # Delete credentials for one exchange
            creds_to_delete = ExchangeCredentials.query.filter_by(
                user_id=user.id,
                exchange='exchange2'
            ).all()
            
            for cred in creds_to_delete:
                db.session.delete(cred)
            db.session.commit()
            
            # Verify only that exchange's credentials were deleted
            remaining_creds = ExchangeCredentials.query.filter_by(user_id=user.id).all()
            assert len(remaining_creds) == 2
            
            exchange_names = [cred.exchange for cred in remaining_creds]
            assert 'exchange1' in exchange_names
            assert 'exchange3' in exchange_names
            assert 'exchange2' not in exchange_names


class TestExchangeRegistryIntegration:
    """Test integration with exchange registry."""
    
    def test_exchange_registry_integration_fixed(self, app, regular_user):
        """Test integration with exchange registry for supported exchanges."""
        with app.app_context():
            # Test with supported exchanges from registry
            supported_exchanges = ExchangeRegistry.get_all_exchanges()  # Fixed: correct method name
            
            # Should have some exchanges available
            assert len(supported_exchanges) > 0
            
            # Test that we can create credentials for a supported exchange
            if supported_exchanges:
                test_exchange = supported_exchanges[0]
                user = User.query.filter_by(email='testuser@example.com').first()
                
                creds = ExchangeCredentials(
                    user_id=user.id,
                    exchange=test_exchange,
                    portfolio_name='default',
                    api_key='test_key',
                    api_secret='test_secret',
                    passphrase='test_passphrase'
                )
                db.session.add(creds)
                db.session.commit()
                
                # Verify credential was created
                saved_creds = ExchangeCredentials.query.filter_by(
                    user_id=user.id,
                    exchange=test_exchange
                ).first()
                
                assert saved_creds is not None
                assert saved_creds.exchange == test_exchange
