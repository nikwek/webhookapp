from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import ccxt
from ccxt.base.errors import ExchangeError
from flask import current_app

from app import cache
from app.exchanges.base_adapter import ExchangeAdapter
from app.models.exchange_credentials import ExchangeCredentials
from app.models.portfolio import Portfolio
from app.utils.circuit_breaker import circuit_breaker

logger = logging.getLogger(__name__)


def _make_key_ccxt_client(cls, user_id, portfolio_name="default"):
    return f"ccxt_client:{cls.get_name()}:{user_id}:{portfolio_name}"


def _make_key_ccxt_get_portfolio_value(
    cls, user_id, portfolio_id, target_currency="USD"
):
    return (
        f"ccxt_portfolio_value:{cls.get_name()}:{user_id}:{portfolio_id}:"
        f"{target_currency}"
    )


class CcxtBaseAdapter(ExchangeAdapter):
    _exchange_id: str | None = None

    @classmethod
    def _get_exchange_class(cls):
        if not cls._exchange_id:
            raise ValueError("_exchange_id not set")
        exchange_id = (
            "coinbase" if cls._exchange_id == "coinbase-ccxt" else cls._exchange_id
        )
        try:
            return getattr(ccxt, exchange_id)
        except AttributeError as exc:
            raise ValueError(f"ccxt has no exchange named '{cls._exchange_id}'") from exc

    @classmethod
    def get_name(cls) -> str:
        if not cls._exchange_id:
            raise ValueError("_exchange_id not configured")
        return cls._exchange_id

    @classmethod
    def get_display_name(cls) -> str:
        if not cls._exchange_id:
            raise ValueError("_exchange_id not configured")
        if cls._exchange_id == "coinbase-ccxt":
            return "Coinbase"
        return " ".join(
            p.capitalize()
            for p in cls._exchange_id.replace("_", " ").replace("-", " ").split()
        )

    @classmethod
    @cache.cached(timeout=600, make_cache_key=_make_key_ccxt_client)
    def get_client(cls, user_id: int, portfolio_name: str = "default"):
        creds = ExchangeCredentials.query.filter_by(
            user_id=user_id, exchange=cls.get_name(), portfolio_name=portfolio_name
        ).first()
        if not creds:
            logger.warning("No %s credentials for user %s", cls.get_name(), user_id)
            return None

        secret = creds.decrypt_secret()
        if cls.get_name() in ["coinbase-ccxt", "coinbase"] and secret:
            secret = secret.replace("\\n", "\n")

        params = {
            "apiKey": creds.api_key,
            "secret": secret,
            "options": {"defaultType": "spot"},
        }
        if creds.passphrase:
            params["password"] = creds.passphrase

        client = cls._get_exchange_class()(params)

        if cls.get_name() in current_app.config.get("CCXT_SANDBOX_EXCHANGES", []):
            if hasattr(client, "set_sandbox_mode"):
                client.set_sandbox_mode(True)

        return client

    @classmethod
    def get_portfolios(cls, user_id: int, include_default: bool = False) -> List[str]:
        return ["default"]

    @classmethod
    @circuit_breaker("ccxt_api")
    def get_trading_pairs(cls, user_id: int) -> List[Dict[str, Any]]:
        client = cls.get_client(user_id)
        if not client:
            return []
        try:
            markets = client.load_markets()
            pairs = [
                {
                    "id": s,
                    "product_id": s,
                    "base_currency": m.get("base"),
                    "quote_currency": m.get("quote"),
                    "display_name": s,
                }
                for s, m in markets.items()
                if m.get("active") is not False
            ]
            return sorted(pairs, key=lambda p: p["display_name"])
        except Exception as exc:
            logger.error("%s load_markets failed: %s", cls.get_name(), exc)
            return []

    @classmethod
    @circuit_breaker("ccxt_api")
    def get_ticker(cls, user_id: int, trading_pair: str) -> Dict[str, Any]:
        """
        Fetches the ticker information for a given trading pair.

        Args:
            user_id: The ID of the user.
            trading_pair: The trading pair to fetch the ticker for (e.g., 'BTC/USD').

        Returns:
            A dictionary containing the ticker information or an empty dictionary on error.
        """
        client = cls.get_client(user_id)
        if not client:
            logger.warning(
                "get_ticker failed: CCXT client not available for user %s", user_id
            )
            return {}

        try:
            return client.fetch_ticker(trading_pair)
        except ExchangeError as exc:
            logger.error(
                "%s fetch_ticker for %s failed: %s",
                cls.get_name(),
                trading_pair,
                exc,
            )
            return {}
        except Exception as exc:
            logger.error(
                "%s fetch_ticker for %s failed with unexpected error: %s",
                cls.get_name(),
                trading_pair,
                exc,
            )
            return {}

    @classmethod
    @cache.cached(timeout=60, make_cache_key=_make_key_ccxt_get_portfolio_value)
    @circuit_breaker("ccxt_api_portfolio_value")
    def get_portfolio_value(
        cls, user_id: int, portfolio_id: int, target_currency: str = "USD"
    ) -> Dict[str, Any]:
        client = cls.get_client(user_id)
        if not client:
            return {"success": False, "error": "Client not available", "total_value": 0.0}

        try:
            client.load_markets()
            balances = client.fetch_balance()
            total_value = 0.0
            detailed_balances = []
            pricing_errors = []

            for asset, amount in balances.get("total", {}).items():
                if not isinstance(amount, (int, float)) or amount <= 1e-8:
                    continue

                asset_upper = asset.upper()
                target_upper = target_currency.upper()
                value = 0.0

                if asset_upper == target_upper or (
                    asset_upper == "USDC" and target_upper == "USD"
                ):
                    value = amount
                else:
                    try:
                        symbol = f"{asset_upper}/{target_upper}"
                        ticker = client.fetch_ticker(symbol)
                        price = ticker.get("last") or ticker.get("close")
                        if price:
                            value = amount * price
                        else:
                            pricing_errors.append(
                                {
                                    "asset": asset_upper,
                                    "error": f"No price in ticker for {symbol}",
                                }
                            )
                    except Exception as e:
                        pricing_errors.append({"asset": asset_upper, "error": str(e)})

                if value > 0:
                    total_value += value
                    detailed_balances.append(
                        {"asset": asset_upper, "total": amount, "usd_value": value}
                    )

            return {
                "success": True,
                "currency": target_currency,
                "total_value": total_value,
                "balances": detailed_balances,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "pricing_errors": pricing_errors,
            }
        except Exception as e:
            logger.error(f"Error in get_portfolio_value for {cls.get_name()}: {e}")
            return {"success": False, "error": str(e), "total_value": 0.0}



    # ------------------- execute trade --------------------------------
    @classmethod
    def execute_trade(
        cls,
        credentials: ExchangeCredentials,
        portfolio: Optional[Portfolio],
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

        # ----------------- exchange minimum order validation -----------------
        try:
            client.load_markets()
            market = client.markets.get(trading_pair)
        except Exception as e:
            logger.warning("Could not load markets for limit validation: %s", e)
            market = None

        if market:
            limits = market.get("limits", {}) or {}
            amount_limits = limits.get("amount", {}) or {}
            cost_limits = limits.get("cost", {}) or {}
            amount_min = amount_limits.get("min")
            cost_min = cost_limits.get("min")

            # Determine price to use when validating cost minimum
            price_for_cost = price
            if price_for_cost is None:
                try:
                    ticker = client.fetch_ticker(trading_pair)
                    price_for_cost = (
                        ticker.get("last")
                        or ticker.get("close")
                        or ticker.get("ask")
                        or ticker.get("bid")
                    )
                except Exception as e:
                    logger.warning("Failed to fetch ticker for cost validation: %s", e)

            # Check amount minimum
            if amount_min is not None and amount < amount_min:
                msg = (
                    f"Order amount {amount} below exchange minimum {amount_min}. "
                    "Trade aborted."
                )
                logger.info(msg)
                return {
                    "trade_executed": False,
                    "message": msg,
                    "trade_status": "rejected",
                    "client_order_id": client_order_id,
                }

            # Check cost minimum
            if cost_min is not None and price_for_cost is not None:
                order_cost = amount * price_for_cost
                if order_cost < cost_min:
                    msg = (
                        f"Order cost ${order_cost:.2f} below exchange minimum "
                        f"${cost_min:.2f}. Trade aborted."
                    )
                    logger.info(msg)
                    return {
                        "trade_executed": False,
                        "message": msg,
                        "trade_status": "rejected",
                        "client_order_id": client_order_id,
                    }

        try:
            # Generic order options
            options = {}
            
            # The exchange-specific adapters should override this method to handle
            # special cases for their particular exchange before calling super()
            
            # Step 1: Create the order
            initial_order = client.create_order(
                trading_pair, order_type, side, amount, price, params=options
            )
            order_id = initial_order.get("id")
            logger.info(f"Submitted order {order_id} to {cls.get_name()}. Initial response: {initial_order}")

            if not order_id:
                logger.error(f"Exchange {cls.get_name()} did not return an order ID on creation.")
                return {
                    "trade_executed": True,
                    "message": "success, but order status could not be confirmed without order ID",
                    "trade_status": initial_order.get("status", "unknown"),
                    "client_order_id": client_order_id,
                    "exchange_order_id": None,
                    "raw_order": initial_order,
                }

            # Step 2: Poll for the final order status to get filled/cost details
            final_order = initial_order
            # Poll for up to 30 seconds (15 attempts * 2s sleep)
            for i in range(15):
                try:
                    # Some exchanges require the symbol for fetch_order
                    fetched_order = client.fetch_order(order_id, trading_pair)
                    final_order = fetched_order
                    
                    # 'closed' is the unified ccxt status for a filled order.
                    if fetched_order.get("status") == "closed":
                        logger.info(f"Order {order_id} confirmed as 'closed' (filled). Final details: {fetched_order}")
                        break  # Success, we have the final order details

                    logger.info(f"Order {order_id} status is '{fetched_order.get('status')}' (attempt {i+1}/15). Waiting...")
                    time.sleep(2)

                except ccxt.OrderNotFound:
                    logger.warning(f"Order {order_id} not found on attempt {i+1}/15, retrying...")
                    time.sleep(2)
                except Exception as e:
                    logger.error(f"Error polling for order {order_id}: {e}. Aborting poll.")
                    break # Stop polling on other errors

            # Step 3: Return the most up-to-date order information
            if final_order.get("status") != "closed":
                logger.warning(
                    f"Order {order_id} did not reach 'closed' status after polling. "
                    f"Final status: '{final_order.get('status')}'. "
                    f"Proceeding with potentially incomplete data: {final_order}"
                )

            return {
                "trade_executed": True,
                "message": "success",
                "trade_status": final_order.get("status"),
                "client_order_id": client_order_id,
                "exchange_order_id": final_order.get("id"),
                "raw_order": final_order, # This now contains the filled/cost details
            }

        except Exception as exc:
            logger.error(f"Trade execution for {trading_pair} failed: {exc}", exc_info=True)
            return {
                "trade_executed": False,
                "message": str(exc),
                "trade_status": "error",
                "client_order_id": client_order_id,
            }

    # ------------------- validate api keys ----------------------------
    @classmethod
    def validate_api_keys(cls, api_key: str, api_secret: str, password: str = None, uid: str = None, **kwargs) -> Tuple[bool, str]:
        # password, uid, and **kwargs are added to match the base adapter's signature
        # and to allow passing these credentials if an exchange requires them.
        try:
            # Some exchanges (e.g. Coinbase Advanced Trade) expect the API secret
            # to be a PEM-encoded private key.  If the user pasted it into a single-line
            # input field the newlines get escaped as literal "\n" sequences, which
            # breaks the key parser inside CCXT and surfaces as a vague "index out of
            # range" error.  Convert those escaped newlines back to real newline
            # characters before instantiating the exchange client.
            if api_secret and "\\n" in api_secret and "\n" not in api_secret:
                api_secret = api_secret.replace("\\n", "\n").strip()

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
