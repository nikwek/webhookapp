# scripts/generate_encryption_key.py
from cryptography.fernet import Fernet
from . import ScriptUtils

def main():
    """Generate a new Fernet encryption key and store it securely."""
    # Set up Python path for imports
    ScriptUtils.setup_project_path()
    
    # Generate new key
    key = Fernet.generate_key()
    key_str = key.decode()
    
    print("\nGenerated Encryption Key:")
    print(f"ENCRYPTION_KEY={key_str}")
    
    print("\nIMPORTANT:")
    print("1. Save this key securely - you'll need it to decrypt any stored credentials")
    print("2. Add this key to your environment variables:")
    print("   - For development: Add to your .env file")
    print("   - For production: Add to your server environment")
    
    # Offer to update .env
    ScriptUtils.update_env_file('ENCRYPTION_KEY', key_str)

if __name__ == "__main__":
    main()