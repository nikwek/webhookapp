#!/usr/bin/env python3
"""
Database hack to test TWRR timing fix.
This script will update Strategy 5's snapshot timestamp to be AFTER the transfer timestamp
to verify that our data collection fix resolves the 333% spike issue.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta
from app import create_app, db
from app.models.trading import AssetTransferLog, StrategyValueHistory

def test_twrr_timing_fix():
    """Test the TWRR timing fix by adjusting Strategy 5's problematic timestamps."""
    
    app = create_app()
    with app.app_context():
        strategy_id = 5
        
        print("=== BEFORE FIX ===")
        
        # Find the problematic transfer and snapshot
        transfers = AssetTransferLog.query.filter(
            (AssetTransferLog.strategy_id_from == strategy_id) |
            (AssetTransferLog.strategy_id_to == strategy_id)
        ).order_by(AssetTransferLog.timestamp.asc()).all()
        
        snapshots = StrategyValueHistory.query.filter(
            StrategyValueHistory.strategy_id == strategy_id
        ).order_by(StrategyValueHistory.timestamp.asc()).all()
        
        print(f"Found {len(transfers)} transfers and {len(snapshots)} snapshots for Strategy {strategy_id}")
        
        # Show the problematic timing
        problem_transfer = None
        problem_snapshot = None
        
        for transfer in transfers:
            print(f"Transfer: {transfer.timestamp} - {transfer.amount} {transfer.asset_symbol}")
            if "1000" in str(transfer.amount):
                problem_transfer = transfer
        
        for i, snapshot in enumerate(snapshots):
            print(f"Snapshot {i+1}: {snapshot.timestamp} - ${snapshot.value_usd}")
            # Find snapshot around the same time as the problem transfer
            if problem_transfer and abs((snapshot.timestamp - problem_transfer.timestamp).total_seconds()) < 1:
                problem_snapshot = snapshot
        
        if problem_transfer and problem_snapshot:
            print(f"\n🔍 PROBLEMATIC TIMING FOUND:")
            print(f"Transfer:  {problem_transfer.timestamp} (1000 USDC)")
            print(f"Snapshot:  {problem_snapshot.timestamp} (${problem_snapshot.value_usd})")
            
            time_diff = (problem_snapshot.timestamp - problem_transfer.timestamp).total_seconds()
            print(f"Time diff: {time_diff:.6f} seconds")
            
            if time_diff < 0:
                print("❌ Snapshot is BEFORE transfer - this causes the 333% bug!")
                
                print("\n=== APPLYING FIX ===")
                # Fix: Make snapshot timestamp 1ms after transfer
                new_snapshot_time = problem_transfer.timestamp + timedelta(milliseconds=1)
                problem_snapshot.timestamp = new_snapshot_time
                
                db.session.commit()
                print(f"✅ Updated snapshot timestamp to: {new_snapshot_time}")
                print(f"New time diff: {(new_snapshot_time - problem_transfer.timestamp).total_seconds():.6f} seconds")
                
                print("\n=== TESTING TWRR ENDPOINT ===")
                print("Now test the TWRR endpoint to see if the 333% spike is resolved:")
                print("curl 'http://192.168.7.20:5002/api/strategy/5/performance/twrr?debug=1'")
                
            else:
                print("✅ Snapshot is already AFTER transfer - timing is correct!")
        else:
            print("❌ Could not find the problematic transfer/snapshot pair")

if __name__ == "__main__":
    test_twrr_timing_fix()
