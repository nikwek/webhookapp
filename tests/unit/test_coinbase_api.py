import pytest
import json
from unittest.mock import patch, MagicMock
from app.models.portfolio import Portfolio
from app import db
from app.models.exchange_credentials import ExchangeCredentials

def test_get_portfolios_with_mocked_db(auth_client, monkeypatch):
    """Test with mocked database query"""
    # Create mock portfolio objects
    mock_portfolios = [
        MagicMock(id=1, name="Portfolio 1", exchange="coinbase", user_id=1, portfolio_id="port1"),
        MagicMock(id=2, name="Portfolio 2", exchange="coinbase", user_id=1, portfolio_id="port2")
    ]
    
    # Mock the database query
    mock_query = MagicMock()
    mock_query.filter_by.return_value.all.return_value = mock_portfolios
    
    # Mock the Portfolio query
    with patch('app.models.portfolio.Portfolio.query', mock_query):
        # Mock ExchangeCredentials lookup
        mock_creds_query = MagicMock()
        mock_creds_query.filter_by.return_value.first.return_value = True
        
        with patch('app.models.exchange_credentials.ExchangeCredentials.query', mock_creds_query):
            # Mock the get_portfolio_value method
            with patch('app.services.account_service.AccountService.get_portfolio_value', 
                    return_value=10000.0):
                
                # Make request
                response = auth_client.get('/api/coinbase/portfolios')
                
                # Verify response
                assert response.status_code == 200
                data = json.loads(response.data)
                
                # Print for debugging
                print(f"Response data: {data}")
                
                assert 'has_credentials' in data
                assert 'portfolios' in data
                assert len(data['portfolios']) == 2
                assert data['portfolios'][0]['name'] == "Portfolio 1"
                assert data['portfolios'][1]['name'] == "Portfolio 2"