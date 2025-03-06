import pytest
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from app.models.portfolio import Portfolio
from app.models.exchange_credentials import ExchangeCredentials

def test_dashboard_redirect_for_admin(admin_client):
    response = admin_client.get('/dashboard', follow_redirects=True)
    assert response.status_code == 200
    assert request.path == '/admin/users'

def test_dashboard_view(auth_client, regular_user):
    response = auth_client.get('/dashboard')
    assert response.status_code == 200
    assert b'Webhook Logs' in response.data
    assert b'Automations' in response.data

def test_get_logs(auth_client, regular_user):
    # Create test automation
    automation = Automation(
        user_id=regular_user.id,
        automation_id='test-auto',
        name='Test Automation'
    )
    db.session.add(automation)
    
    # Create test logs
    log = WebhookLog(
        automation_id=automation.id,
        payload={'test': 'data'},
        action='test'
    )
    db.session.add(log)
    db.session.commit()
    
    response = auth_client.get('/api/logs')
    assert response.status_code == 200
    data = response.get_json()
    assert len(data) == 1
    assert data[0]['automation_name'] == 'Test Automation'

def test_clear_logs(auth_client, regular_user):
    # Setup test data similar to test_get_logs
    automation = Automation(
        user_id=regular_user.id,
        automation_id='test-auto',
        name='Test Automation'
    )
    db.session.add(automation)
    
    log = WebhookLog(
        automation_id=automation.id,
        payload={'test': 'data'},
        action='test'
    )
    db.session.add(log)
    db.session.commit()
    
    response = auth_client.post('/clear-logs')
    assert response.status_code == 200
    
    # Verify logs are cleared
    logs = WebhookLog.query.all()
    assert len(logs) == 0

def test_get_coinbase_portfolios(auth_client, regular_user):
    # Create test portfolio
    portfolio = Portfolio(
        user_id=regular_user.id,
        name='Test Portfolio',
        exchange='coinbase'
    )
    db.session.add(portfolio)
    
    # Add credentials
    creds = ExchangeCredentials(
        user_id=regular_user.id,
        portfolio_id=portfolio.id,
        exchange='coinbase',
        api_key='test_key',
        api_secret='test_secret'
    )
    db.session.add(creds)
    db.session.commit()
    
    response = auth_client.get('/api/coinbase/portfolios')
    assert response.status_code == 200
    data = response.get_json()
    assert data['has_credentials'] is True
    assert len(data['portfolios']) == 1
    assert data['portfolios'][0]['name'] == 'Test Portfolio'
