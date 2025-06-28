# app/routes/api.py
from flask import Blueprint, current_app, jsonify, request
from flask_security import current_user
from sqlalchemy.orm import joinedload

from .. import db
from ..models import ExchangeCredentials, TradingStrategy, WebhookLog
from .automation import api_login_required

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
        current_app.logger.error(f"Error fetching strategy logs: {e}")
        return jsonify({"error": "An internal error occurred"}), 500
