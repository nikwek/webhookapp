def test_login_success(client, regular_user):
    response = client.post('/login', data={
        'username': 'testuser',
        'password': 'password'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Dashboard' in response.data

def test_login_failure(client):
    response = client.post('/login', data={
        'username': 'wrong',
        'password': 'wrong'
    }, follow_redirects=True)
    assert b'Invalid username or password' in response.data

def test_register(client):
    response = client.post('/register', data={
        'username': 'newuser',
        'password': 'newpass'
    }, follow_redirects=True)
    assert response.status_code == 200

def test_register_duplicate_username(client, regular_user):
    response = client.post('/register', data={
        'username': 'testuser',  # Same as regular_user
        'password': 'password'
    }, follow_redirects=True)
    assert b'Username already exists' in response.data

def test_login_required_pages(client):
    # Test pages that require login
    pages = [
        '/dashboard',
        '/settings'
    ]
    for page in pages:
        response = client.get(page)  # Don't follow redirects
        assert response.status_code == 302  # Should redirect to login
        assert '/login' in response.location  # Should redirect to login page

def test_logout(auth_client):
    response = auth_client.get('/logout', follow_redirects=True)
    assert response.status_code == 200
    assert b'Login' in response.data
    
    # Verify can't access protected page after logout
    response = auth_client.get('/dashboard')
    assert response.status_code == 302  # Redirects to login 