from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict


FIAT_STABLES = {"USD", "USDC", "USDT", "USDP", "DAI"}


def _infer_decimals_from_step(step: Any) -> int:
    try:
        s = str(step)
    except Exception:
        return 8
    if 'e-' in s or 'E-' in s:
        try:
            return int(s.split('-')[-1])
        except Exception:
            return 8
    if '.' in s:
        return len(s.split('.')[-1].rstrip('0')) or 0
    return 0


def get_market_precisions(client: Any, symbol: str) -> Dict[str, Any]:
    """
    Resolve amount, price, and quote (cost) precisions/quanta for a symbol using CCXT markets.

    Returns dict with:
      - amount_decimals, price_decimals, quote_decimals
      - amount_quant, price_quant, quote_quant (Decimal quanta)
      - quote_asset (str)
    Fallbacks: amount=8 dp; price=8 dp; quote=2 dp if fiat/stable, else 8 dp.
    """
    amount_decimals = 8
    price_decimals = 8
    quote_decimals = 8
    quote_asset = None

    try:
        client.load_markets()
        market = client.markets.get(symbol) if hasattr(client, 'markets') else None
    except Exception:
        market = None

    if isinstance(market, dict):
        # Amount precision
        prec_amount = (market.get("precision") or {}).get("amount")
        if isinstance(prec_amount, int):
            amount_decimals = prec_amount
        elif prec_amount is not None:
            amount_decimals = _infer_decimals_from_step(prec_amount)

        # Price precision
        prec_price = (market.get("precision") or {}).get("price")
        if isinstance(prec_price, int):
            price_decials_candidate = prec_price
            price_decimals = price_decials_candidate
        elif prec_price is not None:
            price_decimals = _infer_decimals_from_step(prec_price)

        # Quote asset and quote precision
        quote_asset = market.get("quote")

        # Try limits.cost.min to infer quote decimals
        limits = market.get("limits") or {}
        cost_limits = limits.get("cost") or {}
        cost_min = cost_limits.get("min")
        if cost_min is not None:
            quote_decimals = _infer_decimals_from_step(cost_min)

        # Heuristic if not obtained above
        if quote_decimals == 8 and isinstance(quote_asset, str) and quote_asset.upper() in FIAT_STABLES:
            quote_decimals = 2

    amount_quant = Decimal('1').scaleb(-amount_decimals)
    price_quant = Decimal('1').scaleb(-price_decimals)
    quote_quant = Decimal('1').scaleb(-quote_decimals)

    return {
        'amount_decimals': amount_decimals,
        'price_decimals': price_decimals,
        'quote_decimals': quote_decimals,
        'amount_quant': amount_quant,
        'price_quant': price_quant,
        'quote_quant': quote_quant,
        'quote_asset': quote_asset,
    }
