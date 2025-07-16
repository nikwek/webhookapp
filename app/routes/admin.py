# app/routes/admin.py
from flask import Blueprint, jsonify, render_template, redirect, url_for, request, current_app
from app.models.user import User
from app.models.automation import Automation  # Legacy
from app.models.trading import TradingStrategy, AssetTransferLog
from app.models.exchange_credentials import ExchangeCredentials
from app.models.webhook import WebhookLog
from sqlalchemy import func
from app import db
from flask_security import roles_required, current_user

bp = Blueprint('admin', __name__, url_prefix='/admin')

# Role check helper
def get_user_roles():
    return [role.name for role in current_user.roles]

@bp.route('/')
@roles_required('admin') 
def index():
    return redirect(url_for('admin.users'))


@bp.route('/users')
@roles_required('admin')
def users():
    search = request.args.get('search', '')
    
    # Query users with strategy count
    query = db.session.query(User, func.count(TradingStrategy.id).label('strategy_count'))\
        .outerjoin(TradingStrategy, User.id == TradingStrategy.user_id)\
        .group_by(User.id)
    
    if search:
        query = query.filter(User.email.ilike(f'%{search}%'))
    
    # Returns tuple of (user, automation_count)
    results = query.all()
    
    # Transform results for template
    users = []
    for user, count in results:
        user.strategy_count = count
        users.append(user)
    
    return render_template('admin/users.html', users=users)





@bp.route('/settings')
@roles_required('admin') 
def settings():
    return render_template('admin/settings.html')

# API endpoints for user management
@bp.route('/api/user/<int:user_id>/reset', methods=['POST'])
@roles_required('admin') 
def reset_user(user_id):
    try:
        user = User.query.get_or_404(user_id)

        # 1. Delete all trading strategies and their related logs for this user
        strategy_ids = [s.id for s in user.trading_strategies]
        if strategy_ids:
            # Delete webhook logs tied to these strategies
            WebhookLog.query.filter(WebhookLog.strategy_id.in_(strategy_ids)).delete(synchronize_session=False)
            # Delete asset transfer logs where these strategies were involved
            AssetTransferLog.query.filter(
                (AssetTransferLog.strategy_id_from.in_(strategy_ids)) |
                (AssetTransferLog.strategy_id_to.in_(strategy_ids))
            ).delete(synchronize_session=False)
            # Delete the strategies themselves
            TradingStrategy.query.filter(TradingStrategy.id.in_(strategy_ids)).delete(synchronize_session=False)

        # 2. (Legacy) Clear automation logs for backward-compat users
        automation_ids = [a.automation_id for a in getattr(user, 'automations', [])]
        if automation_ids:
            WebhookLog.query.filter(WebhookLog.automation_id.in_(automation_ids)).delete(synchronize_session=False)
            Automation.query.filter(Automation.automation_id.in_(automation_ids)).delete(synchronize_session=False)

        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@bp.route('/api/user/<int:user_id>/suspend', methods=['POST'])
@roles_required('admin') 
def suspend_user(user_id):
    try:
        user = User.query.get_or_404(user_id)
        user.is_suspended = not user.is_suspended
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@bp.route('/api/user/<int:user_id>/delete', methods=['POST'])
@roles_required('admin')
def delete_user(user_id):
    try:
        user = User.query.get_or_404(user_id)
        
        # Get automation IDs directly from the Automation table
        automations = Automation.query.filter_by(user_id=user.id).all()
        automation_ids = [a.automation_id for a in automations]
        
        # 1. Delete webhook logs first
        if automation_ids:
            WebhookLog.query.filter(WebhookLog.automation_id.in_(automation_ids)).delete(synchronize_session='fetch')
        
        # 2. Delete account caches
        from app.models.account_cache import AccountCache
        AccountCache.query.filter_by(user_id=user.id).delete()
        
        # 3. Delete exchange credentials (before portfolios and automations to avoid FK constraint issues)
        ExchangeCredentials.query.filter_by(user_id=user.id).delete()
        
        # 4. Delete trading strategies and their related data for this user (if any)
        strategy_ids = [s.id for s in user.trading_strategies]
        if strategy_ids:
            # Delete webhook logs tied to these strategies
            WebhookLog.query.filter(WebhookLog.strategy_id.in_(strategy_ids)).delete(synchronize_session=False)
            # Delete asset transfer logs involving these strategies
            AssetTransferLog.query.filter((AssetTransferLog.strategy_id_from.in_(strategy_ids)) | (AssetTransferLog.strategy_id_to.in_(strategy_ids))).delete(synchronize_session=False)
            # Delete the strategies themselves
            TradingStrategy.query.filter(TradingStrategy.id.in_(strategy_ids)).delete(synchronize_session=False)
 
        # 5. Delete user's automations (legacy – safe to attempt even if none)
        Automation.query.filter_by(user_id=user.id).delete(synchronize_session=False)
 
        # 6. Delete user's portfolios (if the relationship exists)
        if hasattr(user, 'portfolios'):
            for portfolio in user.portfolios:
                db.session.delete(portfolio)
 
        # 7. Clear the user's roles
        user.roles = []
 
        # 8. Finally delete the user
        db.session.delete(user)
        db.session.commit()
        
        current_app.logger.info(f"User {user_id} deleted successfully")
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting user: {str(e)}")
        return jsonify({"error": str(e)}), 500


# -------------------------------------------------------------------------
# New Admin Pages & APIs for Exchanges and Trading Strategies
# -------------------------------------------------------------------------

@bp.route('/exchanges')
@roles_required('admin')
def exchanges():
    """Admin page listing all exchange credentials across users."""
    search = request.args.get('search', '')

    # Aggregate strategy counts per credential
    query = (
        db.session.query(
            ExchangeCredentials,
            User,
            func.count(TradingStrategy.id).label('strategy_count')
        )
        .join(User, ExchangeCredentials.user_id == User.id)
        .outerjoin(TradingStrategy, ExchangeCredentials.id == TradingStrategy.exchange_credential_id)
        .group_by(ExchangeCredentials.id, User.id)
    )

    if search:
        ilike = f"%{search}%"
        query = query.filter(
            db.or_(
                User.email.ilike(ilike),
                ExchangeCredentials.exchange.ilike(ilike)
            )
        )

    results = query.all()
    rows = []
    for cred, user, strategy_count in results:
        rows.append({
            'credential': cred,
            'user': user,
            'strategy_count': strategy_count
        })

    return render_template('admin/exchanges.html', rows=rows)


@bp.route('/strategies')
@roles_required('admin')
def strategies():
    """Admin page listing all trading strategies across users."""
    search = request.args.get('search', '')

    query = (
        db.session.query(TradingStrategy, User, ExchangeCredentials)
        .join(User, TradingStrategy.user_id == User.id)
        .join(ExchangeCredentials, TradingStrategy.exchange_credential_id == ExchangeCredentials.id)
    )

    if search:
        ilike = f"%{search}%"
        query = query.filter(
            db.or_(
                User.email.ilike(ilike),
                TradingStrategy.name.ilike(ilike),
                ExchangeCredentials.exchange.ilike(ilike)
            )
        )

    results = query.all()
    rows = []
    for strategy, user, cred in results:
        rows.append({'strategy': strategy, 'user': user, 'credential': cred})

    return render_template('admin/strategies.html', rows=rows)

# --------------------  API ENDPOINTS  ------------------------------------

@bp.route('/api/exchange/<int:cred_id>/delete_keys', methods=['POST'])
@roles_required('admin')
def delete_api_keys_admin(cred_id: int):
    try:
        cred = ExchangeCredentials.query.get_or_404(cred_id)
        db.session.delete(cred)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@bp.route('/api/strategy/<int:strategy_id>/toggle', methods=['POST'])
@roles_required('admin')
def toggle_strategy_admin(strategy_id: int):
    try:
        strategy = TradingStrategy.query.get_or_404(strategy_id)
        strategy.is_active = not strategy.is_active
        db.session.commit()
        return jsonify({"success": True, "is_active": strategy.is_active})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


@bp.route('/api/strategy/<int:strategy_id>/delete', methods=['POST'])
@roles_required('admin')
def delete_strategy_admin(strategy_id: int):
    try:
        strategy = TradingStrategy.query.get_or_404(strategy_id)
        # Delete related logs and transfers first
        WebhookLog.query.filter_by(strategy_id=strategy.id).delete(synchronize_session=False)
        AssetTransferLog.query.filter(
            (AssetTransferLog.strategy_id_from == strategy.id) | (AssetTransferLog.strategy_id_to == strategy.id)
        ).delete(synchronize_session=False)
        db.session.delete(strategy)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500








    
