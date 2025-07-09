# app/routes/api.py
from flask import Blueprint, jsonify, request
from flask_security import current_user
from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload
import sys

from .. import db
from ..models import ExchangeCredentials, TradingStrategy, StrategyValueHistory, WebhookLog, AssetTransferLog
from .automation import api_login_required
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

        # Include legacy logs where strategy_id is NULL but we can infer the strategy via stored name or client_order_id prefix
        pattern = f"strat_{strategy_id}%"
        logs_query = WebhookLog.query.filter(
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

        pagination = logs_query.order_by(WebhookLog.timestamp.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        logs = pagination.items

        logs_data = []
        for log in logs:
            log_dict = log.to_dict()
            log_dict['strategy_name'] = strategy.name
            log_dict['exchange_name'] = strategy.exchange_credential.exchange
            logs_data.append(log_dict)

        # ----- Add asset transfer logs -----
        transfer_rows = AssetTransferLog.query.filter(
            AssetTransferLog.user_id == current_user.id,
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
            src_desc = "Main Account" if row.strategy_id_from is None else (
                "This Strategy" if row.strategy_id_from == strategy_id else name_lookup.get(row.strategy_id_from, "(deleted)"))
            dst_desc = "Main Account" if row.strategy_id_to is None else (
                "This Strategy" if row.strategy_id_to == strategy_id else name_lookup.get(row.strategy_id_to, "(deleted)"))
            amount_str = _trim_decimal(row.amount)
            message = f"to {dst_desc} | {amount_str} {row.asset_symbol}"
            logs_data.append({
                'id': f"transfer-{row.id}",
                'timestamp': row.timestamp.isoformat(),
                'exchange_name': strategy.exchange_credential.exchange,
                'strategy_name': strategy.name,
                'account_name': src_desc,
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

        # Build a base query
        logs_query = WebhookLog.query
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
                    log_dict['exchange_name'] = log.strategy.exchange_credential.exchange
                elif log.automation and getattr(log.automation, 'exchange_credential', None):
                    log_dict['exchange_name'] = log.automation.exchange_credential.exchange
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

        # Build lookup maps for strategies involved in transfers
        involved_ids = {row.strategy_id_from for row in transfer_rows if row.strategy_id_from}
        involved_ids.update({row.strategy_id_to for row in transfer_rows if row.strategy_id_to})
        name_lookup = {}
        exch_lookup = {}
        if involved_ids:
            strats = TradingStrategy.query.filter(TradingStrategy.id.in_(involved_ids)).all()
            name_lookup = {s.id: s.name for s in strats}
            exch_lookup = {s.id: (s.exchange_credential.exchange if s.exchange_credential else None) for s in strats}

        for row in transfer_rows:
            # Skip main→main transfers where both strategy ids are null
            if row.strategy_id_from is None and row.strategy_id_to is None:
                continue
            src_desc = 'Main Account' if row.strategy_id_from is None else name_lookup.get(row.strategy_id_from, '(deleted)')
            dst_desc = 'Main Account' if row.strategy_id_to is None else name_lookup.get(row.strategy_id_to, '(deleted)')
            if search_term and search_term.lower() not in (src_desc + dst_desc + row.asset_symbol).lower():
                continue
            amount_str = _trim_decimal(row.amount)
            message = f"to {dst_desc} | {amount_str} {row.asset_symbol}"
            exch_val = None
            if row.strategy_id_from and exch_lookup.get(row.strategy_id_from):
                exch_val = exch_lookup[row.strategy_id_from]
            elif row.strategy_id_to and exch_lookup.get(row.strategy_id_to):
                exch_val = exch_lookup[row.strategy_id_to]

            logs_data.append({
                'id': f"transfer-{row.id}",
                'timestamp': row.timestamp.isoformat(),
                'exchange_name': exch_val,
                'strategy_name': src_desc,
                'account_name': src_desc,
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
            src_desc = describe_side(t.strategy_id_from, t.source_identifier)
            dst_desc = describe_side(t.strategy_id_to, t.destination_identifier)
            amount_str = _trim_decimal(t.amount)
            message = f"to {dst_desc} | {amount_str} {t.asset_symbol}"
            logs_data.append({
                'id': f"transfer-{t.id}",
                'timestamp': t.timestamp.isoformat(),
                'exchange_name': exchange_id,
                'strategy_name': src_desc,  # retain for compatibility
                'account_name': src_desc,
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