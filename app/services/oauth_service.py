# app/services/oauth_service.py
from datetime import datetime, timedelta
from flask import current_app
from authlib.integrations.flask_client import OAuth
from sqlalchemy.orm import relationship

oauth = OAuth()

def init_oauth(app, db):
    oauth.init_app(app)
    
    oauth.register(
        name='coinbase',
        client_id=app.config['COINBASE_CLIENT_ID'],
        client_secret=app.config['COINBASE_CLIENT_SECRET'],
        access_token_url='https://login.coinbase.com/oauth2/token',
        access_token_params=None,
        authorize_url='https://login.coinbase.com/oauth2/auth',
        authorize_params=None,
        api_base_url='https://api.coinbase.com/v3/',
        client_kwargs={
            'scope': 'wallet:accounts:read wallet:accounts:create wallet:user:read'
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

    credentials.access_token = token_response['access_token']
    credentials.refresh_token = token_response.get('refresh_token')
    
    if 'expires_in' in token_response:
        credentials.expires_at = datetime.utcnow() + timedelta(seconds=token_response['expires_in'])
    
    credentials.scope = token_response.get('scope')
    db.session.commit()
    
    return credentials

def get_oauth_credentials(user_id, provider):
    """Get OAuth credentials for a user"""
    from app.models.oauth_credentials import OAuthCredentials
    return OAuthCredentials.query.filter_by(
        user_id=user_id,
        provider=provider
    ).first()

def refresh_access_token(db, credentials):
    """Refresh the access token if it's expired"""
    current_app.logger.debug(f"Checking token expiration for user {credentials.user_id}")
    if not credentials.is_expired():
        return credentials

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
    db.session.commit()

    return credentials