import pytest
import json
from datetime import datetime
from app import db
from app.models.automation import Automation
from app.models.portfolio import Portfolio
from app.models.webhook import WebhookLog

@pytest.fixture
def automation(app, regular_user):
    """Fixture for creating a test automation with portfolio"""
    with app.app_context():
        portfolio = Portfolio(
            user_id=regular_user.id,
            name='Test Portfolio',
            exchange='coinbase'
        )
        db.session.add(portfolio)
        db.session.commit()

        automation = Automation(
            user_id=regular_user.id,
            portfolio_id=portfolio.id,
            name='Test Automation',
            automation_id='test-auto-id',
            trading_pair='BTC-USD',
            conditions={
                'indicator': 'price',
                'operator': '>',
                'value': 50000
            },
            actions={
                'type': 'notify',
                'message': 'Test alert'
            },
            is_active=True
        )
        db.session.add(automation)
        db.session.commit()
        return automation

def test_create_automation(auth_client, regular_user):
    portfolio = Portfolio(
        user_id=regular_user.id,
        name='Test Portfolio',
        exchange='coinbase'
    )
    db.session.add(portfolio)
    db.session.commit()

    response = auth_client.post('/create-automation', 
        json={
            'name': 'Test Automation',
            'portfolio_id': portfolio.id,
            'trading_pair': 'BTC-USD',
            'conditions': {
                'indicator': 'price',
                'operator': '>',
                'value': 50000
            },
            'actions': {
                'type': 'notify',
                'message': 'Price alert'
            }
        },
        content_type='application/json'
    )
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'automation_id' in data
    assert 'webhook_url' in data
    assert 'template' in data

def test_create_automation_unauthorized(client):
    response = client.post('/create-automation', 
        json={'name': 'Test Automation'}
    )
    assert response.status_code == 403

def test_update_automation_name(auth_client, automation):
    response = auth_client.post('/update_automation_name',
        json={
            'automation_id': automation.automation_id,
            'name': 'Updated Name'
        }
    )
    assert response.status_code == 200
    assert response.json['success'] is True
    
    db.session.refresh(automation)
    assert automation.name == 'Updated Name'

def test_update_automation_conditions(auth_client, automation):
    new_conditions = {
        'indicator': 'volume',
        'operator': '<',
        'value': 1000
    }
    
    response = auth_client.post('/update_automation',
        json={
            'automation_id': automation.automation_id,
            'conditions': new_conditions
        }
    )
    assert response.status_code == 200
    assert response.json['success'] is True
    
    db.session.refresh(automation)
    assert automation.conditions == new_conditions

def test_update_automation_actions(auth_client, automation):
    new_actions = {
        'type': 'notify',
        'message': 'Updated alert message'
    }
    
    response = auth_client.post('/update_automation',
        json={
            'automation_id': automation.automation_id,
            'actions': new_actions
        }
    )
    assert response.status_code == 200
    assert response.json['success'] is True
    
    db.session.refresh(automation)
    assert automation.actions == new_actions

def test_deactivate_automation(auth_client, automation):
    response = auth_client.post(f'/deactivate-automation/{automation.automation_id}')
    assert response.status_code == 200
    
    db.session.refresh(automation)
    assert not automation.is_active

def test_delete_automation(auth_client, automation):
    response = auth_client.post('/delete_automation',
        json={'automation_id': automation.automation_id}
    )
    assert response.status_code == 200
    assert response.json['success'] is True
    
    deleted = Automation.query.filter_by(automation_id=automation.automation_id).first()
    assert deleted is None

def test_delete_automation_unauthorized(client, automation):
    response = client.post('/delete_automation',
        json={'automation_id': automation.automation_id}
    )
    assert response.status_code == 403

def test_delete_nonexistent_automation(auth_client):
    response = auth_client.post('/delete_automation',
        json={'automation_id': 'nonexistent'}
    )
    assert response.status_code == 404

def test_update_automation_name_unauthorized(client, automation):
    response = client.post('/update_automation_name',
        json={
            'automation_id': automation.automation_id,
            'name': 'Updated Name'
        }
    )
    assert response.status_code == 403

def test_update_nonexistent_automation(auth_client):
    response = auth_client.post('/update_automation_name',
        json={
            'automation_id': 'nonexistent',
            'name': 'Updated Name'
        }
    )
    assert response.status_code == 404

def test_create_automation_missing_required_fields(auth_client):
    response = auth_client.post('/create-automation',
        json={},
        content_type='application/json'
    )
    assert response.status_code == 400
    assert 'error' in response.json

def test_create_automation_invalid_portfolio(auth_client):
    response = auth_client.post('/create-automation',
        json={
            'name': 'Test Automation',
            'portfolio_id': 999,
            'trading_pair': 'BTC-USD'
        },
        content_type='application/json'
    )
    assert response.status_code == 404

def test_create_automation_invalid_trading_pair(auth_client, regular_user):
    portfolio = Portfolio(
        user_id=regular_user.id,
        name='Test Portfolio',
        exchange='coinbase'
    )
    db.session.add(portfolio)
    db.session.commit()

    response = auth_client.post('/create-automation',
        json={
            'name': 'Test Automation',
            'portfolio_id': portfolio.id,
            'trading_pair': 'INVALID-PAIR'
        },
        content_type='application/json'
    )
    assert response.status_code == 400
    assert 'error' in response.json

def test_get_automation_details(auth_client, automation):
    response = auth_client.get(f'/automation/{automation.automation_id}')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['name'] == automation.name
    assert data['trading_pair'] == automation.trading_pair
    assert data['conditions'] == automation.conditions
    assert data['actions'] == automation.actions

def test_get_automation_history(auth_client, automation):
    # Create some webhook logs
    log1 = WebhookLog(
        automation_id=automation.id,
        payload={'test': 'data1'},
        timestamp=datetime.utcnow()
    )
    log2 = WebhookLog(
        automation_id=automation.id,
        payload={'test': 'data2'},
        timestamp=datetime.utcnow()
    )
    db.session.add_all([log1, log2])
    db.session.commit()

    response = auth_client.get(f'/automation/{automation.automation_id}/history')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert len(data['logs']) == 2
