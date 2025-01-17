import json
from app import db
from app.models.automation import Automation

def test_create_automation(auth_client, regular_user):
    response = auth_client.post('/create-automation', 
        json={'name': 'Test Automation'},
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
    assert response.json['success'] == True
    
    db.session.refresh(automation)
    assert automation.name == 'Updated Name'

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
    assert response.json['success'] == True
    
    # Verify automation was deleted
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

def test_create_automation_missing_name(auth_client):
    response = auth_client.post('/create-automation',
        json={},  # Missing name field
        content_type='application/json'
    )
    assert response.status_code == 400
    assert 'error' in response.json
    assert 'name' in response.json['error']

def test_create_automation_empty_name(auth_client):
    response = auth_client.post('/create-automation',
        json={'name': ''},  # Empty name
        content_type='application/json'
    )
    assert response.status_code == 400
    assert 'error' in response.json

def test_create_automation_invalid_json(auth_client):
    response = auth_client.post('/create-automation',
        data='not json',  # Invalid JSON
        content_type='application/json'
    )
    assert response.status_code == 400
    assert 'error' in response.json 