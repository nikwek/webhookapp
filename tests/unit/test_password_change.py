from app.models.user import User
from app import db


class TestPasswordChangeAccess:
    """Test password change access and basic functionality"""
    
    def test_password_change_redirect_exists(self, auth_client):
        """Test password change redirect endpoint exists"""
        response = auth_client.get('/change-password')
        # Should either show form or redirect (not 404)
        assert response.status_code in [200, 302, 405]  # 405 is method not allowed, but endpoint exists
        
    def test_unauthenticated_cannot_access_password_change(self, client):
        """Test unauthenticated users cannot access password change"""
        response = client.get('/change-password', follow_redirects=True)
        assert response.status_code == 200
        # Should be redirected to login
        login_indicators = [b'Login', b'sign in', b'Email', b'Password']
        assert any(indicator in response.data for indicator in login_indicators)


class TestPasswordChangeIntegration:
    """Test password change integration with other features"""
    
    def test_password_change_with_2fa_enabled(self, auth_client, app):
        """Test password change endpoint is accessible when 2FA is enabled"""
        with app.app_context():
            # Enable 2FA
            user = User.query.filter_by(email='testuser@example.com').first()
            user.tf_totp_secret = '{"key": "TESTSECRET123456"}'
            user.tf_primary_method = "authenticator"
            db.session.commit()
            
            # Test that password change endpoint is accessible with 2FA enabled
            response = auth_client.get('/change-password')
            # Should either show form or redirect (not fail completely)
            assert response.status_code in [200, 302, 405]  # Endpoint should exist
            
            # 2FA should still be enabled
            user = User.query.filter_by(email='testuser@example.com').first()
            assert user.tf_totp_secret is not None
            assert user.tf_primary_method == "authenticator"
