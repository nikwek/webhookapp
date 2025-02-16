# scripts/generate_jwt.py
import secrets
from . import ScriptUtils

def main():
    """Generate a new JWT secret key."""
    # Set up Python path for imports
    ScriptUtils.setup_project_path()
    
    # Generate new key
    key = secrets.token_urlsafe(32)
    
    print("\nGenerated JWT Secret Key:")
    print(f"JWT_SECRET_KEY={key}")
    
    print("\nIMPORTANT:")
    print("1. Save this key securely")
    print("2. Add this key to your environment variables:")
    print("   - For development: Add to your .env file")
    print("   - For production: Add to your server environment")
    
    # Offer to update .env
    ScriptUtils.update_env_file('JWT_SECRET_KEY', key)

if __name__ == "__main__":
    main()