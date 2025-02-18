from flask import current_app
import requests
from app.services.oauth_service import get_oauth_credentials, refresh_access_token

class CoinbaseService:
    def __init__(self, user_id):
        self.user_id = user_id
        self.base_url = 'https://api.coinbase.com/v2'
        self._credentials = None

    @property
    def credentials(self):
        if not self._credentials:
            self._credentials = get_oauth_credentials(self.user_id, 'coinbase')
            if self._credentials and self._credentials.is_expired():
                self._credentials = refresh_access_token(self._credentials)
        return self._credentials

    def _get_headers(self):
        if not self.credentials:
            raise ValueError("No Coinbase credentials found")
        return {
            'Authorization': f'Bearer {self.credentials.access_token}',
            'Accept': 'application/json'
        }

    def list_portfolios(self):
        """Fetch all portfolios for the user"""
        response = requests.get(
            f'{self.base_url}/accounts',
            headers=self._get_headers()
        )
        response.raise_for_status()
        
        accounts = response.json().get('data', [])
        # Filter for portfolio accounts only
        portfolios = [
            account for account in accounts 
            if account['type'] == 'portfolio'  # Adjust this condition based on Coinbase's actual API response
        ]
        return portfolios

    def get_portfolio_api_credentials(self, portfolio_id):
        """Fetch API credentials for a specific portfolio"""
        response = requests.post(
            f'{self.base_url}/accounts/{portfolio_id}/api_keys',
            headers=self._get_headers()
        )
        response.raise_for_status()
        return response.json().get('data', {})

    def create_portfolio(self, name):
        """Create a new portfolio"""
        response = requests.post(
            f'{self.base_url}/accounts',
            headers=self._get_headers(),
            json={
                'name': name,
                'type': 'portfolio'
            }
        )
        response.raise_for_status()
        return response.json().get('data', {})