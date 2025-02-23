# app/services/oauth_service.py
from datetime import datetime, timedelta
from flask import current_app
from authlib.integrations.flask_client import OAuth
from sqlalchemy.orm import relationship
import logging

oauth = OAuth()

def init_oauth(app, db):
    oauth.init_app(app)
    
    oauth.register(
        name='coinbase',
        client_id=app.config['COINBASE_CLIENT_ID'],
        client_secret=app.config['COINBASE_CLIENT_SECRET'],
        access_token_url='https://login.coinbase.com/oauth2/token',
        authorize_url='https://login.coinbase.com/oauth2/auth',
        api_base_url='https://api.coinbase.com/api/v3/',
        client_kwargs={
            'scope': 'wallet:accounts:read wallet:trades:read wallet:trades:create offline_access',
            'response_type': 'code'
        }
    )

def save_oauth_credentials(db, user_id, provider, token_response):
    """Save or update OAuth credentials for a user"""
    from app.models.oauth_credentials import OAuthCredentials
    
    credentials = OAuthCredentials.query.filter_by(
        user_id=user_id,
        provider=provider
    ).first()

    if not credentials:
        credentials = OAuthCredentials(
            user_id=user_id,
            provider=provider
        )
        db.session.add(credentials)

    try:
        credentials.access_token = token_response['access_token']
        credentials.refresh_token = token_response.get('refresh_token')
        
        if 'expires_in' in token_response:
            credentials.expires_at = datetime.utcnow() + timedelta(seconds=token_response['expires_in'])
        
        credentials.scope = token_response.get('scope')
        credentials.is_valid = True
        credentials.refresh_error = None
        db.session.commit()
        
        current_app.logger.info(f"Successfully saved OAuth credentials for user {user_id}")
        return credentials
    except Exception as e:
        current_app.logger.error(f"Error saving OAuth credentials for user {user_id}: {str(e)}")
        db.session.rollback()
        raise

def get_oauth_credentials(user_id, provider):
    """Get OAuth credentials for a user and refresh if needed"""
    from app.models.oauth_credentials import OAuthCredentials
    credentials = OAuthCredentials.query.filter_by(
        user_id=user_id,
        provider=provider
    ).first()
    
    if credentials and credentials.needs_refresh():
        try:
            credentials = refresh_access_token(db, credentials)
        except Exception as e:
            current_app.logger.error(f"Failed to refresh token for user {user_id}: {str(e)}")
            # Don't raise the error - return the credentials even if refresh failed
            # The caller can check credentials.is_valid
    
    return credentials

def refresh_access_token(db, credentials):
    """Refresh the access token if needed"""
    current_app.logger.debug(f"Attempting to refresh token for user {credentials.user_id}")
    
    try:
        if not credentials.refresh_token:
            raise ValueError("No refresh token available")

        client = oauth.create_client('coinbase')
        token_response = client.fetch_token(
            url='https://login.coinbase.com/oauth2/token',
            grant_type='refresh_token',
            refresh_token=credentials.refresh_token
        )

        # Update the credentials with the new token information
        credentials.access_token = token_response['access_token']
        credentials.refresh_token = token_response.get('refresh_token', credentials.refresh_token)

        if 'expires_in' in token_response:
            credentials.expires_at = datetime.utcnow() + timedelta(seconds=token_response['expires_in'])

        credentials.scope = token_response.get('scope', credentials.scope)
        credentials.is_valid = True
        credentials.refresh_error = None
        credentials.mark_refresh_attempt()
        db.session.commit()

        current_app.logger.info(f"Successfully refreshed token for user {credentials.user_id}")
        return credentials

    except Exception as e:
        error_msg = str(e)
        current_app.logger.error(f"Failed to refresh token for user {credentials.user_id}: {error_msg}")
        credentials.mark_refresh_attempt(error_msg)
        db.session.commit()
        raise

def check_oauth_status(user_id, provider='coinbase'):
    """Check OAuth status and return detailed information"""
    credentials = get_oauth_credentials(user_id, provider)
    if not credentials:
        return {
            'status': 'disconnected',
            'message': 'No OAuth connection found'
        }
    
    if not credentials.is_valid:
        return {
            'status': 'invalid',
            'message': f'OAuth connection invalid: {credentials.refresh_error}',
            'last_attempt': credentials.last_refresh_attempt
        }
    
    if credentials.is_expired():
        return {
            'status': 'expired',
            'message': 'OAuth token expired',
            'expires_at': credentials.expires_at
        }
    
    return {
        'status': 'connected',
        'message': 'OAuth connection active',
        'expires_at': credentials.expires_at
    }

# Add this to app/services/oauth_service.py
def get_connection_status(user_id, provider='coinbase'):
    """Get detailed OAuth connection status for UI display"""
    credentials = get_oauth_credentials(user_id, provider)
    
    if not credentials:
        return {
            'status': 'disconnected',
            'message': 'Not connected to Coinbase',
            'css_class': 'danger',
            'icon': 'fa-times-circle',
            'is_connected': False
        }
    
    if not credentials.is_valid:
        return {
            'status': 'error',
            'message': f'Connection error: {credentials.refresh_error}',
            'css_class': 'danger',
            'icon': 'fa-exclamation-circle',
            'is_connected': False,
            'last_attempt': credentials.last_refresh_attempt
        }
    
    if credentials.is_expired():
        return {
            'status': 'expired',
            'message': 'Connection expired',
            'css_class': 'warning',
            'icon': 'fa-clock',
            'is_connected': False,
            'expires_at': credentials.expires_at
        }
    
    # Calculate days until expiration
    if credentials.expires_at:
        from datetime import datetime
        days_left = (credentials.expires_at - datetime.utcnow()).days
        expires_text = f"Expires in {days_left} days" if days_left > 0 else "Expires soon"
    else:
        expires_text = "No expiration set"
    
    return {
        'status': 'connected',
        'message': f'Connected to Coinbase ({expires_text})',
        'css_class': 'success',
        'icon': 'fa-check-circle',
        'is_connected': True,
        'expires_at': credentials.expires_at
    }
