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
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import ccxt  # type: ignore
from flask import current_app

from app.models.exchange_credentials import ExchangeCredentials
from app.models.portfolio import Portfolio
from app.exchanges.base_adapter import ExchangeAdapter
from app.utils.circuit_breaker import circuit_breaker

logger = logging.getLogger(__name__)


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
        try:
            return getattr(ccxt, cls._exchange_id)
        except AttributeError as exc:
            raise ValueError(f"ccxt has no exchange named '{cls._exchange_id}'") from exc

    # ------------------------------------------------------------------
    # Mandatory ExchangeAdapter interface implementation
    # ------------------------------------------------------------------
    @classmethod
    def get_name(cls) -> str:  # noqa: D401
        """Return the exchange id this adapter represents."""
        if not cls._exchange_id:
            raise ValueError("_exchange_id not configured")
        return cls._exchange_id

    # --------------------------- client -------------------------------
    @classmethod
    def get_client(cls, user_id: int, portfolio_name: str = "default"):
        creds = (
            ExchangeCredentials.query.filter_by(
                user_id=user_id,
                exchange=cls.get_name(),
                portfolio_name=portfolio_name,
            ).first()
        )
        if not creds:
            logger.warning("No %s credentials for user %s", cls.get_name(), user_id)
            return None

        params: Dict[str, Any] = {
            "apiKey": creds.api_key,
            "secret": creds.decrypt_secret(),
        }
        if creds.passphrase:
            # Some exchanges call this "password", ccxt handles both.
            params["password"] = creds.passphrase

        exchange_class = cls._get_exchange_class()
        client = exchange_class(params)

        # Optional sandbox mode via config.
        sandbox_cfg = current_app.config.get("CCXT_SANDBOX_EXCHANGES", []) if current_app else []
        if cls.get_name() in sandbox_cfg and hasattr(client, "set_sandbox_mode"):
            client.set_sandbox_mode(True)
        return client

    # ------------------------ portfolios ------------------------------
    @classmethod
    def get_portfolios(cls, user_id: int, include_default: bool = False) -> List[str]:
        """CCXT exchanges are account-wide; we return a single implicit portfolio."""
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
    def get_portfolio_value(
        cls, user_id: int, portfolio_id: int, currency: str = "USD"
    ) -> Dict[str, Any]:
        client = cls.get_client(user_id)
        if not client:
            return {}
        try:
            bal = client.fetch_balance()
            total = bal.get("total", {})
            # Very naive valuation: only include target currency balance
            value = total.get(currency, 0.0)
            return {
                "currency": currency,
                "total_value": value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("%s fetch_balance failed: %s", cls.get_name(), exc)
            return {}

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
                "client_order_id": client_order_id,
            }

    # ------------------- validate api keys ----------------------------
    @classmethod
    def validate_api_keys(cls, api_key: str, api_secret: str) -> Tuple[bool, str]:
        try:
            exchange_class = cls._get_exchange_class()
            client = exchange_class({"apiKey": api_key, "secret": api_secret})
            client.fetch_balance()
            return True, "API keys are valid"
        except Exception as exc:  # noqa: BLE001
            logger.warning("API key validation failed: %s", exc)
            return False, str(exc)
