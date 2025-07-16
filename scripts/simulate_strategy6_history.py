#!/usr/bin/env python
"""Populate the database with a deposit-plus-trade timeline for strategy_id=6.

The timeline contains 5 events spaced one day apart:
1. 15 USDC deposited from the parent main account into the strategy.
2. Buy 0.00475932 ETH with all USDC (snapshot only).
3. Sell all ETH back to USDC at $3 140.7566899 (snapshot only).
4. Buy 0.004723 ETH with all USDC (snapshot only).
5. Sell all ETH back to USDC at $3 120.3674975 (snapshot only).

Running the script will:
• Wipe any existing AssetTransferLog or StrategyValueHistory rows that reference the strategy (so you can re-run it safely).
• Insert one AssetTransferLog (deposit) and five StrategyValueHistory snapshots, each exactly 24 h apart, starting 4 days ago at 12:00 UTC.
• Update the strategy’s allocated_base_asset_quantity / allocated_quote_asset_quantity to reflect the *final* position after step 5.

USAGE (from repo root):

    # Option 1 – via `python` (ensure your virtual-env is activated)
    python -m scripts.simulate_strategy6_history

    # Option 2 – via Flask shell
    FLASK_APP=run.py flask shell < scripts/simulate_strategy6_history.py

The script requires no arguments; edit STRATEGY_ID if you want to target a different one.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app import create_app, db
from app.models.trading import (
    AssetTransferLog,
    StrategyValueHistory,
    TradingStrategy,
)

STRATEGY_ID = 6  # Change if needed

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _usd_value(base_qty: Decimal, quote_qty: Decimal, *, offset: int) -> Decimal:
    """Return USD value given base/quote quantities and the trade index (offset).

    For snapshots where we hold ETH (`base_qty` > 0), we hard-code the trade
    average price that was supplied by the user for that particular leg.
    """
    if quote_qty > 0:
        return quote_qty

    # Holding ETH – map snapshot offset → quoted price
    px_map: dict[int, Decimal] = {
        1: Decimal("3143.304285864367"),  # First buy
        3: Decimal("3139.948692229515"),  # Second buy
    }
    price = px_map.get(offset, Decimal("3140"))  # fallback reasonable price
    return base_qty * price


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def main() -> None:
    app = create_app()
    with app.app_context():
        strategy: TradingStrategy | None = TradingStrategy.query.get(STRATEGY_ID)
        if strategy is None:
            raise RuntimeError(f"Strategy {STRATEGY_ID} not found – aborting")

        user_id = strategy.user_id

        # Start 4 days ago at 12:00 UTC so points are visible in charts.
        base_ts = (
            datetime.now(timezone.utc)
            .replace(hour=12, minute=0, second=0, microsecond=0)
            - timedelta(days=4)
        )

        # Clean up prior test runs for idempotency.
        db.session.query(AssetTransferLog).filter(
            (AssetTransferLog.strategy_id_to == STRATEGY_ID)
            | (AssetTransferLog.strategy_id_from == STRATEGY_ID)
        ).delete(synchronize_session=False)
        db.session.query(StrategyValueHistory).filter_by(strategy_id=STRATEGY_ID).delete(
            synchronize_session=False
        )

        # ------------------------------------------------------------------
        # 1️⃣  Deposit – 15 USDC → strategy
        # ------------------------------------------------------------------
        db.session.add(
            AssetTransferLog(
                user_id=user_id,
                timestamp=base_ts,
                source_identifier=f"main:{strategy.exchange_credential_id}",
                destination_identifier=f"strategy:{STRATEGY_ID}",
                asset_symbol="USDC",
                amount=Decimal("15"),
                strategy_id_from=None,
                strategy_id_to=STRATEGY_ID,
            )
        )

        # ------------------------------------------------------------------
        # 5 snapshots (deposit + 4 trades) spaced one day apart
        # ------------------------------------------------------------------
        snapshots: list[tuple[int, Decimal, Decimal]] = [
            # (days offset,  base_qty (ETH),         quote_qty (USDC))
            (0, Decimal("0"),               Decimal("15")),                # after deposit
            (1, Decimal("0.00475932"),     Decimal("0")),                # buy
            (2, Decimal("0"),               Decimal("14.8731267988525")),  # sell
            (3, Decimal("0.004723"),       Decimal("0")),                # buy
            (4, Decimal("0"),               Decimal("14.6638082126445")),  # sell
        ]

        for offset, base_q, quote_q in snapshots:
            ts = base_ts + timedelta(days=offset)
            value_usd = _usd_value(base_q, quote_q, offset=offset)
            db.session.add(
                StrategyValueHistory(
                    strategy_id=STRATEGY_ID,
                    timestamp=ts,
                    value_usd=value_usd,
                    base_asset_quantity_snapshot=base_q,
                    quote_asset_quantity_snapshot=quote_q,
                )
            )

        # Final position (after last sell)
        final_base = snapshots[-1][1]
        final_quote = snapshots[-1][2]
        strategy.allocated_base_asset_quantity = final_base
        strategy.allocated_quote_asset_quantity = final_quote
        db.session.add(strategy)

        db.session.commit()
        print(
            "Inserted test timeline for strategy",
            STRATEGY_ID,
            "– 1 transfer &",
            len(snapshots),
            "snapshots",
        )


if __name__ == "__main__":
    main()
