from datetime import datetime
import json
from app import db
from app.models.webhook import WebhookLog

def test_webhook_creation(client, automation):
    payload = {
        "ticker": "AAPL",
        "action": "buy",
        "timestamp": datetime.now().isoformat()
    }
    
    response = client.post(
        f'/webhook?automation_id={automation.automation_id}',
        json=payload
    )
    assert response.status_code == 200
    assert response.json['success'] == True

    # Verify the webhook was logged
    log = WebhookLog.query.filter_by(automation_id=automation.automation_id).first()
    assert log is not None
    assert log.payload['ticker'] == 'AAPL'
    
    # Verify last_run was updated
    db.session.refresh(automation)
    assert automation.last_run is not None

def test_webhook_invalid_automation(client):
    response = client.post('/webhook?automation_id=invalid', json={})
    assert response.status_code == 404

def test_webhook_missing_automation_id(client):
    response = client.post('/webhook', json={})
    assert response.status_code == 400

def test_webhook_inactive_automation(client, automation):
    automation.is_active = False
    db.session.commit()
    
    payload = {"action": "test"}
    response = client.post(
        f'/webhook?automation_id={automation.automation_id}',
        json=payload
    )
    assert response.status_code == 403

def test_webhook_invalid_json(client, automation):
    response = client.post(
        f'/webhook?automation_id={automation.automation_id}',
        data='invalid json',
        content_type='application/json'
    )
    assert response.status_code == 400

def test_webhook_multiple_logs(client, automation):
    # Send multiple webhooks and verify they're all logged
    payloads = [
        {"ticker": "AAPL", "action": "buy"},
        {"ticker": "GOOGL", "action": "sell"},
        {"ticker": "MSFT", "action": "buy"}
    ]
    
    for payload in payloads:
        response = client.post(
            f'/webhook?automation_id={automation.automation_id}',
            json=payload
        )
        assert response.status_code == 200
    
    logs = WebhookLog.query.filter_by(automation_id=automation.automation_id).all()
    assert len(logs) == 3 