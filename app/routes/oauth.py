# app/routes/oauth.py
from flask import Blueprint, current_app, url_for, redirect, flash
from flask_login import current_user, login_required
from app.services.oauth_service import oauth, save_oauth_credentials
from app import db

bp = Blueprint('oauth', __name__)

@bp.route('/connect/exchange/authorize')
@login_required
def exchange_authorize():
    """Initiate OAuth flow with Coinbase"""
    client = oauth.create_client('coinbase')
    redirect_uri = current_app.config['OAUTH_REDIRECT_URI']
    return client.authorize_redirect(redirect_uri)

@bp.route('/connect/exchange/callback')
@login_required
def exchange_callback():
    """Handle OAuth callback from Coinbase"""
    try:
        client = oauth.create_client('coinbase')
        token = client.authorize_access_token()
        
        # Save the credentials
        save_oauth_credentials(
            db=db,
            user_id=current_user.id,
            provider='coinbase',
            token_response=token
        )
        
        flash('Successfully connected to Coinbase!', 'success')
        return redirect(url_for('dashboard.settings'))
        
    except Exception as e:
        current_app.logger.error(f"OAuth callback error: {str(e)}")
        flash('Failed to connect to Coinbase. Please try again.', 'error')
        return redirect(url_for('dashboard.settings'))

@bp.route('/connect/exchange/disconnect', methods=['POST'])
@login_required
def exchange_disconnect():
    """Disconnect Coinbase integration"""
    from app.models.oauth_credentials import OAuthCredentials
    try:
        # Remove OAuth credentials
        creds = OAuthCredentials.query.filter_by(
            user_id=current_user.id,
            provider='coinbase'
        ).first()
        
        if creds:
            db.session.delete(creds)
            db.session.commit()
            flash('Successfully disconnected from Coinbase.', 'success')
        else:
            flash('No Coinbase connection found.', 'info')
            
    except Exception as e:
        current_app.logger.error(f"Error disconnecting Coinbase: {str(e)}")
        flash('Error disconnecting from Coinbase.', 'error')
        
    return redirect(url_for('dashboard.settings'))
