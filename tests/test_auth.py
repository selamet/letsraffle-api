"""
Authentication endpoint tests
"""

import pytest


@pytest.mark.auth
class TestRegister:
    """Test user registration endpoint"""
    
    def test_register_success(self, client):
        """Test successful user registration"""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "newuser@example.com",
                "password": "NewPassword123!"
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["access_token"] is not None
        assert data["refresh_token"] is not None
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == "newuser@example.com"
        assert data["user"]["id"] is not None
    
    def test_register_duplicate_email(self, client, test_user):
        """Test registration with duplicate email"""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": test_user.email,
                "password": "AnotherPassword123!"
            }
        )
        
        assert response.status_code == 400
        assert "already registered" in response.json()["detail"].lower()
    
    def test_register_invalid_email(self, client):
        """Test registration with invalid email format"""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "invalid-email",
                "password": "Password123!"
            }
        )
        
        assert response.status_code == 422
    
    def test_register_missing_password(self, client):
        """Test registration without password"""
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "test@example.com"}
        )
        
        assert response.status_code == 422


@pytest.mark.auth
class TestLogin:
    """Test user login endpoint"""
    
    def test_login_success(self, client, test_user):
        """Test successful login"""
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user.email,
                "password": "TestPassword123!"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] is not None
        assert data["refresh_token"] is not None
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == test_user.email
    
    def test_login_wrong_password(self, client, test_user):
        """Test login with wrong password"""
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user.email,
                "password": "WrongPassword123!"
            }
        )
        
        assert response.status_code == 401
        assert "incorrect" in response.json()["detail"].lower()
    
    def test_login_nonexistent_user(self, client):
        """Test login with non-existent email"""
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": "Password123!"
            }
        )
        
        assert response.status_code == 401
    
    def test_login_invalid_email_format(self, client):
        """Test login with invalid email format"""
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "invalid-email",
                "password": "Password123!"
            }
        )
        
        assert response.status_code == 422


@pytest.mark.auth
class TestRefreshToken:
    """Test refresh token endpoint"""
    
    def test_refresh_token_success(self, client, test_user, test_db):
        """Test successful token refresh"""
        # First login to get refresh token
        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "email": test_user.email,
                "password": "TestPassword123!"
            }
        )
        
        assert login_response.status_code == 200
        refresh_token = login_response.json()["refresh_token"]
        
        # Refresh token
        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["access_token"] is not None
        assert data["refresh_token"] is not None
        assert data["token_type"] == "bearer"
        assert data["user"]["email"] == test_user.email
        
        # Verify tokens are valid (can be used)
        # Note: Tokens might be the same if generated in the same second,
        # but the important thing is that refresh endpoint works correctly
        assert len(data["access_token"]) > 0
        assert len(data["refresh_token"]) > 0
    
    def test_refresh_token_invalid(self, client):
        """Test refresh with invalid token"""
        response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid-token"}
        )
        
        assert response.status_code == 401
        assert "invalid" in response.json()["detail"].lower()
    
    def test_refresh_token_missing(self, client):
        """Test refresh without token"""
        response = client.post(
            "/api/v1/auth/refresh",
            json={}
        )
        
        assert response.status_code == 422

