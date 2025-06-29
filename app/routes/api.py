# app/routes/api.py
from flask import Blueprint, current_app, jsonify, request
from flask_security import current_user
from sqlalchemy.orm import joinedload

from .. import db
from ..models import ExchangeCredentials, TradingStrategy, WebhookLog
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
        per_page = request.args.get('per_page', 20, type=int)

        strategy = (
            db.session.query(TradingStrategy)
            .join(ExchangeCredentials)
            .filter(
                TradingStrategy.id == strategy_id,
                ExchangeCredentials.user_id == current_user.id,
            )
            .options(joinedload(TradingStrategy.exchange_credential))
            .first_or_404()
        )

        pagination = WebhookLog.query.filter_by(
            strategy_id=strategy_id
        ).order_by(WebhookLog.timestamp.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        logs = pagination.items

        logs_data = []
        for log in logs:
            log_dict = log.to_dict()
            log_dict['strategy_name'] = strategy.name
            log_dict['exchange_name'] = strategy.exchange_credential.exchange
            logs_data.append(log_dict)

        return jsonify({
            'logs': logs_data,
            'pagination': {
                'page': pagination.page,
                'per_page': pagination.per_page,
                'total': pagination.total,
                'pages': pagination.pages,
            }
        })
    except Exception as e:
        logger.error(f"Error fetching strategy logs: {e}")
        return jsonify({"error": "An internal error occurred"}), 500


@api_bp.route('/api/exchange/<string:exchange_id>/logs', methods=['GET'])
@api_login_required
def get_exchange_logs(exchange_id: str):
    """Get webhook logs for all trading strategies on an exchange with pagination."""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)

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
        
        # Now get logs for all these strategies
        logs_query = WebhookLog.query.filter(
            WebhookLog.strategy_id.in_(strategy_ids)
        ).order_by(WebhookLog.timestamp.desc())
        
        # Get paginated results
        pagination = logs_query.paginate(
            page=page, per_page=per_page, error_out=False
        )
        logs = pagination.items
        
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
            # Add strategy name if available
            if log.strategy_id and log.strategy_id in strategy_map:
                log_dict['strategy_name'] = strategy_map[log.strategy_id]['name']
                log_dict['exchange_name'] = exchange_id
            logs_data.append(log_dict)

        return jsonify({
            'logs': logs_data,
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
