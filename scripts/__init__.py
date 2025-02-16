# scripts/__init__.py
import os
import sys
from pathlib import Path
from typing import Optional

class ScriptUtils:
    @staticmethod
    def get_project_root() -> Path:
        """Get the absolute path to the project root directory."""
        return Path(__file__).parent.parent.absolute()
    
    @staticmethod
    def setup_project_path() -> None:
        """Add project root to Python path to allow importing from app."""
        root_dir = str(ScriptUtils.get_project_root())
        if root_dir not in sys.path:
            sys.path.append(root_dir)
    
    @staticmethod
    def load_env_file() -> dict:
        """Load environment variables from .env file if it exists."""
        env_path = ScriptUtils.get_project_root() / '.env'
        env_vars = {}
        
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        key, value = line.split('=', 1)
                        env_vars[key.strip()] = value.strip()
        
        return env_vars
    
    @staticmethod
    def update_env_file(key: str, value: str) -> bool:
        """
        Update or add a key-value pair to the .env file.
        
        Args:
            key: The environment variable name
            value: The value to set
            
        Returns:
            bool: True if file was updated, False if user declined
        """
        env_path = ScriptUtils.get_project_root() / '.env'
        
        # Create .env if it doesn't exist
        if not env_path.exists():
            confirm = input(".env file not found. Create it? (y/N): ")
            if confirm.lower() != 'y':
                return False
            env_path.write_text(f"{key}={value}\n")
            print(f"Created .env file with {key}")
            return True
        
        # Read existing contents
        env_vars = ScriptUtils.load_env_file()
        
        # Check if key exists
        if key in env_vars:
            confirm = input(f"{key} already exists in .env. Replace it? (y/N): ")
            if confirm.lower() != 'y':
                return False
        
        # Update or add the key-value pair
        env_vars[key] = value
        
        # Write back to file
        with open(env_path, 'w') as f:
            for k, v in env_vars.items():
                f.write(f"{k}={v}\n")
        
        print(f"Updated {key} in .env file")
        return True
    
    @staticmethod
    def get_env_value(key: str, prompt: Optional[str] = None) -> Optional[str]:
        """
        Get an environment variable value, optionally prompting user if not found.
        
        Args:
            key: The environment variable name
            prompt: Optional prompt to show user if value not found
            
        Returns:
            Optional[str]: The value if found or provided by user, None otherwise
        """
        value = os.environ.get(key)
        
        if not value and prompt:
            value = input(prompt)
        
        return value