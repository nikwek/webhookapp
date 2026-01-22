from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from decimal import Decimal, ROUND_DOWN

import ccxt
from ccxt.base.errors import ExchangeError
from flask import current_app

from app import cache
from app.exchanges.base_adapter import ExchangeAdapter
from app.models.exchange_credentials import ExchangeCredentials
from app.models.portfolio import Portfolio
from app.utils.circuit_breaker import circuit_breaker
from app.exchanges.precision import get_market_precisions

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

        # Coinbase Advanced via CCXT may require a price for market buy orders unless
        # this option is disabled. Our Coinbase adapter uses cost-based market buys,
        # so disable the requirement at the client level for robustness.
        try:
            if cls.get_name() in ["coinbase", "coinbase-ccxt"]:
                if hasattr(client, "options") and isinstance(client.options, dict):
                    client.options["createMarketBuyOrderRequiresPrice"] = False
        except Exception:
            # Defensive: ignore if options structure changes
            pass

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
                    # Convert amount to Decimal with proper quantization to match database precision (18 decimal places)
                    from decimal import Decimal
                    amount_decimal = Decimal(str(amount)).quantize(Decimal('0.000000000000000001'))
                    detailed_balances.append(
                        {"asset": asset_upper, "total": amount_decimal, "usd_value": value}
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
        raw_amount = payload.get("size") or payload.get("amount") or payload.get("quantity")
        if raw_amount is None:
            return {
                "trade_executed": False,
                "message": "No trade size specified in payload",
                "trade_status": "error",
                "client_order_id": client_order_id,
            }
        # Normalize amount to Decimal for safe math and rounding
        try:
            amount_dec = Decimal(str(raw_amount))
        except Exception:
            return {
                "trade_executed": False,
                "message": "Invalid amount format",
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

            # Resolve amount quantum and quantize amount
            try:
                prec = get_market_precisions(client, trading_pair)
                amount_quant = prec.get('amount_quant') or Decimal('0.00000001')
            except Exception:
                amount_quant = Decimal('0.00000001')

            try:
                amount_dec = amount_dec.quantize(amount_quant, rounding=ROUND_DOWN)
            except Exception:
                amount_dec = max(amount_dec, Decimal('0'))

            # Check amount minimum with Decimal
            if amount_min is not None:
                try:
                    amount_min_dec = Decimal(str(amount_min))
                except Exception:
                    amount_min_dec = None
                if amount_min_dec is not None and amount_dec < amount_min_dec:
                    msg = (
                        f"Order amount {amount_dec} below exchange minimum {amount_min}. "
                        "Trade aborted."
                    )
                    logger.info(msg)
                    return {
                        "trade_executed": False,
                        "message": msg,
                        "trade_status": "rejected",
                        "client_order_id": client_order_id,
                    }

            # Check cost minimum with Decimal
            if cost_min is not None and price_for_cost is not None:
                try:
                    price_dec = Decimal(str(price_for_cost))
                    cost_min_dec = Decimal(str(cost_min))
                    order_cost = amount_dec * price_dec
                except Exception as e:
                    logger.warning("Failed to compute Decimal order cost for validation: %s", e)
                    order_cost = None
                if order_cost is not None and order_cost < cost_min_dec:
                    msg = (
                        f"Order cost ${order_cost} below exchange minimum ${cost_min}. Trade aborted."
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
            if side == "buy" and order_type == "market":
                # Prefer quote-size (cost-based) market buys when supported
                initial_order = None
                try:
                    cost_amount = None
                    # Compute cost from base amount and current price if available
                    if market and (price_for_cost is not None):
                        try:
                            base_amt_dec = amount_dec
                            price_dec = Decimal(str(price_for_cost))
                            cost_dec = base_amt_dec * price_dec
                            # Determine quote precision (2 dp for fiat/stables, else 8 dp default)
                            quote = market.get("quote") if isinstance(market, dict) else None
                            fiat_stables = {"USD", "USDC", "USDT", "USDP", "DAI"}
                            if isinstance(quote, str) and quote.upper() in fiat_stables:
                                q_decimals = 2
                            else:
                                q_decimals = 8
                            q_quant = Decimal("1").scaleb(-q_decimals)
                            cost_dec = cost_dec.quantize(q_quant, rounding=ROUND_DOWN)
                            cost_amount = float(cost_dec)
                        except Exception:
                            cost_amount = None

                    # Coinbase Advanced: has a dedicated cost-based market buy helper
                    if cost_amount is not None and hasattr(client, "create_market_buy_order_with_cost"):
                        initial_order = client.create_market_buy_order_with_cost(trading_pair, cost_amount)
                    # Binance: supports quoteOrderQty parameter
                    elif cost_amount is not None and getattr(client, "id", "").lower() in {"binance", "binanceus"}:
                        initial_order = client.create_order(trading_pair, "market", "buy", None, None, params={"quoteOrderQty": cost_amount})
                except Exception as e:
                    logger.info(f"Cost-based market buy path not used due to: {e}")

                if initial_order is None:
                    # Fallback to base-size market buy
                    initial_order = client.create_order(
                        trading_pair, order_type, side, float(amount_dec), price, params=options
                    )
            else:
                # For SELL orders, especially on Coinbase, we may hit PREVIEW_INSUFFICIENT_FUND
                # even after prior capping/cushions. Retry by reducing the amount by one
                # precision step per attempt.
                if side == "sell":
                    initial_order = None
                    last_error = None
                    # Determine a reasonable step from market precision or client formatting
                    step = None
                    try:
                        # Default to amount_quant if available
                        try:
                            prec = get_market_precisions(client, trading_pair)
                            step = prec.get('amount_quant') or Decimal('0.00000001')
                        except Exception:
                            step = Decimal('0.00000001')

                        # If client exposes amount_to_precision, refine step to match exchange formatting
                        if hasattr(client, 'amount_to_precision'):
                            formatted = client.amount_to_precision(trading_pair, float(amount_dec))
                            if isinstance(formatted, str) and '.' in formatted:
                                decs = len(formatted.split('.')[-1])
                                step2 = Decimal('1').scaleb(-decs) if decs > 0 else Decimal('1')
                                if step2 > 0:
                                    # Use the larger step to ensure we actually reduce below exchange rounding
                                    step = max(step, step2)
                    except Exception:
                        pass

                    # Ensure step is sane
                    if not isinstance(step, Decimal) or step <= 0:
                        step = Decimal('0.00000001')

                    attempt_amount = amount_dec
                    for attempt in range(3):
                        try:
                            initial_order = client.create_order(
                                trading_pair, order_type, side, float(attempt_amount), price, params=options
                            )
                            break
                        except ExchangeError as e:
                            last_error = e
                            emsg = str(e)
                            # On Coinbase, the preview may fail with various insufficient messages; treat any
                            # ExchangeError as a signal to step down and retry. On other exchanges, only retry
                            # for explicit insufficient fund messages.
                            is_coinbase = getattr(client, 'id', '').lower().startswith('coinbase')
                            insufficient = ('INSUFFICIENT_FUND' in emsg) or ('PREVIEW_INSUFFICIENT_FUND' in emsg)
                            if is_coinbase or insufficient:
                                # Reduce by one more step and retry
                                new_amount = (attempt_amount - step)
                                try:
                                    new_amount = new_amount.quantize(step, rounding=ROUND_DOWN) if new_amount > 0 else Decimal('0')
                                except Exception:
                                    # Fallback: no quantize if step not a valid quant
                                    pass
                                logger.info(
                                    "Retrying SELL after insufficient fund (attempt %s): %s -> %s (step=%s)",
                                    attempt + 1, attempt_amount, new_amount, step,
                                )
                                if new_amount <= 0 or new_amount == attempt_amount:
                                    break
                                attempt_amount = new_amount
                                continue
                            # Other errors: rethrow
                            raise

                    if initial_order is None:
                        if last_error is not None:
                            raise last_error
                        else:
                            raise ExchangeError("Failed to create SELL order after retries")
                else:
                    initial_order = client.create_order(
                        trading_pair, order_type, side, float(amount_dec), price, params=options
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
