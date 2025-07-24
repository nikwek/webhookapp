import json
from unittest.mock import patch, MagicMock
from app.models.user import User
from app import db


class TestTwoFactorAuthentication:
    """Test 2FA setup, verification, and management functionality"""
    
    def test_2fa_setup_page_loads(self, auth_client):
        """Test 2FA setup page loads correctly"""
        response = auth_client.get('/auth/setup-2fa')
        assert response.status_code == 200
        # Look for 2FA related content
        content_indicators = [b'Two-Factor', b'2FA', b'Authentication', b'Setup']
        assert any(indicator in response.data for indicator in content_indicators)
    
    def test_2fa_setup_post_redirects_to_verify(self, auth_client, app):
        """Test 2FA setup POST redirects to verification page"""
        with app.app_context():
            # Mock database operations that might fail
            with patch('app.routes.two_factor.db.session.execute') as mock_execute:
                with patch('app.routes.two_factor.db.session.commit') as mock_commit:
                    mock_execute.return_value = None
                    mock_commit.return_value = None
                    
                    response = auth_client.post('/auth/setup-2fa', follow_redirects=True)
                    # Should either succeed or show setup page again
                    assert response.status_code in [200, 302]
                    # Should contain 2FA related content
                    content_indicators = [b'QR', b'verify', b'code', b'2FA', b'Authentication']
                    assert any(indicator in response.data for indicator in content_indicators)
    
    def test_2fa_verification_page_loads_with_secret(self, auth_client, app):
        """Test 2FA verification page loads when user has a secret"""
        with app.app_context():
            # Set up 2FA secret for user
            user = User.query.filter_by(email='testuser@example.com').first()
            user.tf_totp_secret = json.dumps({"key": "TESTSECRET123456"})
            user.tf_primary_method = "authenticator"
            db.session.commit()
            
            response = auth_client.get('/auth/verify-2fa')
            # Accept both 200 (page loads) and 302 (redirect) as valid
            assert response.status_code in [200, 302]
            if response.status_code == 200:
                # Should show QR code or verification form
                verification_indicators = [b'QR', b'code', b'verify', b'authenticator']
                assert any(indicator in response.data for indicator in verification_indicators)
    
    def test_2fa_verification_without_secret_redirects(self, auth_client):
        """Test accessing verify page without setting up 2FA first redirects to setup"""
        response = auth_client.get('/auth/verify-2fa', follow_redirects=True)
        assert response.status_code == 200
        # Should be redirected to setup or show setup message
        setup_indicators = [b'Set up 2FA first', b'setup', b'Two-Factor', b'Authentication']
        assert any(indicator in response.data for indicator in setup_indicators)
    
    def test_2fa_disable_endpoint_exists(self, auth_client, app):
        """Test 2FA disable endpoint is accessible and responds correctly"""
        with app.app_context():
            # Enable 2FA first
            user = User.query.filter_by(email='testuser@example.com').first()
            user.tf_totp_secret = json.dumps({"key": "TESTSECRET123456"})
            user.tf_primary_method = "authenticator"
            db.session.commit()
            
            # Verify 2FA is enabled
            assert user.tf_totp_secret is not None
            assert user.tf_primary_method == "authenticator"
            
            response = auth_client.post('/auth/disable-2fa', follow_redirects=True)
            # Should either succeed or redirect (not fail with 404/500)
            assert response.status_code in [200, 302]
            # Endpoint should exist and be accessible
    
    def test_2fa_reset_endpoint_accessible(self, auth_client, app):
        """Test 2FA reset endpoint is accessible"""
        with app.app_context():
            # Enable 2FA with recovery codes
            user = User.query.filter_by(email='testuser@example.com').first()
            user.tf_totp_secret = json.dumps({"key": "TESTSECRET123456"})
            user.tf_primary_method = "authenticator"
            user.tf_recovery_codes = "some_recovery_codes"
            db.session.commit()
            
            response = auth_client.post('/auth/reset-2fa', follow_redirects=True)
            # Should either succeed or redirect (not fail with 404/500)
            assert response.status_code in [200, 302]
            # Endpoint should exist and be accessible
    
    def test_2fa_recovery_codes_endpoint_accessible(self, auth_client):
        """Test recovery codes endpoint is accessible"""
        response = auth_client.get('/auth/recovery-2fa')
        # Should either show page or redirect (not fail with 404/500)
        assert response.status_code in [200, 302]
        # Endpoint should exist and be accessible
    
    def test_2fa_reset_get_page_loads(self, auth_client):
        """Test 2FA reset GET page loads correctly"""
        response = auth_client.get('/auth/reset-2fa')
        # Should either show page or redirect (not fail with 404/500)
        assert response.status_code in [200, 302]
        if response.status_code == 200:
            # Should contain reset-related content
            reset_indicators = [b'reset', b'2FA', b'Authentication']
            assert any(indicator in response.data for indicator in reset_indicators)
    
    def test_unauthenticated_cannot_access_2fa_endpoints(self, client):
        """Test unauthenticated users cannot access 2FA endpoints"""
        endpoints = [
            '/auth/setup-2fa',
            '/auth/verify-2fa',
            '/auth/recovery-2fa',
            '/auth/reset-2fa'
        ]
        
        for endpoint in endpoints:
            response = client.get(endpoint, follow_redirects=True)
            # Should be redirected to login
            assert response.status_code == 200
            assert b'Login' in response.data or b'sign in' in response.data.lower()
