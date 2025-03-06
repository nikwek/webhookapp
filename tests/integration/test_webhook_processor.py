import pytest
from app.models.automation import Automation
from app.models.webhook import WebhookLog
from app.services.webhook_processor import WebhookProcessor
from app import db

@pytest.fixture
def webhook_processor(app):
    with app.app_context():
        return WebhookProcessor()

@pytest.fixture
def test_automation(regular_user):
    automation = Automation(
        user_id=regular_user.id,
        automation_id='test-auto',
        name='Test Automation',
        trading_pair='BTC-USD',
        conditions={
            'indicator': 'price',
            'operator': '>',
            'value': 50000
        },
        actions={
            'type': 'notify',
            'message': 'Test alert'
        }
    )
    db.session.add(automation)
    db.session.commit()
    return automation

def test_process_webhook_valid_condition(webhook_processor, test_automation):
    payload = {
        'price': 51000,
        'trading_pair': 'BTC-USD'
    }
    
    result = webhook_processor.process(test_automation.automation_id, payload)
    assert result['success'] is True
    
    # Verify log was created
    log = WebhookLog.query.filter_by(automation_id=test_automation.id).first()
    assert log is not None
    assert log.action == 'notify'
    assert log.payload == payload

def test_process_webhook_invalid_condition(webhook_processor, test_automation):
    payload = {
        'price': 49000,
        'trading_pair': 'BTC-USD'
    }
    
    result = webhook_processor.process(test_automation.automation_id, payload)
    assert result['success'] is True
    assert result['triggered'] is False

def test_process_webhook_invalid_automation_id(webhook_processor):
    result = webhook_processor.process('invalid-id', {})
    assert result['success'] is False
    assert 'Automation not found' in result['error']

def test_process_webhook_missing_required_fields(webhook_processor, test_automation):
    payload = {'trading_pair': 'BTC-USD'}  # Missing price
    
    result = webhook_processor.process(test_automation.automation_id, payload)
    assert result['success'] is False
    assert 'Missing required fields' in result['error']

def test_process_webhook_invalid_trading_pair(webhook_processor, test_automation):
    payload = {
        'price': 51000,
        'trading_pair': 'ETH-USD'  # Different from automation trading pair
    }
    
    result = webhook_processor.process(test_automation.automation_id, payload)
    assert result['success'] is False
    assert 'Trading pair mismatch' in result['error']
