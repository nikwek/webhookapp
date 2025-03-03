from app.models.account_cache import AccountCache
from app.models.exchange_credentials import ExchangeCredentials
from app import db
from datetime import datetime, timezone, timedelta
import logging
from app.services.coinbase_service import CoinbaseService

logger = logging.getLogger(__name__)

class AccountService:
    CACHE_DURATION = timedelta(minutes=5)  # Cache expires after 5 minutes

    @staticmethod
    def get_accounts(user_id, portfolio_id=None, force_refresh=False):
        """
        Get account data, using cache if available and not expired
        """
        try:
            logger.info(f"Getting accounts for user_id={user_id}, portfolio_id={portfolio_id}, force_refresh={force_refresh}")
            
            # Check cache first
            if not force_refresh:
                cached_accounts = AccountCache.query.filter_by(
                    user_id=user_id
                )
                
                if portfolio_id is not None:
                    cached_accounts = cached_accounts.filter_by(portfolio_id=portfolio_id)
                
                cached_accounts = cached_accounts.all()
                
                # Check if we have cached accounts and if they're not expired
                if cached_accounts:
                    most_recent = max(acct.last_cached_at for acct in cached_accounts)
                    if datetime.now(timezone.utc) - most_recent < AccountService.CACHE_DURATION:
                        logger.info(f"Using {len(cached_accounts)} cached accounts, last updated at {most_recent}")
                        return cached_accounts
            
            # Get credentials based on portfolio
            if portfolio_id:
                creds = ExchangeCredentials.query.filter_by(
                    user_id=user_id,
                    portfolio_id=portfolio_id,
                    exchange='coinbase'
                ).first()
                logger.info(f"Found credentials for specific portfolio: {creds is not None}")
            else:
                creds = ExchangeCredentials.query.filter_by(
                    user_id=user_id,
                    exchange='coinbase',
                    is_default=True
                ).first()
                logger.info(f"Found default credentials: {creds is not None}")
            
            if not creds:
                logger.warning(f"No API credentials found for user_id={user_id}, portfolio_id={portfolio_id}")
                return []
            
            # Create Coinbase client
            client = CoinbaseService.get_client_from_credentials(creds)
            if not client:
                logger.error("Failed to create Coinbase client")
                return []

            # Fetch accounts from Coinbase
            logger.info("Fetching accounts from Coinbase API")
            accounts_response = client.get_accounts()
            logger.info(f"Received response from Coinbase: {type(accounts_response)}")

            # Try to understand the structure of the response
            if isinstance(accounts_response, dict):
                logger.info(f"Response is a dictionary with keys: {list(accounts_response.keys())}")
                # Check if accounts are in a nested property
                if 'accounts' in accounts_response:
                    accounts_response = accounts_response['accounts']
                    logger.info(f"Extracted accounts from 'accounts' key, found {len(accounts_response)} accounts")
                elif 'data' in accounts_response:
                    accounts_response = accounts_response['data']
                    logger.info(f"Extracted accounts from 'data' key, found {len(accounts_response)} accounts")
            elif hasattr(accounts_response, 'accounts'):
                accounts_response = accounts_response.accounts
                logger.info(f"Extracted accounts from 'accounts' attribute, found {len(accounts_response)} accounts")
            elif hasattr(accounts_response, 'data'):
                accounts_response = accounts_response.data
                logger.info(f"Extracted accounts from 'data' attribute, found {len(accounts_response)} accounts")
            
            # Log some information about the accounts
            if hasattr(accounts_response, '__iter__'):
                account_count = len(list(accounts_response))
                logger.info(f"Found {account_count} accounts in the response")
            else:
                logger.info(f"Response is not iterable: {accounts_response}")
            
            # Clear existing cache for this user/portfolio
            delete_query = AccountCache.query.filter_by(user_id=user_id)
            if portfolio_id is not None:
                delete_query = delete_query.filter_by(portfolio_id=portfolio_id)
            deleted_count = delete_query.delete()
            logger.info(f"Deleted {deleted_count} cached accounts")
            
            # Store new data in cache
            accounts = []
            try:
                for acct in accounts_response:
                    # Log account details for debugging
                    logger.debug(f"Processing account: {getattr(acct, 'uuid', None)} - {getattr(acct, 'currency', {}).get('code', 'N/A')}")
                    
                    try:
                        cache_entry = AccountCache.create_from_coinbase_account(
                            account_data=acct,
                            user_id=user_id,
                            portfolio_id=portfolio_id
                        )
                        db.session.add(cache_entry)
                        accounts.append(cache_entry)
                    except Exception as e:
                        logger.error(f"Error creating cache entry for account: {str(e)}")
            except Exception as e:
                logger.error(f"Error iterating through accounts: {str(e)}")
                
            logger.info(f"Created {len(accounts)} new account cache entries")
            db.session.commit()
            return accounts
                
        except Exception as e:
            logger.error(f"Error getting accounts: {str(e)}", exc_info=True)
            db.session.rollback()
            return []

    @staticmethod
    def get_portfolio_value(user_id, portfolio_id=None, currency='USD'):
        """
        Calculate total portfolio value in specified currency
        """
        try:
            if not portfolio_id:
                return 0.0
                
            # Get the value from the portfolio breakdown API
            from app.services.coinbase_service import CoinbaseService
            value = CoinbaseService.get_portfolio_value_from_breakdown(
                user_id=user_id,
                portfolio_id=portfolio_id,
                currency=currency
            )
            
            return value
        except Exception as e:
            logger.error(f"Error calculating portfolio value: {str(e)}")
            return 0.0
