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
    try:
        client = oauth.create_client('coinbase')
        redirect_uri = url_for('oauth.exchange_callback', _external=True)
        current_app.logger.debug(f"Starting OAuth flow with redirect URI: {redirect_uri}")
        return client.authorize_redirect(redirect_uri)
    except Exception as e:
        current_app.logger.error(f"OAuth authorize error: {str(e)}")
        flash('Failed to initiate Coinbase connection.', 'danger')
        return redirect(url_for('dashboard.settings'))

@bp.route('/connect/exchange/callback')
@login_required
def exchange_callback():
    """Handle OAuth callback from Coinbase"""
    try:
        client = oauth.create_client('coinbase')
        current_app.logger.debug("Processing OAuth callback")
        token = client.authorize_access_token()
        current_app.logger.debug(f"Received token response: {token}")
        
        # Save the credentials
        credentials = save_oauth_credentials(
            db=db,
            user_id=current_user.id,
            provider='coinbase',
            token_response=token
        )
        current_app.logger.debug(f"Saved credentials for user {current_user.id}")
        
        flash('Successfully connected to Coinbase!', 'success')
        return redirect(url_for('dashboard.settings'))
        
    except Exception as e:
        current_app.logger.error(f"OAuth callback error: {str(e)}")
        flash('Failed to connect to Coinbase. Please try again.', 'danger')
        return redirect(url_for('dashboard.settings'))
    