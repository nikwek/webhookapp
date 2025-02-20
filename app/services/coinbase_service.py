from flask import current_app
import requests
from app.services.oauth_service import get_oauth_credentials, refresh_access_token
from app import db

class CoinbaseService:
    def __init__(self, user_id):
        self.user_id = user_id
        self.base_url = 'https://api.coinbase.com/api/v3'
        self._credentials = None

    @property
    def credentials(self):
        """Get and refresh OAuth credentials if needed"""
        if not self._credentials:
            self._credentials = get_oauth_credentials(self.user_id, 'coinbase')
            if self._credentials and self._credentials.is_expired():
                self._credentials = refresh_access_token(db, self._credentials)
        return self._credentials

    def _get_headers(self):
        """Get headers for API requests"""
        if not self.credentials:
            raise ValueError("No credentials available")
        return {
            'Authorization': f'Bearer {self.credentials.access_token}',
            'Accept': 'application/json'
        }

    def list_portfolios(self):
        """Fetch all portfolios and their balances for the user"""
        try:
            # First get the list of portfolios
            response = requests.get(
                f'{self.base_url}/brokerage/portfolios',
                headers=self._get_headers()
            )
            response.raise_for_status()
            
            data = response.json()
            portfolios = data.get('portfolios', [])
            
            processed_portfolios = []
            for portfolio in portfolios:
                if portfolio.get('deleted', False):
                    continue
                
                try:
                    # Get detailed breakdown for each portfolio
                    breakdown_response = requests.get(
                        f'{self.base_url}/brokerage/portfolios/{portfolio["uuid"]}',
                        headers=self._get_headers()
                    )
                    breakdown_response.raise_for_status()
                    breakdown_data = breakdown_response.json().get('breakdown', {})
                    
                    # Get portfolio balances
                    portfolio_balances = breakdown_data.get('portfolio_balances', {})
                    total_balance = portfolio_balances.get('total_balance', {})
                    
                    processed_portfolios.append({
                        'id': portfolio['uuid'],
                        'name': portfolio['name'],
                        'type': portfolio['type'],
                        'balance': {
                            'amount': float(total_balance.get('value', '0')),
                            'currency': total_balance.get('currency', 'USD')
                        },
                        'has_api_keys': True  # We have access through OAuth
                    })
                except Exception as e:
                    current_app.logger.error(f"Error fetching breakdown for portfolio {portfolio['uuid']}: {str(e)}")
                    processed_portfolios.append({
                        'id': portfolio['uuid'],
                        'name': portfolio['name'],
                        'type': portfolio['type'],
                        'balance': {
                            'amount': 0,
                            'currency': 'USD'
                        },
                        'has_api_keys': True
                    })
            
            current_app.logger.debug(f"Processed Portfolios with balances: {processed_portfolios}")
            return processed_portfolios
            
        except Exception as e:
            current_app.logger.error(f"Error fetching portfolios: {str(e)}")
            return []

    def create_portfolio(self, name):
        """Create a new portfolio"""
        try:
            response = requests.post(
                f'{self.base_url}/brokerage/portfolios',
                headers=self._get_headers(),
                json={'name': name}
            )
            response.raise_for_status()
            
            data = response.json()
            portfolio = data.get('portfolio')
            
            if portfolio:
                return {
                    'id': portfolio['uuid'],
                    'name': portfolio['name'],
                    'type': portfolio['type']
                }
            return None
            
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"Error creating portfolio: {str(e)}")
            raise

    def get_portfolio_breakdown(self, portfolio_id):
        """Get detailed breakdown of a portfolio"""
        try:
            response = requests.get(
                f'{self.base_url}/brokerage/portfolios/{portfolio_id}',
                headers=self._get_headers()
            )
            response.raise_for_status()
            
            data = response.json()
            return data.get('breakdown')
            
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"Error fetching portfolio breakdown: {str(e)}")
            return None