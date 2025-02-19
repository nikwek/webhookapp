from flask import current_app
import requests
from app.services.oauth_service import get_oauth_credentials, refresh_access_token
from app import db

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
                self._credentials = refresh_access_token(db, self._credentials)
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
    try:
        response = requests.get(
            f'{self.base_url}/accounts',
            headers=self._get_headers()
        )
        response.raise_for_status()
        
        # Debug output
        print("Coinbase API Response:", response.status_code)
        print("Response Headers:", response.headers)
        print("Response Body:", response.text[:500])  # First 500 chars
        
        accounts = response.json().get('data', [])
        
        # Debug output
        print("Parsed Accounts:", len(accounts))
        if accounts:
            print("First Account Sample:", accounts[0])
        
        portfolios = []
        for account in accounts:
            portfolios.append({
                'id': account['id'],
                'name': account['name'],
                'balance': {
                    'amount': account['balance']['amount'],
                    'currency': account['balance']['currency']
                },
                'type': account['type'],
                'primary': account.get('primary', False)
            })
        
        print("Processed Portfolios:", len(portfolios))
        return portfolios
        
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Error fetching Coinbase portfolios: {str(e)}")
        return []  # Return empty list instead of raising

    def get_portfolio_api_credentials(self, portfolio_id):
        """Fetch API credentials for a specific portfolio"""
        try:
            response = requests.post(
                f'{self.base_url}/accounts/{portfolio_id}/api_keys',
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json().get('data', {})
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"Error creating API credentials: {str(e)}")
            raise

    def create_portfolio(self, name):
        """Create a new portfolio"""
        try:
            response = requests.post(
                f'{self.base_url}/accounts',
                headers=self._get_headers(),
                json={
                    'name': name,
                    'type': 'trading'  # Set type to trading for new portfolios
                }
            )
            response.raise_for_status()
            return response.json().get('data', {})
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"Error creating portfolio: {str(e)}")
            raise