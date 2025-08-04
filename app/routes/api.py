# app/routes/api.py
from flask import Blueprint, jsonify, request
from flask_security import current_user
from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload
import sys

from .. import db
from ..models import ExchangeCredentials, TradingStrategy, StrategyValueHistory, WebhookLog, AssetTransferLog
from functools import wraps

# Local replacement for legacy decorator removed with Automations module

def api_login_required(view_func):
    """Simple auth guard for API routes (session or token)."""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({"error": "Authentication required"}), 401
        return view_func(*args, **kwargs)
    return wrapper
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)

def _trim_decimal(value: Decimal) -> str:
    """Return string of Decimal without insignificant trailing zeros."""
    s = format(value, 'f')
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return s

api_bp = Blueprint('api', __name__)


def _friendly_exchange(slug: str | None):
    """Return a user-friendly exchange slug (strip '-ccxt')."""
    if not slug:
        return slug
    return slug.rsplit('-ccxt', 1)[0] if slug.endswith('-ccxt') else slug


@api_bp.route('/api/strategy/<int:strategy_id>/logs', methods=['GET'])
@api_login_required
def get_strategy_logs(strategy_id: int):
    """Get webhook logs for a specific trading strategy with pagination."""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', type=int)
        if per_page is None:
            per_page = request.args.get('itemsPerPage', 20, type=int)
        try:
            per_page = int(per_page)
        except (ValueError, TypeError):
            per_page = 20

        from werkzeug.exceptions import NotFound
        # Fetch the strategy ensuring it belongs to the current user.
        strategy = (
            db.session.query(TradingStrategy)
            .filter(
                TradingStrategy.id == strategy_id,
                TradingStrategy.user_id == current_user.id,
            )
            .options(joinedload(TradingStrategy.exchange_credential))
            .first_or_404()
        )
        created_cutoff = strategy.created_at

        # Include legacy logs where strategy_id is NULL but we can infer the strategy via stored name or client_order_id prefix
        pattern = f"strat_{strategy_id}%"
        logs_query = WebhookLog.query.filter(
            and_(
                WebhookLog.timestamp >= created_cutoff,
                or_(
                    WebhookLog.strategy_id == strategy_id,
                    and_(
                        WebhookLog.strategy_id.is_(None),
                        WebhookLog.target_type == 'strategy',
                        or_(
                            WebhookLog.strategy_name == strategy.name,
                            WebhookLog.client_order_id.like(pattern)
                        )
                    )
                )
            )
        )

        pagination = logs_query.order_by(WebhookLog.timestamp.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        logs = pagination.items

        logs_data = []
        for log in logs:
            log_dict = log.to_dict()
            log_dict['strategy_name'] = strategy.name
            # Prefer exchange from strategy credential but make it user-friendly
            exch = strategy.exchange_credential.exchange if strategy.exchange_credential else log_dict.get('exchange_name')
            if exch and exch.endswith('-ccxt'):
                exch = exch.rsplit('-ccxt', 1)[0]
            log_dict['exchange_name'] = exch
            # Ensure user-friendly exchange name
            exn = log_dict.get('exchange_name')
            if exn and exn.endswith('-ccxt'):
                log_dict['exchange_name'] = exn.rsplit('-ccxt', 1)[0]
            logs_data.append(log_dict)

        # ----- Add asset transfer logs -----
        transfer_rows = AssetTransferLog.query.filter(
            AssetTransferLog.user_id == current_user.id,
            AssetTransferLog.timestamp >= created_cutoff,
            or_(AssetTransferLog.strategy_id_from == strategy_id, AssetTransferLog.strategy_id_to == strategy_id)
        ).order_by(AssetTransferLog.timestamp.desc()).all()

        # Build name lookup for involved strategy IDs (to handle deleted strategies)
        involved_ids = {row.strategy_id_from for row in transfer_rows if row.strategy_id_from}
        involved_ids.update({row.strategy_id_to for row in transfer_rows if row.strategy_id_to})
        name_lookup = {}
        if involved_ids:
            existing_strategies = TradingStrategy.query.filter(TradingStrategy.id.in_(involved_ids)).all()
            name_lookup = {s.id: s.name for s in existing_strategies}

        for row in transfer_rows:
            src_desc = (
                "Main Account"
                if row.strategy_id_from is None
                else (
                    "This Strategy"
                    if row.strategy_id_from == strategy_id
                    else (getattr(row, 'strategy_name_from', None) or name_lookup.get(row.strategy_id_from) or "(deleted)")
                )
            )
            dst_desc = (
                "Main Account"
                if row.strategy_id_to is None
                else (
                    "This Strategy"
                    if row.strategy_id_to == strategy_id
                    else (getattr(row, 'strategy_name_to', None) or name_lookup.get(row.strategy_id_to) or "(deleted)")
                )
            )
            amount_str = _trim_decimal(row.amount)
            message = f"to {dst_desc} | {amount_str} {row.asset_symbol}"
            logs_data.append({
                'id': f"transfer-{row.id}",
                'timestamp': row.timestamp.isoformat(),
                'exchange_name': (strategy.exchange_credential.exchange.rsplit('-ccxt',1)[0] if strategy.exchange_credential and strategy.exchange_credential.exchange.endswith('-ccxt') else strategy.exchange_credential.exchange),
                'strategy_name': strategy.name,
                'account_name': src_desc,
                'source_deleted': bool(row.strategy_id_from and row.strategy_id_from not in name_lookup),
                'destination_deleted': bool(row.strategy_id_to and row.strategy_id_to not in name_lookup),
                'destination_name': dst_desc,
                'amount_str': amount_str,
                'action': 'TRANSFER',
                'ticker': row.asset_symbol,
                'message': message,
                'status': 'success',
                'payload': None,
                'raw_response': None,
            })

        # Optional search filter (case-insensitive)
        search_term = request.args.get('search')
        if search_term:
            term_lower = search_term.lower()
            logs_data = [l for l in logs_data if term_lower in (str(l.get('message', '')).lower() + str(l.get('ticker', '')).lower())]

        # Sort combined list by timestamp desc
        from datetime import datetime
        logs_data.sort(key=lambda l: datetime.fromisoformat(l['timestamp']), reverse=True)

        # Manual pagination over combined list
        import math
        total_logs = len(logs_data)
        total_pages = max(1, math.ceil(total_logs / per_page))
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_logs = logs_data[start_idx:end_idx]

        # Replace original pagination variables so existing return block continues to work
        class _DummyPag:
            def __init__(self, page, per_page, total, pages):
                self.page = page
                self.per_page = per_page
                self.total = total
                self.pages = pages
        pagination = _DummyPag(page, per_page, total_logs, total_pages)
        logs_data = paginated_logs

        # logger.debug(str(pagination))
        for log in logs_data:
            pass  # debug removed

        return jsonify({
            'logs': logs_data,
            'totalPages': pagination.pages,
            'totalLogs': pagination.total,
            'pagination': {
                'page': pagination.page,
                'per_page': pagination.per_page,
                'total': pagination.total,
                'pages': pagination.pages,
            }
        })
    except NotFound:
        # Propagate 404 so Flask returns a proper not-found response
        raise
    except Exception as e:
        logger.error(f"Error fetching strategy logs: {e}")
        return jsonify({"error": "An internal error occurred"}), 500


@api_bp.route('/api/strategy/<int:strategy_id>/performance/twrr', methods=['GET'])
@api_login_required
def get_strategy_twrr(strategy_id: int):
    """Return cumulative TWRR series for a strategy.

    Query params:
        days (optional int): limit to recent N days (default 90)
    """
    try:
        from datetime import datetime, timedelta
        from sqlalchemy import asc
        from app.models.trading import AssetTransferLog  # import inside to prevent circulars
        from app.services.price_service import PriceService

        # Verify ownership
        strategy = (
            db.session.query(TradingStrategy)
            .filter(
                TradingStrategy.id == strategy_id,
                TradingStrategy.user_id == current_user.id,
            )
            .first_or_404()
        )

        # Determine range of snapshots
        days = request.args.get("days", 90, type=int)
        if days and days > 0:
            start_dt = datetime.utcnow() - timedelta(days=days)
            snap_q = StrategyValueHistory.query.filter(
                StrategyValueHistory.strategy_id == strategy_id,
                StrategyValueHistory.timestamp >= start_dt,
            )
        else:
            snap_q = StrategyValueHistory.query.filter_by(strategy_id=strategy_id)

        snaps: list[StrategyValueHistory] = snap_q.order_by(
            asc(StrategyValueHistory.timestamp)
        ).all()

        if not snaps:
            return jsonify({"strategy_id": strategy_id, "data": []})

        # Always start with an initial data point at 0 % cumulative return so the
        # front-end has something to plot even with a single snapshot.
        data = [
            {
                "timestamp": snaps[0].timestamp.isoformat(),
                "cum_return": 0.0,
                "sub_return": 0.0,
            }
        ]

        # Fetch transfers in the same time window for efficiency
        transfers_q = AssetTransferLog.query.filter(
            (AssetTransferLog.strategy_id_from == strategy_id)
            | (AssetTransferLog.strategy_id_to == strategy_id)
        )
        if days and days > 0:
            transfers_q = transfers_q.filter(AssetTransferLog.timestamp >= start_dt)

        first_snap_ts = snaps[0].timestamp
        # For TWRR calculation, we need to distinguish between funding transfers
        # and performance-affecting cash flows. We'll check for actual trading activity.
        from app.models.webhook import WebhookLog
        
        # Find the first successful trade (webhook) for this strategy
        first_trade = (
            db.session.query(WebhookLog)
            .filter(
                WebhookLog.strategy_id == strategy_id,
                WebhookLog.status == 'success',
                WebhookLog.response_data.like('%Success%')
            )
            .order_by(WebhookLog.timestamp.asc())
            .first()
        )
        
        transfers = transfers_q.all()

        # Organize transfers by interval using timestamp
        from collections import defaultdict
        # Build a mapping: interval index i  → net cash-flow that occurred **after** snaps[i-1]
        # and **up to and including** snaps[i].  This precisely follows the TWRR convention.
        interval_flows: dict[int, float] = {i: 0.0 for i in range(1, len(snaps))}
        

        for tr in transfers:
            # Determine sign (+1 inflow, −1 outflow, 0 ignore if unrelated)
            if tr.strategy_id_to == strategy_id:
                sign = 1
            elif tr.strategy_id_from == strategy_id:
                sign = -1
            else:
                continue  # unrelated transfer

            try:
                price_usd = PriceService.get_price_usd(tr.asset_symbol)
            except Exception:
                price_usd = 0.0
            usd_amount = float(tr.amount) * price_usd * sign
            


            # Locate the interval (prev_snap, curr_snap] into which this transfer falls.
            # IMPORTANT: Only count transfers as cash flows AFTER the first actual trade.
            # All transfers before trading activity are considered funding, not performance-affecting.
            assigned = False
            
            # If no trades have occurred yet, treat all transfers as funding (no cash flows)
            if first_trade is None:
                continue  # Skip this transfer - it's funding, not a cash flow
                
            # Only count transfers that occur AFTER the first trade as cash flows
            if tr.timestamp <= first_trade.timestamp:
                continue  # Skip this transfer - it's pre-trading funding
                
            # Now assign post-trading transfers to appropriate intervals
            for idx in range(1, len(snaps)):
                if snaps[idx - 1].timestamp < tr.timestamp < snaps[idx].timestamp:
                    interval_flows[idx] += usd_amount
                    assigned = True
                    break
            
            # If transfer occurs after the last snapshot, assign it to the final interval
            if not assigned and tr.timestamp >= snaps[-1].timestamp:
                final_idx = len(snaps) - 1
                interval_flows[final_idx] += usd_amount

                assigned = True
            


        # Continue building on the initial data point
        # (index 0 already added above).
        # Subsequent points will show period sub-returns and cumulative TWRR.
        #
        # Note: keep existing variable name for minimal diff.
        #
        # 'data' already has one element; we will append to it next.
        #
        # -----------------------------
        # Existing calculation loop
        # -----------------------------
        #
        # Determine aggregation period (day|month|quarter|year)
        debug_requested = bool(request.args.get('debug'))

        # Helper to round returns and zero-out tiny floating-point noise
        def _clean_rate(val: float, places: int = 4) -> float:  # noqa: ANN001
            threshold = 10 ** (-places)
            if abs(val) < threshold:
                return 0.0
            return round(val, places)
        period = request.args.get('period', 'day').lower()
        if period not in {'day', 'month', 'quarter', 'year'}:
            period = 'day'

        # Collect daily sub-period returns
        daily_points: list[tuple[datetime, float]] = []  # (timestamp, sub_return)
        debug_rows: list[dict] = []  # optional detailed breakdown

        # Start cumulative at 0.
        data = data
        cumulative = 0.0
        for i in range(1, len(snaps)):
            prev_val = float(snaps[i - 1].value_usd)
            curr_val = float(snaps[i].value_usd)
            if prev_val == 0:
                continue
            flow = interval_flows.get(i, 0.0)
            # TWRR (Time-Weighted Rate of Return) should ALWAYS ignore cash flows (transfers)
            # to measure only trading performance, regardless of portfolio value changes.
            # The formula: sub_return = (ending_value - cash_flows) / beginning_value - 1
            sub_return = (curr_val - flow) / prev_val - 1.0
            

            daily_points.append((snaps[i].timestamp, sub_return))
            if debug_requested:
                debug_rows.append({
                    "idx": i,
                    "timestamp": snaps[i].timestamp.isoformat(),
                    "prev_val": prev_val,
                    "curr_val": curr_val,
                    "flow": flow,
                    "sub_return": _clean_rate(sub_return),
                })

        # If day view requested, compute cumulative from daily_points and return
        if period == 'day':
            cumulative = 0.0
            for ts, sub_return in daily_points:
                cumulative = (1 + cumulative) * (1 + sub_return) - 1.0
                data.append({
                    "timestamp": ts.isoformat(),
                    "cum_return": _clean_rate(cumulative),
                    "sub_return": _clean_rate(sub_return),
                })
            return jsonify({"strategy_id": strategy_id, "data": data, **({"debug": debug_rows} if debug_requested else {})})

        # ---------- Aggregate returns into requested buckets ----------
        from collections import OrderedDict
        bucket_returns: "OrderedDict[str, tuple[float, datetime]]" = OrderedDict()

        def bucket_key(ts):
            if period == 'month':
                return ts.strftime('%Y-%m')
            if period == 'quarter':
                q = (ts.month - 1) // 3 + 1
                return f"{ts.year}-Q{q}"
            if period == 'year':
                return str(ts.year)
            return ts.strftime('%Y-%m-%d')  # fallback day

        for ts, sub in daily_points:
            key = bucket_key(ts)
            if key in bucket_returns:
                prev_ret, _ = bucket_returns[key]
                bucket_returns[key] = ((1 + prev_ret) * (1 + sub) - 1.0, ts)
            else:
                bucket_returns[key] = (sub, ts)

        # Build cumulative series over buckets
        cumulative = 0.0
        for key, (bucket_ret, ts) in bucket_returns.items():
            cumulative = (1 + cumulative) * (1 + bucket_ret) - 1.0
            data.append({
                "timestamp": ts.isoformat(),  # use last day timestamp of bucket
                "cum_return": _clean_rate(cumulative),
                "sub_return": _clean_rate(bucket_ret),
                "period": key,
            })

        return jsonify({"strategy_id": strategy_id, "data": data, **({"debug": debug_rows} if debug_requested else {})})
    except Exception as e:
        logger.error("Error computing TWRR for strategy %s: %s", strategy_id, e, exc_info=True)
        return jsonify({"error": "Internal error"}), 500


@api_bp.route('/api/strategy/<int:strategy_id>/risk', methods=['GET'])
@api_login_required
def get_strategy_risk(strategy_id: int):
    """Return equity curve and drawdown series for a strategy.

    Query params:
        days (optional int): Limit to most recent N days (default 90)
    Response JSON structure:
        {
          "strategy_id": 123,
          "data": [
              {"timestamp": "ISO8601", "equity": 12345.67, "drawdown": -0.12},
              ...
          ]
        }
    drawdown is expressed as a negative fraction (e.g. -0.2 = -20%).
    """
    try:
        from datetime import datetime, timedelta
        from sqlalchemy import asc
        # local import to avoid circular
        from app.models.trading import StrategyValueHistory, TradingStrategy

        # Authorisation
        strategy = (
            db.session.query(TradingStrategy)
            .filter(
                TradingStrategy.id == strategy_id,
                TradingStrategy.user_id == current_user.id,
            )
            .first_or_404()
        )

        days = request.args.get('days', 90, type=int)
        if days and days > 0:
            start_dt = datetime.utcnow() - timedelta(days=days)
            q = StrategyValueHistory.query.filter(
                StrategyValueHistory.strategy_id == strategy_id,
                StrategyValueHistory.timestamp >= start_dt,
            )
        else:
            q = StrategyValueHistory.query.filter_by(strategy_id=strategy_id)

        rows = q.order_by(asc(StrategyValueHistory.timestamp)).all()
        if not rows:
            return jsonify({"strategy_id": strategy_id, "data": []})

        data = []
        running_max = float(rows[0].value_usd)
        for r in rows:
            equity = float(r.value_usd)
            running_max = max(running_max, equity)
            drawdown = (equity / running_max) - 1.0 if running_max else 0.0
            data.append({
                "timestamp": r.timestamp.isoformat(),
                "equity": equity,
                "drawdown": drawdown,
            })

        return jsonify({"strategy_id": strategy_id, "data": data})
    except Exception as e:
        logger.error("Error computing risk series for strategy %s: %s", strategy_id, e, exc_info=True)
        return jsonify({"error": "Internal error"}), 500


@api_bp.route('/api/strategy/<int:strategy_id>/performance', methods=['GET'])
@api_login_required
def get_strategy_performance(strategy_id: int):
    """Return historical daily USD value snapshots for a trading strategy.

    Query params:
        days (optional int): Limit to the most recent N days. Default = 30.
    """
    try:
        # Ensure the strategy belongs to the current user
        strategy = (
            db.session.query(TradingStrategy)
            .filter(
                TradingStrategy.id == strategy_id,
                TradingStrategy.user_id == current_user.id,
            )
            .first_or_404()
        )

        # Determine range
        days = request.args.get('days', 30, type=int)
        if days and days > 0:
            from datetime import datetime, timedelta

            start_date = datetime.utcnow() - timedelta(days=days)
            q = StrategyValueHistory.query.filter(
                StrategyValueHistory.strategy_id == strategy_id,
                StrategyValueHistory.timestamp >= start_date,
            )
        else:
            q = StrategyValueHistory.query.filter_by(strategy_id=strategy_id)

        history_rows = (
            q.order_by(StrategyValueHistory.timestamp.asc()).all()
        )

        data = [
            {
                "timestamp": row.timestamp.isoformat(),
                "value_usd": float(row.value_usd),
                "base_asset_quantity_snapshot": float(row.base_asset_quantity_snapshot),
                "quote_asset_quantity_snapshot": float(row.quote_asset_quantity_snapshot),
            }
            for row in history_rows
        ]

        return jsonify({"strategy_id": strategy_id, "data": data})
    except Exception as e:
        logger.error(f"Error fetching performance data for strategy {strategy_id}: {e}")
        return jsonify({"error": "An internal error occurred"}), 500


# ---------------- Existing routes ----------------
@api_bp.route('/api/logs', methods=['GET'])
@api_login_required
def get_all_logs():
    """Get webhook logs with optional filtering.

    Query Params:
        page: int (default 1)
        per_page: int  – alias: itemsPerPage (default 20)
        exchange: str  – slug in exchange_credentials.exchange (e.g. ``coinbase-ccxt``)
        strategy: str  – strategy name for convenience
        search: str    – simple case-insensitive search in ``message``/``trading_pair``/``payload`` JSON string

    Returns (JSON):
        logs: list[dict]
        totalPages: int
        totalLogs: int
        pagination: {page, per_page, total, pages}
    """

    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', type=int)
        if per_page is None:
            per_page = request.args.get('itemsPerPage', 20, type=int)
        try:
            per_page = int(per_page)
        except (ValueError, TypeError):
            per_page = 20
        
        # Optional filters sent by the React component
        exchange_filter = request.args.get('exchange') or None
        strategy_filter = request.args.get('strategy') or None
        strategy_id_filter = request.args.get('strategy_id', type=int)
        search_term = request.args.get('search') or None

        logger.info(f"Fetching logs – page:{page} per_page:{per_page} exchange:{exchange_filter} strategy:{strategy_filter} search:{search_term}")

        # Build a base query restricted to current user's data only
        from ..models import Automation  # local import to avoid circular deps
        logs_query = WebhookLog.query.filter(
            or_(
                # Logs linked to strategies owned by the user
                WebhookLog.strategy.has(TradingStrategy.user_id == current_user.id),
                # Logs linked to automations owned by the user (legacy)
                WebhookLog.automation.has(Automation.user_id == current_user.id)
            )
        )
        # Apply filters if provided
        if exchange_filter:
            # Match logs by explicit exchange_name OR by strategies linked to credentials on this exchange
            from ..models import Automation
            # Determine all strategy IDs for current user on this exchange to broaden search
            user_creds = ExchangeCredentials.query.filter_by(user_id=current_user.id, exchange=exchange_filter).all()
            strategy_ids_for_exchange = []
            strategy_names_for_exchange = []
            if user_creds:
                cred_ids = [c.id for c in user_creds]
                strategies_for_exchange = TradingStrategy.query.filter(TradingStrategy.exchange_credential_id.in_(cred_ids)).all()
                strategy_ids_for_exchange = [s.id for s in strategies_for_exchange]
                strategy_names_for_exchange = [s.name for s in strategies_for_exchange]
            logs_query = logs_query.filter(
                or_(
                    WebhookLog.exchange_name == exchange_filter,
                    WebhookLog.strategy_id.in_(strategy_ids_for_exchange),
                    and_(
                        WebhookLog.strategy_id.is_(None),
                        WebhookLog.exchange_name.is_(None),
                        WebhookLog.strategy_name.in_(strategy_names_for_exchange)
                    ),
                    and_(
                        WebhookLog.exchange_name.is_(None),
                        WebhookLog.strategy.has(
                            TradingStrategy.exchange_credential.has(ExchangeCredentials.exchange == exchange_filter)
                        )
                    ),
                    and_(
                        WebhookLog.exchange_name.is_(None),
                        WebhookLog.automation.has(
                            Automation.exchange_credential.has(ExchangeCredentials.exchange == exchange_filter)
                        )
                    )
                )
            )
        if strategy_id_filter:
            logs_query = logs_query.filter(WebhookLog.strategy_id == strategy_id_filter)
        elif strategy_filter:
            logs_query = logs_query.filter(WebhookLog.strategy_name == strategy_filter)
        if search_term:
            term_like = f"%{search_term}%"
            logs_query = logs_query.filter(or_(WebhookLog.message.ilike(term_like), WebhookLog.trading_pair.ilike(term_like)))
        
        pagination = logs_query.order_by(WebhookLog.id.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

                # Fetch ALL matching webhook logs (drop db-level pagination since we'll combine with transfers)
        webhook_rows = logs_query.order_by(WebhookLog.timestamp.desc()).all()

                # Build logs_data from webhook rows
        # Build logs_data from ALL matching webhook rows (no db pagination)
        logs_data = []
        for log in webhook_rows:
            log_dict = log.to_dict()
            # Populate missing strategy/exchange names if possible
            if not log_dict.get('strategy_name') or log_dict['strategy_name'] == 'Unknown':
                if log.strategy:
                    log_dict['strategy_name'] = log.strategy.name
                elif log.automation:
                    log_dict['strategy_name'] = log.automation.name
            if not log_dict.get('exchange_name') or log_dict['exchange_name'] in (None, 'None', ''):
                if log.strategy and log.strategy.exchange_credential:
                    exch = log.strategy.exchange_credential.exchange
                    if exch and exch.endswith('-ccxt'):
                        exch = exch.rsplit('-ccxt', 1)[0]
                    log_dict['exchange_name'] = exch
                elif log.automation and getattr(log.automation, 'exchange_credential', None):
                    exch = log.automation.exchange_credential.exchange
                    if exch and exch.endswith('-ccxt'):
                        exch = exch.rsplit('-ccxt', 1)[0]
                    log_dict['exchange_name'] = exch
            # Ensure user-friendly exchange name
            exn = log_dict.get('exchange_name')
            if exn and exn.endswith('-ccxt'):
                log_dict['exchange_name'] = exn.rsplit('-ccxt', 1)[0]
            logs_data.append(log_dict)

        # ----- Append AssetTransferLog rows -----
        from sqlalchemy import false as _false  # utility
        strategy_ids_for_exchange = locals().get('strategy_ids_for_exchange', [])
        transfer_query = AssetTransferLog.query.filter(AssetTransferLog.user_id == current_user.id)
        if exchange_filter:
            if strategy_ids_for_exchange:
                transfer_query = transfer_query.filter(or_(AssetTransferLog.strategy_id_from.in_(strategy_ids_for_exchange),
                                                           AssetTransferLog.strategy_id_to.in_(strategy_ids_for_exchange)))
            else:
                transfer_query = transfer_query.filter(_false())
        if strategy_id_filter:
            transfer_query = transfer_query.filter(or_(AssetTransferLog.strategy_id_from == strategy_id_filter,
                                                       AssetTransferLog.strategy_id_to == strategy_id_filter))
        elif strategy_filter:
            strat_obj = TradingStrategy.query.filter_by(user_id=current_user.id, name=strategy_filter).first()
            if strat_obj:
                transfer_query = transfer_query.filter(or_(AssetTransferLog.strategy_id_from == strat_obj.id,
                                                           AssetTransferLog.strategy_id_to == strat_obj.id))

        transfer_rows = transfer_query.order_by(AssetTransferLog.timestamp.desc()).all()

        # Helper to infer exchange from main-account identifier
        from ..models import ExchangeCredentials as _ExchangeCred
        def _exchange_from_identifier(ident: str | None):
            if ident and ident.startswith('main::'):
                parts = ident.split('::')
                if len(parts) >= 2:
                    try:
                        cid = int(parts[1])
                        cred = _ExchangeCred.query.get(cid)
                        if cred and cred.exchange:
                            return _friendly_exchange(cred.exchange)
                    except ValueError:
                        pass
            return None
        # Build lookup maps for strategies involved in transfers
        involved_ids = {row.strategy_id_from for row in transfer_rows if row.strategy_id_from}
        involved_ids.update({row.strategy_id_to for row in transfer_rows if row.strategy_id_to})
        name_lookup = {}
        exch_lookup = {}
        if involved_ids:
            strats = TradingStrategy.query.filter(TradingStrategy.id.in_(involved_ids)).all()
            name_lookup = {s.id: s.name for s in strats}
            exch_lookup = {}
            for s in strats:
                ex = s.exchange_credential.exchange if s.exchange_credential else None
                if ex and ex.endswith('-ccxt'):
                    ex = ex.rsplit('-ccxt', 1)[0]
                exch_lookup[s.id] = _friendly_exchange(ex)

        for row in transfer_rows:
            # Skip main→main transfers where both strategy ids are null
            if row.strategy_id_from is None and row.strategy_id_to is None:
                continue
            src_desc = (
                'Main Account'
                if row.strategy_id_from is None
                else (getattr(row, 'strategy_name_from', None) or name_lookup.get(row.strategy_id_from) or '(deleted)')
            )
            dst_desc = (
                'Main Account'
                if row.strategy_id_to is None
                else (getattr(row, 'strategy_name_to', None) or name_lookup.get(row.strategy_id_to) or '(deleted)')
            )
            if search_term and search_term.lower() not in (src_desc + dst_desc + row.asset_symbol).lower():
                continue
            amount_str = _trim_decimal(row.amount)
            message = f"to {dst_desc} | {amount_str} {row.asset_symbol}"
            exch_val = None
            if row.strategy_id_from and exch_lookup.get(row.strategy_id_from):
                exch_val = exch_lookup[row.strategy_id_from]
            elif row.strategy_id_to and exch_lookup.get(row.strategy_id_to):
                exch_val = exch_lookup[row.strategy_id_to]
            # Fallback: infer from main account identifier
            if exch_val is None:
                exch_val = _exchange_from_identifier(row.source_identifier) or _exchange_from_identifier(row.destination_identifier)

            logs_data.append({
                'id': f"transfer-{row.id}",
                'timestamp': row.timestamp.isoformat(),
                'exchange_name': _friendly_exchange(exch_val or exchange_filter),
                'strategy_name': src_desc,
                'account_name': src_desc,
                'source_deleted': bool(row.strategy_id_from and row.strategy_id_from not in name_lookup),
                'destination_deleted': bool(row.strategy_id_to and row.strategy_id_to not in name_lookup),
                'destination_name': dst_desc,
                'amount_str': amount_str,
                'action': 'TRANSFER',
                'ticker': row.asset_symbol,
                'message': message,
                'status': 'success',
                'payload': None,
                'raw_response': None,
            })

        # ----- Final sort & in-memory pagination -----
        from datetime import datetime as _dt
        logs_data.sort(key=lambda l: _dt.fromisoformat(l['timestamp']), reverse=True)
        import math
        total_logs = len(logs_data)
        total_pages = max(1, math.ceil(total_logs / per_page)) if total_logs else 1
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * per_page
        paginated_logs = logs_data[start_idx:start_idx + per_page]

        return jsonify({
            'logs': paginated_logs,
            'totalPages': total_pages,
            'totalLogs': total_logs,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total_logs,
                'pages': total_pages,
            }
        })
    except Exception as e:
        logger.error(f"Error fetching all logs: {e}")
        return jsonify({"error": "An internal error occurred"}), 500


@api_bp.route('/api/exchange/<string:exchange_id>/logs', methods=['GET'])
@api_login_required
def get_exchange_logs(exchange_id: str):
    """Get webhook logs for all trading strategies on an exchange with pagination."""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', type=int)
        if per_page is None:
            per_page = request.args.get('itemsPerPage', 20, type=int)
        try:
            per_page = int(per_page)
        except (ValueError, TypeError):
            per_page = 20

        # First get all credentials for this exchange and user
        exchange_credentials = ExchangeCredentials.query.filter_by(
            user_id=current_user.id,
            exchange=exchange_id
        ).all()
        if not exchange_credentials:
            return jsonify({"error": "No credentials found for this exchange"}), 404
        # Get all strategy IDs for these credentials
        credential_ids = [cred.id for cred in exchange_credentials]
        strategies = TradingStrategy.query.filter(
            TradingStrategy.exchange_credential_id.in_(credential_ids)
        ).all()
        strategy_ids = [strategy.id for strategy in strategies]
        if not strategy_ids:
            # Return empty logs if no strategies found
            return jsonify({
                'logs': [],
                'pagination': {
                    'page': page,
                    'per_page': per_page,
                    'total': 0,
                    'pages': 0,
                }
            })
        # Build query for all logs for this exchange, including from deleted strategies
        logs_query = WebhookLog.query.filter(
            or_(
                # Logs from active strategies for this exchange
                WebhookLog.strategy_id.in_(strategy_ids) if strategy_ids else False,
                # Logs from deleted strategies but with matching exchange name
                and_(
                    WebhookLog.strategy_name.isnot(None),
                    WebhookLog.exchange_name == exchange_id
                )
            )
        ).order_by(WebhookLog.timestamp.desc())
        
        # Get paginated results
        pagination = logs_query.paginate(
            page=page, per_page=per_page, error_out=False
        )
        logs = pagination.items
        
        # logger.debug(str(pagination))
        for log in logs:
            pass  # debug removed

        # Create a mapping of strategy_id to strategy details for efficient lookup
        strategy_map = {}
        for strategy in strategies:
            strategy_map[strategy.id] = {
                'name': strategy.name,
                'exchange_id': exchange_id
            }
        
        logs_data = []
        for log in logs:
            log_dict = log.to_dict()
            # For active strategies, ensure strategy name and exchange name are set
            if log.strategy_id and log.strategy_id in strategy_map:
                log_dict['strategy_name'] = strategy_map[log.strategy_id]['name']
                log_dict['exchange_name'] = exchange_id
            # Fallbacks when names are still missing (e.g., logs tied to automations)
            if (not log_dict.get('strategy_name') or log_dict['strategy_name'] == 'Unknown') and log.automation:
                log_dict['strategy_name'] = log.automation.name
            if (not log_dict.get('exchange_name') or log_dict['exchange_name'] in (None, 'None', '')) and log.automation and getattr(log.automation, 'exchange_credential', None):
                log_dict['exchange_name'] = log.automation.exchange_credential.exchange
            # Ensure user-friendly exchange name
            exn = log_dict.get('exchange_name')
            if exn and exn.endswith('-ccxt'):
                log_dict['exchange_name'] = exn.rsplit('-ccxt', 1)[0]
            logs_data.append(log_dict)

        # ----- Include AssetTransferLogs for this exchange -----
        # Build list of transfer records touching strategies on this exchange or their main account
        cred_ids = credential_ids  # already determined above
        # Build filter: user match AND (strategy involvement OR main-account involvement)
        base_filter = AssetTransferLog.user_id == current_user.id
        strategy_cond = None
        main_cond = None
        if strategy_ids:
            strategy_cond = or_(
                AssetTransferLog.strategy_id_from.in_(strategy_ids),
                AssetTransferLog.strategy_id_to.in_(strategy_ids)
            )
        if cred_ids:
            main_like_clauses = [
                AssetTransferLog.source_identifier.like(f"main::{cid}::%") for cid in cred_ids
            ] + [
                AssetTransferLog.destination_identifier.like(f"main::{cid}::%") for cid in cred_ids
            ]
            main_cond = or_(*main_like_clauses)

        # Combine conditions so that either branch qualifies
        if strategy_cond is not None and main_cond is not None:
            final_cond = or_(strategy_cond, main_cond)
        elif strategy_cond is not None:
            final_cond = strategy_cond
        elif main_cond is not None:
            final_cond = main_cond
        else:
            final_cond = None  # No extra filtering – unlikely but safe fallback

        query_filters = [base_filter]
        if final_cond is not None:
            query_filters.append(final_cond)

        transfer_rows = AssetTransferLog.query.filter(and_(*query_filters)).order_by(AssetTransferLog.timestamp.desc()).all()

        # Map strategy id -> name for quick lookup (handle deleted)
        strat_name_lookup = {s.id: s.name for s in strategies}

        def describe_side(sid, identifier):
            if sid is None:
                return "Main Account"
            return strat_name_lookup.get(sid, "(deleted)")

        for t in transfer_rows:
            # Skip transfers that do not involve any strategy (main account to main account)
            if t.strategy_id_from is None and t.strategy_id_to is None:
                continue
            src_desc = (
                'Main Account'
                if t.strategy_id_from is None
                else (getattr(t, 'strategy_name_from', None) or strat_name_lookup.get(t.strategy_id_from) or '(deleted)')
            )
            dst_desc = (
                'Main Account'
                if t.strategy_id_to is None
                else (getattr(t, 'strategy_name_to', None) or strat_name_lookup.get(t.strategy_id_to) or '(deleted)')
            )
            amount_str = _trim_decimal(t.amount)
            message = f"to {dst_desc} | {amount_str} {t.asset_symbol}"
            logs_data.append({
                'id': f"transfer-{t.id}",
                'timestamp': t.timestamp.isoformat(),
                'exchange_name': _friendly_exchange(exchange_id),
                'strategy_name': src_desc,  # retain for compatibility
                'account_name': src_desc,
                'source_deleted': bool(t.strategy_id_from and t.strategy_id_from not in strat_name_lookup),
                'destination_deleted': bool(t.strategy_id_to and t.strategy_id_to not in strat_name_lookup),
                'destination_name': dst_desc,
                'amount_str': amount_str,
                'action': 'TRANSFER',
                'ticker': t.asset_symbol,
                'message': message,
                'status': 'success',
                'payload': None,
                'raw_response': None,
            })

        # ---- Sort combined list and paginate ----
        from datetime import datetime
        logs_data.sort(key=lambda l: datetime.fromisoformat(l['timestamp']), reverse=True)
        import math
        total_logs = len(logs_data)
        total_pages = max(1, math.ceil(total_logs / per_page))
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        paginated_logs = logs_data[start_idx:end_idx]

        return jsonify({
            'logs': paginated_logs,
            'totalPages': total_pages,
            'totalLogs': total_logs,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total_logs,
                'pages': total_pages,
            }
        })
    except Exception as e:
        logger.error(f"Error fetching exchange logs: {e}")
        return jsonify({"error": "An internal error occurred"}), 500