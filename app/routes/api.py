# app/routes/api.py
from flask import Blueprint, jsonify, request
from flask_security import current_user
from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload
import sys

from .. import db
from ..models import ExchangeCredentials, TradingStrategy, StrategyValueHistory, WebhookLog
from .automation import api_login_required
import logging

logger = logging.getLogger(__name__)

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

        logger.info(f"Total logs: {pagination.total}, Pages: {pagination.pages}, Current Page: {pagination.page}")

        # Convert logs to dictionaries using the model's to_dict method
        logs_data = []
        for log in pagination.items:
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
    except Exception as e:
        logger.error(f"Error fetching exchange logs: {e}")
        return jsonify({"error": "An internal error occurred"}), 500