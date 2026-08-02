def test_auth_routes_are_not_registered(client):
    assert client.get('/api/auth/me').status_code == 404
    assert client.post('/api/auth/login', json={'username': 'x', 'password': 'y'}).status_code == 404
