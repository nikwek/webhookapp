#!/usr/bin/env python
"""Generate realistic test data for chart label testing.

This script creates dense daily strategy value history data with various patterns:
- Flat periods (to test overlapping labels at same height)
- Volatile periods (to test label density)
- Trending periods (to test label positioning)
- Mixed scenarios

USAGE (from repo root):
    python -m scripts.generate_chart_test_data --strategy-id 4 --days 90

Or with Flask shell:
    FLASK_APP=run.py flask shell < scripts/generate_chart_test_data.py
"""
import argparse
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Tuple

from app import create_app, db
from app.models.trading import StrategyValueHistory, TradingStrategy


def generate_realistic_values(
    start_value: float, 
    days: int, 
    base_volatility: float = 0.02
) -> List[Tuple[datetime, Decimal]]:
    """Generate realistic daily strategy values with various patterns."""
    
    values = []
    current_value = start_value
    base_ts = (
        datetime.now(timezone.utc)
        .replace(hour=12, minute=0, second=0, microsecond=0)
        - timedelta(days=days)
    )
    
    for day in range(days):
        ts = base_ts + timedelta(days=day)
        
        # Create different patterns based on day ranges
        if day < days * 0.2:  # First 20% - flat period with tiny variations
            # Flat period to test overlapping labels
            daily_change = random.uniform(-0.001, 0.001)  # ±0.1%
            
        elif day < days * 0.4:  # Next 20% - volatile period
            # High volatility to test dense labels
            daily_change = random.uniform(-0.05, 0.05)  # ±5%
            
        elif day < days * 0.6:  # Next 20% - steady uptrend
            # Upward trend with small variations
            daily_change = random.uniform(0.005, 0.015)  # +0.5% to +1.5%
            
        elif day < days * 0.8:  # Next 20% - another flat period
            # Another flat period with slightly different base
            daily_change = random.uniform(-0.002, 0.002)  # ±0.2%
            
        else:  # Last 20% - downtrend
            # Downward trend
            daily_change = random.uniform(-0.02, 0.005)  # -2% to +0.5%
        
        # Apply the change
        current_value *= (1 + daily_change)
        
        # Add some noise to make it more realistic
        noise = random.uniform(-base_volatility/4, base_volatility/4)
        current_value *= (1 + noise)
        
        # Ensure we don't go negative
        current_value = max(current_value, 0.01)
        
        values.append((ts, Decimal(str(round(current_value, 2)))))
    
    return values


def generate_asset_quantities(
    value_history: List[Tuple[datetime, Decimal]], 
    trading_pair: str
) -> List[Tuple[datetime, Decimal, Decimal, Decimal]]:
    """Generate corresponding base/quote asset quantities for each value."""
    
    # Parse trading pair (e.g., "SOL/USDC" -> base="SOL", quote="USDC")
    if '/' in trading_pair:
        base_symbol, quote_symbol = trading_pair.split('/')
    else:
        base_symbol, quote_symbol = "ETH", "USDC"  # fallback
    
    result = []
    
    for i, (ts, value_usd) in enumerate(value_history):
        # Simulate realistic price movements for the base asset
        # Let's assume base asset price varies between $50-$200
        base_price = 100 + (50 * random.uniform(-1, 1))  # $50-$150 range
        
        # Randomly decide if we're holding base or quote asset
        # Create some trading activity patterns
        if i == 0:
            # Start with quote asset (USDC)
            base_qty = Decimal("0")
            quote_qty = value_usd
        elif i % 7 == 0:  # Trade every ~7 days
            if random.choice([True, False]):
                # Hold base asset
                base_qty = value_usd / Decimal(str(base_price))
                quote_qty = Decimal("0")
            else:
                # Hold quote asset
                base_qty = Decimal("0")
                quote_qty = value_usd
        else:
            # Keep previous position type but update quantities
            prev_base = result[-1][1] if result else Decimal("0")
            if prev_base > 0:
                # Was holding base, continue holding base
                base_qty = value_usd / Decimal(str(base_price))
                quote_qty = Decimal("0")
            else:
                # Was holding quote, continue holding quote
                base_qty = Decimal("0")
                quote_qty = value_usd
        
        result.append((ts, base_qty, quote_qty, value_usd))
    
    return result


def main(strategy_id: int = None, days: int = 90):
    """Generate test data for the specified strategy."""
    
    app = create_app()
    with app.app_context():
        # If no strategy_id provided, try to find one
        if strategy_id is None:
            strategy = TradingStrategy.query.first()
            if not strategy:
                print("No strategies found. Please create a strategy first.")
                return
            strategy_id = strategy.id
        else:
            strategy = TradingStrategy.query.get(strategy_id)
            if not strategy:
                print(f"Strategy {strategy_id} not found.")
                return
        
        print(f"Generating {days} days of test data for strategy {strategy_id} ({strategy.name})")
        
        # Clean up existing test data
        db.session.query(StrategyValueHistory).filter_by(strategy_id=strategy_id).delete(
            synchronize_session=False
        )
        
        # Generate realistic value progression
        start_value = float(strategy.allocated_base_asset_quantity or 0) * 100 + float(strategy.allocated_quote_asset_quantity or 1000)
        if start_value < 100:
            start_value = 1000  # Default starting value
            
        value_history = generate_realistic_values(start_value, days)
        
        # Generate corresponding asset quantities
        asset_data = generate_asset_quantities(value_history, strategy.trading_pair)
        
        # Insert into database
        for ts, base_qty, quote_qty, value_usd in asset_data:
            db.session.add(
                StrategyValueHistory(
                    strategy_id=strategy_id,
                    timestamp=ts,
                    value_usd=value_usd,
                    base_asset_quantity_snapshot=base_qty,
                    quote_asset_quantity_snapshot=quote_qty,
                )
            )
        
        # Update strategy's current allocation to match final values
        final_base, final_quote = asset_data[-1][1], asset_data[-1][2]
        strategy.allocated_base_asset_quantity = final_base
        strategy.allocated_quote_asset_quantity = final_quote
        db.session.add(strategy)
        
        db.session.commit()
        
        print(f"✅ Generated {len(asset_data)} datapoints for strategy {strategy_id}")
        print(f"   - Flat periods: Days 1-{int(days*0.2)} and {int(days*0.6)}-{int(days*0.8)}")
        print(f"   - Volatile period: Days {int(days*0.2)}-{int(days*0.4)}")
        print(f"   - Uptrend: Days {int(days*0.4)}-{int(days*0.6)}")
        print(f"   - Downtrend: Days {int(days*0.8)}-{days}")
        print(f"   - Final value: ${asset_data[-1][3]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate chart test data')
    parser.add_argument('--strategy-id', type=int, help='Strategy ID to generate data for')
    parser.add_argument('--days', type=int, default=90, help='Number of days of data to generate')
    
    args = parser.parse_args()
    main(args.strategy_id, args.days)
