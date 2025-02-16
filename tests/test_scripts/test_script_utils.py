# /tests/test_scripts/test_script_utils.py
import pytest
from pathlib import Path
import sys
import os
from scripts import ScriptUtils

def test_get_project_root():
    """Test that get_project_root returns a Path object to an existing directory."""
    root = ScriptUtils.get_project_root()
    assert isinstance(root, Path)
    assert root.exists()
    assert root.is_dir()

def test_setup_project_path():
    """Test that setup_project_path adds project root to sys.path."""
    root_str = str(ScriptUtils.get_project_root())
    
    # Remove root from sys.path if it's there
    if root_str in sys.path:
        sys.path.remove(root_str)
    
    ScriptUtils.setup_project_path()
    assert root_str in sys.path

def test_load_env_file(mock_env_file, mock_project_root):
    """Test loading variables from .env file."""
    env_vars = ScriptUtils.load_env_file()
    
    assert env_vars['TEST_KEY1'] == 'value1'
    assert env_vars['TEST_KEY2'] == 'value2'
    assert env_vars['TEST_KEY3'] == 'value3 with spaces'
    assert len(env_vars) == 3  # Comments should be ignored

def test_load_env_file_nonexistent(mock_project_root):
    """Test loading from non-existent .env file returns empty dict."""
    env_vars = ScriptUtils.load_env_file()
    assert env_vars == {}

def test_update_env_file_new_key(mock_env_file, mock_project_root, monkeypatch):
    """Test adding a new key to .env file."""
    # Mock input to simulate user confirming
    monkeypatch.setattr('builtins.input', lambda _: 'y')
    
    assert ScriptUtils.update_env_file('NEW_KEY', 'new_value')
    
    env_vars = ScriptUtils.load_env_file()
    assert env_vars['NEW_KEY'] == 'new_value'
    assert len(env_vars) == 4  # Original 3 + new key

def test_update_env_file_existing_key(mock_env_file, mock_project_root, monkeypatch):
    """Test updating an existing key in .env file."""
    # Mock input to simulate user confirming
    monkeypatch.setattr('builtins.input', lambda _: 'y')
    
    assert ScriptUtils.update_env_file('TEST_KEY1', 'updated_value')
    
    env_vars = ScriptUtils.load_env_file()
    assert env_vars['TEST_KEY1'] == 'updated_value'
    assert len(env_vars) == 3  # Number of keys should remain same

def test_update_env_file_user_decline(mock_env_file, mock_project_root, monkeypatch):
    """Test user declining to update existing key."""
    # Mock input to simulate user declining
    monkeypatch.setattr('builtins.input', lambda _: 'n')
    
    assert not ScriptUtils.update_env_file('TEST_KEY1', 'updated_value')
    
    env_vars = ScriptUtils.load_env_file()
    assert env_vars['TEST_KEY1'] == 'value1'  # Value should remain unchanged

def test_get_env_value_existing(monkeypatch):
    """Test getting existing environment variable."""
    monkeypatch.setenv('TEST_ENV_VAR', 'test_value')
    assert ScriptUtils.get_env_value('TEST_ENV_VAR') == 'test_value'

def test_get_env_value_with_prompt(monkeypatch):
    """Test getting non-existent environment variable with prompt."""
    # Mock input to simulate user input
    monkeypatch.setattr('builtins.input', lambda _: 'user_input')
    
    value = ScriptUtils.get_env_value('NONEXISTENT_VAR', prompt='Enter value: ')
    assert value == 'user_input'

def test_get_env_value_none():
    """Test getting non-existent environment variable without prompt."""
    assert ScriptUtils.get_env_value('NONEXISTENT_VAR') is None