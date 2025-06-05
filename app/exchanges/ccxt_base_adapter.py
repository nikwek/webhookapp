"""CCXT-based generic exchange adapter.

This adapter implements the core ExchangeAdapter interface using the
ccxt library. A concrete subclass must define the class attribute
``_exchange_id`` with the ccxt exchange id (e.g. ``'binance'``).

During application start-up, we generate subclasses for each desired
ccxt exchange and register them with ``ExchangeRegistry`` so the rest of
our code can access them by name exactly matching the exchange id.
"""

from __future__ import annotations

import logging
import json  # Added for cache key generation

from app import cache  # Added for caching
import base64
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import ccxt  # type: ignore
from flask import current_app

from app.models.exchange_credentials import ExchangeCredentials
from app.models.portfolio import Portfolio
from app.exchanges.base_adapter import ExchangeAdapter
from app.utils.circuit_breaker import circuit_breaker

logger = logging.getLogger(__name__)

# Cache key generation functions


def _make_key_ccxt_client(cls, user_id, portfolio_name="default"):
    """Generate cache key for CCXT client instances."""
    return f"ccxt_client:{cls.get_name()}:{user_id}:{portfolio_name}"


def _make_key_ccxt_get_portfolio_value(cls, user_id, portfolio_id, target_currency="USD"):
    """Generate cache key for get_portfolio_value method."""
    return f"ccxt_portfolio_value:{cls.get_name()}:{user_id}:{portfolio_id}:{target_currency}"


class CcxtBaseAdapter(ExchangeAdapter):
    """Base class for all dynamically created CCXT adapters."""

    # Concrete subclasses *must* override this.
    _exchange_id: str | None = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @classmethod
    def _get_exchange_class(cls):
        if not cls._exchange_id:
            raise ValueError("_exchange_id not set in adapter subclass")
        exchange_id_for_ccxt = cls._exchange_id
        if cls._exchange_id == 'coinbase-ccxt':
            exchange_id_for_ccxt = 'coinbase'
        try:
            return getattr(ccxt, exchange_id_for_ccxt)
        except AttributeError as exc:
            raise ValueError(
                f"ccxt has no exchange named '{cls._exchange_id}'"
            ) from exc

    # ------------------------------------------------------------------
    # Mandatory ExchangeAdapter interface implementation
    # ------------------------------------------------------------------
    @classmethod
    def get_name(cls) -> str:  # noqa: D401
        """Return the exchange id this adapter represents."""
        if not cls._exchange_id:
            raise ValueError("_exchange_id not configured")
        return cls._exchange_id

    @classmethod
    def get_display_name(cls) -> str:
        """Return a user-friendly display name for the exchange."""
        logger.debug(f"CcxtBaseAdapter.get_display_name called for cls: {cls}, _exchange_id: {cls._exchange_id}")
        if not cls._exchange_id:
            raise ValueError("_exchange_id not configured")
        # Special handling for 'coinbase-ccxt' to make it more readable
        if cls._exchange_id == 'coinbase-ccxt':
            logger.debug(f"CcxtBaseAdapter.get_display_name for {cls._exchange_id} returning special case: Coinbase CCXT")
            return "Coinbase CCXT"
        # General case: capitalize and replace underscores/hyphens with spaces
        name_parts = cls._exchange_id.replace('_', ' ').replace('-', ' ').split()
        result_display_name = ' '.join(part.capitalize() for part in name_parts)
        logger.debug(f"CcxtBaseAdapter.get_display_name for {cls._exchange_id} returning: {result_display_name}")
        return result_display_name

    # --------------------------- client -------------------------------
    @classmethod
    @cache.cached(timeout=600, make_cache_key=_make_key_ccxt_client)
    def get_client(cls, user_id: int, portfolio_name: str = "default"):
        creds = (
            ExchangeCredentials.query.filter_by(
                user_id=user_id,
                exchange=cls.get_name(),
                portfolio_name=portfolio_name,
            ).first()
        )
        if not creds:
            logger.warning(
                "No %s credentials for user %s", cls.get_name(), user_id
            )
            return None

        decrypted_secret = creds.decrypt_secret()
        effective_api_secret = decrypted_secret # Default to the decrypted secret

        if cls.get_name() == "coinbase-ccxt" and decrypted_secret:
            logger.debug(f"Coinbase-CCXT: Decrypted secret (before '\\n' processing, len {len(decrypted_secret)}): {decrypted_secret[:70]}...")
            effective_api_secret = decrypted_secret.replace('\\n', '\n')
            logger.debug(f"Coinbase-CCXT: Processed secret with actual newlines (len {len(effective_api_secret)}): {effective_api_secret[:70]}...")
        
        params: Dict[str, Any] = {
            "apiKey": creds.api_key,
            "secret": effective_api_secret, # Use the potentially newline-corrected secret
            "options": {"defaultType": "spot"},
        }
        # --- TEMPORARY DEBUG LOG ---
#        log_msg_secret = (
#            f"{cls.get_name()}: API Secret for CCXT client init. "
#            f"Type: {type(decrypted_secret)}, "
#            f"Length: {len(decrypted_secret) if decrypted_secret else 0}. "
#            f"Starts with: '{decrypted_secret[:30] if decrypted_secret else ''}...', "
#            f"Ends with: '...{decrypted_secret[-30:] if decrypted_secret else ''}'"
#        )
#        logger.debug(log_msg_secret)
        # --- END TEMPORARY DEBUG LOG ---

        # --- ADDITIONAL PEM DEBUG for coinbase-ccxt ---
        # Use 'effective_api_secret' here as it's the one passed to CCXT
        if cls.get_name() == "coinbase-ccxt" and effective_api_secret:
            logger.debug(
                f"Full PEM Secret (for debugging, after '\\n' replacement) for {cls.get_name()} (len {len(effective_api_secret)}):\n"
                f"{effective_api_secret}"
            )

            # Mimic der.unpem steps to see what content is base64 decoded
            temp_pem_lines = effective_api_secret.strip().split('\n')
            pem_processing_logs = []
            expected_header = "-----BEGIN EC PRIVATE KEY-----"
            expected_footer = "-----END EC PRIVATE KEY-----"
            if len(temp_pem_lines) >= 3:
                actual_header = temp_pem_lines[0]
                actual_footer = temp_pem_lines[-1]
                
                log_entry_header = (
                    f"  Actual Header: '{actual_header}' "
                    f"(Matches expected: {actual_header == expected_header})"
                )
                pem_processing_logs.append(log_entry_header)
                
                log_entry_footer = (
                    f"  Actual Footer: '{actual_footer}' "
                    f"(Matches expected: {actual_footer == expected_footer})"
                )
                pem_processing_logs.append(log_entry_footer)

                content_lines = [line.strip() for line in temp_pem_lines[1:-1]]
                base64_content_to_decode = "".join(content_lines)
                pem_processing_logs.append(
                    f"  Extracted base64 content (len {len(base64_content_to_decode)}):\n"
                    f"    Starts: '{base64_content_to_decode[:45]}...\n"
                    f"    Ends: ...{base64_content_to_decode[-50:]}'"
                )
                try:
                    # Attempt base64 decode (Python's b64decode handles missing newlines) for b64decode if it's a str
                    content_bytes = base64_content_to_decode.encode('ascii')
                    decoded_bytes = base64.b64decode(content_bytes)
                    pem_processing_logs.append(
                        f"  Successfully b64 decoded PEM content. "
                        f"Decoded length: {len(decoded_bytes)}"
                    )
                except Exception as e_b64:
                    pem_processing_logs.append(
                        f"  ERROR b64 decoding PEM content: "
                        f"{type(e_b64).__name__} - {e_b64}"
                    )
                    pem_processing_logs.append(
                        f"  Content that failed (first 100 chars): "
                        f"'{base64_content_to_decode[:100]}'")
            else:
                pem_processing_logs.append(
                    f"  PEM string for {cls.get_name()} has too few lines: "
                    f"{len(temp_pem_lines)} to extract content."
                )

            log_message = "Coinbase CCXT PEM Processing Details:\n" + "\n".join(pem_processing_logs)
            logger.debug(log_message)
        # --- END ADDITIONAL PEM DEBUG ---
        if creds.passphrase:
            # Some exchanges call this "password", ccxt handles both.
            params["password"] = creds.passphrase

        exchange_class = cls._get_exchange_class()
        client = exchange_class(params)

        # Optional sandbox mode via config.
        sandbox_cfg = (
            current_app.config.get("CCXT_SANDBOX_EXCHANGES", [])
            if current_app
            else []
        )
        if (
            cls.get_name() in sandbox_cfg
            and hasattr(client, "set_sandbox_mode")
        ):
            client.set_sandbox_mode(True)
        # Explicitly load markets
        try:
            logger.debug(f"Loading {cls.get_name()} markets...")
            client.load_markets()
            logger.debug(f"{cls.get_name()} markets loaded.")
        except (ccxt.NetworkError, ccxt.ExchangeError) as e_markets:
            # Log the error, but return the client. Some operations might still work, or it might fail later.
            exchange_name = cls.get_name()
            logger.error(
                f"Failed to load markets for {exchange_name} "
                f"during client init: {e_markets}"
            )
        # Catch any other unexpected error
        except Exception as e_markets_unexpected:
            exchange_name = cls.get_name()
            logger.error(
                (
                    f"Unexpected error loading markets for {exchange_name} "
                    f"during client init: {e_markets_unexpected}"
                ),
                exc_info=True,
            )
        
        return client

    # ------------------------ portfolios ------------------------------
    @classmethod
    def get_portfolios(cls, user_id: int, include_default: bool = False) -> List[str]:
        """CCXT exchanges are account-wide; we return
        a single implicit portfolio."""
        return ["default"]

    # ---------------------- trading pairs -----------------------------
    @classmethod
    @circuit_breaker("ccxt_api")
    def get_trading_pairs(cls, user_id: int) -> List[Dict[str, Any]]:
        client = cls.get_client(user_id)
        if not client:
            return []
        try:
            markets = client.load_markets()
        except Exception as exc:  # noqa: BLE001
            logger.error("%s load_markets failed: %s", cls.get_name(), exc)
            return []

        pairs: List[Dict[str, Any]] = []
        for symbol, m in markets.items():
            if m.get("active") is False:
                continue
            pairs.append(
                {
                    "id": symbol,
                    "product_id": symbol,
                    "base_currency": m.get("base"),
                    "quote_currency": m.get("quote"),
                    "display_name": symbol,
                }
            )
        pairs.sort(key=lambda x: x["display_name"])
        return pairs

    # ------------------- portfolio value ------------------------------
    @classmethod
    @cache.cached(timeout=600, make_cache_key=_make_key_ccxt_get_portfolio_value)
    @circuit_breaker("ccxt_api_portfolio_value")
    def get_portfolio_value(
        cls, user_id: int, portfolio_id: int, target_currency: str = "USD"
    ) -> Dict[str, Any]:
        client = cls.get_client(user_id)
        if not client:
            return {
                "currency": target_currency,
                "total_value": 0.0,
                "balances": [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "pricing_errors": [
                    {"asset": "N/A", "error": "Client not available"}
                ],
            }

        total_value_in_target_currency = 0.0
        pricing_errors: List[Dict[str, str]] = []
        detailed_asset_balances: List[Dict[str, Any]] = []

        try:
            # Load markets to ensure ticker data is available/fresh for some exchanges
            if client.has.get('loadMarkets'):
                client.load_markets()

            balances_data = None
            try:
                logger.debug(f"{cls.get_name()}: Attempting to fetch balance.")
                balances_data = client.fetch_balance()
                exchange_name = cls.get_name()
                logger.debug(
                    f"{exchange_name}: Balances fetched. Type: {type(balances_data)}. "
                    f"Content (first 200 chars): {str(balances_data)[:200]}"
                )
            except IndexError as ie_fb:
                logger.error(
                    f"{cls.get_name()}: IndexError during fetch_balance: {ie_fb}",
                    exc_info=True
                )
                raise # Re-raise to be caught by the main error handler
            except Exception as e_fb:
                logger.error(
                    f"{cls.get_name()}: Error during fetch_balance: {e_fb}",
                    exc_info=True
                )
                return {
                    "currency": target_currency,
                    "total_value": 0.0,
                    "balances": [],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "pricing_errors": [{
                        "asset": "N/A",
                        "error": f"Failed to fetch balance: {e_fb}"
                    }]
                }

            asset_balances_iter = {}
            if isinstance(balances_data, dict):
                asset_balances_iter = balances_data.get("total", {})
                if not asset_balances_iter: # Fallback to 'free' if 'total' is empty or not present
                    asset_balances_iter = balances_data.get("free", {})
            else:
                exchange_name = cls.get_name()
                logger.warning(
                    f"{exchange_name}: Balances object not a dict. "
                    f"Type: {type(balances_data)}. Content: {str(balances_data)[:200]}"
                )
            
            # exchange_name = cls.get_name() # This is redundant, already defined
            logger.debug(
                f"{cls.get_name()}: Asset balances to iterate. " # Use cls.get_name() for consistency
                f"Type: {type(asset_balances_iter)}. Content: {str(asset_balances_iter)[:200]}"
            )

            for asset_code, amount_value in asset_balances_iter.items():
                amount = 0.0
                if isinstance(amount_value, (int, float)):
                    amount = float(amount_value)
                elif isinstance(amount_value, str):
                    try:
                        amount = float(amount_value)
                    except ValueError:
                        logger.warning(
                            f"{cls.get_name()}: Could not parse amount for {asset_code}: {amount_value}"
                        )
                        pricing_errors.append({
                            "asset": asset_code,
                            "error": f"Invalid amount format: {amount_value}"
                        })
                        continue
                else:
                    logger.warning(
                        f"{cls.get_name()}: Unexpected amount type for {asset_code}: {type(amount_value)}"
                    )
                    pricing_errors.append({
                        "asset": asset_code,
                        "error": f"Unexpected amount type: {type(amount_value)}"
                    })
                    continue

                if amount <= 1e-8:  # Skip dust or zero balances
                    continue

                asset_upper = asset_code.upper()
                target_currency_upper = target_currency.upper()

                if asset_upper == target_currency_upper:
                    total_value_in_target_currency += amount
                    detailed_asset_balances.append({
                        "asset": asset_upper,
                        "total": amount,
                        "usd_value": amount # Value is itself in target currency
                    })
                else:
                    if asset_upper == 'USDC' and target_currency_upper == 'USD':
                        total_value_in_target_currency += amount
                        detailed_asset_balances.append({
                            "asset": asset_upper,
                            "total": amount,
                            "usd_value": amount # USDC is 1:1 with USD
                        })
                        logger.debug(
                            f"{cls.get_name()}: Converted {amount} {asset_upper} to {target_currency_upper} at 1:1 rate."
                        )
                    elif not client.has.get('fetchTicker'):
                        error_msg = f"Exchange {cls.get_name()} does not support fetchTicker. Cannot price {asset_upper}."
                        logger.warning(f"{cls.get_name()}: {error_msg}")
                        pricing_errors.append({"asset": asset_upper, "error": error_msg})
                        continue
                    else:
                        symbol = f"{asset_upper}/{target_currency_upper}"
                        try:
                            logger.debug(f"{cls.get_name()}: Attempting to fetch ticker for {symbol}.")
                            ticker = client.fetch_ticker(symbol)
                            logger.debug(f"{cls.get_name()}: Ticker for {symbol} fetched. Type: {type(ticker)}. Content (first 500 chars): {str(ticker)[:500]}")

                            if not isinstance(ticker, dict):
                                logger.warning(f"{cls.get_name()}: Ticker for {symbol} is not a dict. Type: {type(ticker)}. Content: {str(ticker)[:500]}")
                                pricing_errors.append({"asset": asset_upper, "error": f"Invalid ticker format for {symbol}"})
                                continue

                            price = ticker.get('last') or ticker.get('close') or ticker.get('bid')

                            if price is not None:
                                try:
                                    asset_value_in_target = amount * float(price)
                                    total_value_in_target_currency += asset_value_in_target
                                    detailed_asset_balances.append({
                                        "asset": asset_upper,
                                        "total": amount,
                                        "usd_value": round(asset_value_in_target, 2)
                                    })
                                except ValueError:
                                    error_msg = f"Invalid price format for {symbol}: {price}"
                                    logger.warning(f"{cls.get_name()}: {error_msg}")
                                    pricing_errors.append({"asset": asset_upper, "error": error_msg})
                            else:
                                error_msg = f"Could not get price for {symbol} from {cls.get_name()}. Ticker: {str(ticker)[:200]}"
                                logger.warning(f"{cls.get_name()}: {error_msg}")
                                pricing_errors.append({"asset": asset_upper, "error": error_msg})

                        except IndexError as ie_ft:
                            logger.error(f"{cls.get_name()}: IndexError during fetch_ticker for {symbol}: {ie_ft}", exc_info=True)
                            pricing_errors.append({"asset": asset_upper, "error": f"IndexError fetching price for {symbol}: {ie_ft}"})
                        except ccxt.NetworkError as e_ne:
                            logger.error(f"{cls.get_name()}: Network error fetching ticker for {symbol}: {e_ne}")
                            pricing_errors.append({"asset": asset_upper, "error": f"Network error: {e_ne}"})
                        except ccxt.ExchangeError as e_ee:
                            logger.warning(f"{cls.get_name()}: Exchange error fetching ticker for {symbol}: {e_ee} (Type: {type(e_ee).__name__})")
                            pricing_errors.append({"asset": asset_upper, "error": f"Exchange error ({type(e_ee).__name__}): {e_ee}"})
                        except Exception as e_generic_ft:
                            logger.exception(f"{cls.get_name()}: Generic error processing ticker/price for {symbol}: {e_generic_ft}")
                            pricing_errors.append({"asset": asset_upper, "error": f"Failed to process price for {symbol}: {e_generic_ft}"})
            
            return {
                "currency": target_currency,
                "total_value": round(total_value_in_target_currency, 2),
                "balances": detailed_asset_balances,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "pricing_errors": pricing_errors,
            }

        except ccxt.NetworkError as e:
            logger.error(f"{cls.get_name()}: Network error in get_portfolio_value: {e}")
            return {
                "currency": target_currency,
                "total_value": 0.0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "pricing_errors": [{"asset": "N/A", "error": f"Network error: {e}"}],
            }
        except Exception as exc:
            logger.error(f"{cls.get_name()}: General error in get_portfolio_value: {exc}")
            return {
                "currency": target_currency,
                "total_value": 0.0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "pricing_errors": [{"asset": "N/A", "error": str(exc)}],
            }

    # ---------------- refresh account data ----------------------------
    @classmethod
    def refresh_account_data(cls, user_id: int, portfolio_id: int) -> bool:
        """No-op for now – to be implemented with AccountCache in future."""
        logger.info("CCXT adapter refresh_account_data not implemented yet")
        return True

    # ------------------- execute trade --------------------------------
    @classmethod
    def execute_trade(
        cls,
        credentials: ExchangeCredentials,
        portfolio: Portfolio,
        trading_pair: str,
        action: str,
        payload: Dict[str, Any],
        client_order_id: str,
    ) -> Dict[str, Any]:
        client = cls.get_client(credentials.user_id, credentials.portfolio_name)
        if not client:
            return {
                "trade_executed": False,
                "message": "Missing credentials or failed auth",
                "trade_status": "error",
                "client_order_id": client_order_id,
            }

        side = action.lower()
        amount = payload.get("size") or payload.get("amount") or payload.get("quantity")
        if not amount:
            return {
                "trade_executed": False,
                "message": "No trade size specified in payload",
                "trade_status": "error",
                "client_order_id": client_order_id,
            }

        order_type = payload.get("order_type", "market").lower()
        price = payload.get("price") if order_type == "limit" else None

        try:
            order = client.create_order(trading_pair, order_type, side, amount, price)
            return {
                "trade_executed": True,
                "message": "success",
                "trade_status": "filled" if order.get("status") == "closed" else order.get("status"),
                "client_order_id": client_order_id,
                "exchange_order_id": order.get("id"),
                "raw_order": order,
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Trade execution failed: %s", exc)
            return {
                "trade_executed": False,
                "message": str(exc),
                "trade_status": "error",
            }

    # ------------------- validate api keys ----------------------------
    @classmethod
    def validate_api_keys(cls, api_key: str, api_secret: str, password: str = None, uid: str = None, **kwargs) -> Tuple[bool, str]:
        # password, uid, and **kwargs are added to match the base adapter's signature
        # and to allow passing these credentials if an exchange requires them.
        try:
            exchange_class = cls._get_exchange_class()
            
            params = {"apiKey": api_key, "secret": api_secret}
            if password:
                params['password'] = password  # Used by some exchanges (e.g. Kraken for API key 2FA/passphrase)
            if uid:
                params['uid'] = uid  # Used by some exchanges for subaccounts, etc.
            
            # The **kwargs from the signature are not explicitly used here but ensure compatibility.
            # If specific exchanges need other params from kwargs, they should handle them.

            client = exchange_class(params)
            client.fetch_balance()  # A common way to test if keys are working
            return True, "API keys are valid and connection successful."
        except ccxt.AuthenticationError as e:
            logger.warning(f"CCXT AuthenticationError for {cls.get_name()}: {e}")
            msg = (
                f"Authentication failed for {cls.get_display_name()}. "
                f"Please check your API key, secret, and password (if applicable). Error: {e}"
            )
            return False, msg
        except ccxt.NetworkError as e:
            logger.warning(f"CCXT NetworkError for {cls.get_name()}: {e}")
            msg = (
                f"Network error: Could not connect to {cls.get_display_name()}. "
                f"Please try again later. Error: {e}"
            )
            return False, msg
        except ccxt.ExchangeError as e:  # Catch other exchange-specific errors
            logger.warning(f"CCXT ExchangeError for {cls.get_name()}: {e}")
            return False, f"Exchange error with {cls.get_display_name()}: {e}"
        except Exception as exc:  # Catch-all for any other unexpected errors
            logger.warning(f"API key validation failed for {cls.get_name()}: {exc}")
            msg = (
                f"An unexpected error occurred during API key validation for {cls.get_display_name()}. "
                f"Error: {str(exc)}"
            )
            return False, msg
