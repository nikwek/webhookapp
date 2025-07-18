"""Custom adapter for Crypto.com exchange to avoid private endpoints during
market discovery. Crypto.com's CCXT implementation relies on a private
endpoint inside ``load_markets`` which fails unless the user's API key has the
IP whitelisted.  By overriding ``get_trading_pairs`` to hit the public
``/public/get-instruments`` endpoint we make read-only operations work even
before the user has configured keys or completed IP binding.

If API credentials *are* present we still try `load_markets` first because it
returns richer metadata (precision, limits …).  We silently fall back to the
public endpoint on any error.
"""
from __future__ import annotations

from typing import List
import logging
import os

import ccxt

from .ccxt_base_adapter import CcxtBaseAdapter

logger = logging.getLogger(__name__)


class CcxtCryptocomAdapter(CcxtBaseAdapter):
    """Crypto.com CCXT adapter with public-endpoint fallback."""

    _exchange_id = "cryptocom"

    @classmethod
    def get_display_name(cls) -> str:
        return "Crypto.com"

    @classmethod
    def get_logo_filename(cls) -> str:
        return "cryptocom.svg"

    # ---------------------------------------------------------------------
    # Overrides
    # ---------------------------------------------------------------------
    @classmethod
    def get_portfolio_value(
        cls,
        user_id: int,
        portfolio_id: int,
        target_currency: str = "USD",
    ) -> dict:  # noqa: D401
        """Return portfolio value, or a friendly error when IP whitelist blocks.

        We *attempt* the default implementation first. If it succeeds we pass
        the data through unmodified.  If it fails (or returns ``success=False``)
        due to Crypto.com's IP whitelist we swallow the low-level error and
        replace it with a clear, actionable message so the UI can inform the
        user without showing raw JSON from the exchange.
        """
        try:
            data = super().get_portfolio_value(
                user_id=user_id,
                portfolio_id=portfolio_id,
                target_currency=target_currency,
            )
            if data.get("success"):
                # Successful — pass straight through
                return data
            # b. returned but success is False ⇒ examine the embedded error
            caught_err_msg = data.get("error", "")
            caught_err = Exception(caught_err_msg) if caught_err_msg else None
        except Exception as err:  # pylint: disable=broad-except
            caught_err = err

        # We reach this point if an exception occurred OR the base call
        # returned success=False. Craft a friendly replacement response.
        ip_msg = (
            "Crypto.com rejected the request because your API key does not "
            "allow this IP address.  Please open Crypto.com Exchange → User "
            "Centre → API and either add the server's IP "
            f"({os.getenv('PUBLIC_IP', 'current host')}) to the whitelist or "
            "disable IP binding."
        )
        generic_msg = "Unable to retrieve portfolio data from Crypto.com."

        raw_msg = str(caught_err) if caught_err else ""
        if "IP_ILLEGAL" in raw_msg or "private/get-currency-networks" in raw_msg:
            user_msg = ip_msg
        else:
            user_msg = f"{generic_msg} {raw_msg}".strip()

        return {
            "success": False,
            "error": user_msg,
            "total_value": 0.0,
            "balances": [],
            "currency": target_currency,
            "pricing_errors": [],
        }

    @classmethod
    def get_trading_pairs(cls, *args, **kwargs) -> List[str]:
        """Return active spot trading pairs using the standard CCXT market loader.

        Crypto.com's public `fetch_markets` works fine without credentials, so we
        delegate to the base implementation which already calls
        ``client.load_markets()`` and builds a list from ``client.markets``.
        """
        return super().get_trading_pairs(*args, **kwargs)
