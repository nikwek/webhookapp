#!/usr/bin/env python
"""Seed Demo Strategy (ID=6) with real production data from strategy 1.

This script takes the real production values and creates corresponding
strategy value history entries for testing chart improvements.

USAGE (from repo root):
    python -m scripts.seed_demo_strategy
"""
from datetime import datetime
from decimal import Decimal

from app import create_app, db
from app.models.trading import StrategyValueHistory, TradingStrategy

# Real production data from strategy 1
PRODUCTION_DATA = [
    ("2025-07-16 23:00:35.623905", 5500),
    ("2025-07-20 22:42:35.355075", 5500),
    ("2025-07-21 08:00:15.018712", 5474.12),
    ("2025-07-22 18:48:50.884546", 5471.37),
    ("2025-07-24 19:52:17.224671", 5460.23),
    ("2025-07-25 07:05:00.396551", 5284.19),
    ("2025-07-26 07:05:00.424295", 5384.09),
    ("2025-07-27 07:05:00.335006", 5425.92),
    ("2025-07-28 07:05:00.337804", 5476.37),
    ("2025-07-29 07:05:00.390311", 5452.93),
    ("2025-07-30 07:05:00.299668", 5425.41),
    ("2025-07-31 07:05:00.337597", 5443.76),
    ("2025-08-01 07:05:00.422956", 5284.42),
    ("2025-08-02 07:05:00.385026", 5214.11),
    ("2025-08-03 07:05:00.395921", 5209.15),
    ("2025-08-04 07:05:00.395309", 5249.24),
    ("2025-08-06 07:05:00.404794", 5232.36),
    ("2025-08-07 07:05:00.380691", 5262.5),
    ("2025-08-08 07:05:00.396306", 5352.58),
    ("2025-08-09 07:05:00.337638", 5351.2),
    ("2025-08-10 07:05:00.412518", 5417.85),
    ("2025-08-11 07:05:00.327974", 5604.94),
]

DEMO_STRATEGY_ID = 6


def main():
    """Seed Demo Strategy with production data."""
    app = create_app()
    with app.app_context():
        # Verify Demo Strategy exists
        strategy = TradingStrategy.query.get(DEMO_STRATEGY_ID)
        if not strategy:
            print(f"Strategy {DEMO_STRATEGY_ID} not found. Please create it first.")
            return
        
        print(f"Seeding strategy {DEMO_STRATEGY_ID} ({strategy.name}) with production data...")
        
        # Clean up existing data
        db.session.query(StrategyValueHistory).filter_by(strategy_id=DEMO_STRATEGY_ID).delete(
            synchronize_session=False
        )
        
        # Parse trading pair for realistic asset allocation
        if '/' in strategy.trading_pair:
            base_symbol, quote_symbol = strategy.trading_pair.split('/')
        else:
            base_symbol, quote_symbol = "ETH", "USDC"  # fallback
        
        # Insert production data
        for timestamp_str, value_usd in PRODUCTION_DATA:
            # Parse timestamp (SQLite format)
            timestamp = datetime.fromisoformat(timestamp_str.replace('|', ''))
            
            # Generate realistic base/quote quantities
            # Assume we're holding quote asset (USDC) most of the time for simplicity
            # This creates realistic-looking data without complex trading simulation
            base_qty = Decimal("0")
            quote_qty = Decimal(str(value_usd))
            
            # Occasionally hold base asset to make it more realistic
            if hash(timestamp_str) % 5 == 0:  # ~20% of the time
                # Simulate holding base asset (e.g., SOL at ~$150)
                estimated_base_price = 150
                base_qty = Decimal(str(value_usd)) / Decimal(str(estimated_base_price))
                quote_qty = Decimal("0")
            
            db.session.add(
                StrategyValueHistory(
                    strategy_id=DEMO_STRATEGY_ID,
                    timestamp=timestamp,
                    value_usd=Decimal(str(value_usd)),
                    base_asset_quantity_snapshot=base_qty,
                    quote_asset_quantity_snapshot=quote_qty,
                )
            )
        
        # Update strategy's current allocation to match final values
        final_value = PRODUCTION_DATA[-1][1]
        strategy.allocated_base_asset_quantity = Decimal("0")
        strategy.allocated_quote_asset_quantity = Decimal(str(final_value))
        db.session.add(strategy)
        
        db.session.commit()
        
        print(f"✅ Seeded {len(PRODUCTION_DATA)} real production datapoints")
        print(f"   - Date range: 2025-07-16 to 2025-08-11")
        print(f"   - Value range: ${min(d[1] for d in PRODUCTION_DATA):.2f} - ${max(d[1] for d in PRODUCTION_DATA):.2f}")
        print(f"   - Final value: ${final_value}")
        print(f"   - Perfect for testing chart label improvements!")


if __name__ == "__main__":
    main()
