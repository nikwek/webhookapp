# /tests/test_scripts/test_jwt.py
import pytest
from scripts.generate_jwt import main
import jwt
from datetime import datetime, timedelta

def test_jwt_key_generation(mock_project_root, monkeypatch, capsys):
    """Test that the JWT key generation creates a valid JWT secret."""
    # Mock input to decline .env update
    monkeypatch.setattr('builtins.input', lambda _: 'n')
    
    main()
    captured = capsys.readouterr()
    
    # Extract key from output
    key_line = [line for line in captured.out.split('\n') 
                if line.startswith('JWT_SECRET_KEY=')][0]
    key = key_line.split('=')[1]
    
    # Verify it's a valid JWT secret by creating and validating a token
    payload = {
        'sub': '1234567890',
        'name': 'Test User',
        'exp': datetime.utcnow() + timedelta(days=1)
    }
    
    # This will raise an error if the key is invalid
    token = jwt.encode(payload, key, algorithm='HS256')
    decoded = jwt.decode(token, key, algorithms=['HS256'])
    
    assert decoded['sub'] == payload['sub']
    assert decoded['name'] == payload['name']