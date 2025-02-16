# /tests/test_scripts/test_encryption_key.py
import pytest
from scripts.generate_encryption_key import main
from cryptography.fernet import Fernet

def test_encryption_key_generation(mock_project_root, monkeypatch, capsys):
    """Test that the encryption key generation creates a valid Fernet key."""
    # Mock input to decline .env update
    monkeypatch.setattr('builtins.input', lambda _: 'n')
    
    main()
    captured = capsys.readouterr()
    
    # Extract key from output
    key_line = [line for line in captured.out.split('\n') 
                if line.startswith('ENCRYPTION_KEY=')][0]
    key = key_line.split('=')[1]
    
    # Verify it's a valid Fernet key
    assert len(key) > 0
    fernet = Fernet(key.encode())
    test_data = b"test message"
    # This will raise an error if the key is invalid
    encrypted = fernet.encrypt(test_data)
    decrypted = fernet.decrypt(encrypted)
    assert decrypted == test_data