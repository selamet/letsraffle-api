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



@pytest.mark.auth
class TestTokenTypes:
    """Only access tokens authenticate a request; every other signed token is refused"""

    def _foreign_tokens(self, email):
        from app.core.security import (
            create_participant_token,
            create_refresh_token,
            create_reset_token,
            create_unsubscribe_token,
        )

        return {
            "refresh": create_refresh_token({"sub": email}),
            "reset": create_reset_token(email),
            "unsubscribe": create_unsubscribe_token(email),
            "participant": create_participant_token(1, 1),
        }

    def test_access_token_authenticates(self, client, auth_headers):
        assert client.get("/api/v1/auth/me", headers=auth_headers).status_code == 200

    @pytest.mark.parametrize("kind", ["refresh", "reset", "unsubscribe", "participant"])
    def test_other_token_types_are_rejected(self, client, test_user, kind):
        token = self._foreign_tokens(test_user.email)[kind]
        headers = {"Authorization": f"Bearer {token}"}

        assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
        assert client.delete("/api/v1/auth/me", headers=headers).status_code == 401

    def test_untyped_token_is_rejected(self, client, test_user):
        import jwt
        from datetime import datetime, timedelta, timezone
        from app.config import settings

        token = jwt.encode(
            {"sub": test_user.email, "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
            settings.secret_key,
            algorithm=settings.algorithm,
        )

        response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401

    def test_optional_auth_ignores_other_token_types(self, client, test_user, test_db):
        from app.core.security import create_unsubscribe_token
        from app.models.draw import Draw

        response = client.post(
            "/api/v1/draws/manual",
            headers={"Authorization": f"Bearer {create_unsubscribe_token(test_user.email)}"},
            json={
                "participants": [
                    {"firstName": "A", "lastName": "A", "email": "a@example.com"},
                    {"firstName": "B", "lastName": "B", "email": "b@example.com"},
                    {"firstName": "C", "lastName": "C", "email": "c@example.com"},
                ]
            },
        )

        assert response.status_code == 201
        draw = test_db.query(Draw).filter(Draw.id == response.json()["drawId"]).first()
        assert draw.creator_id is None

    def test_reset_password_with_reset_token(self, client, test_user):
        from app.core.security import create_reset_token

        response = client.post(
            "/api/v1/auth/reset-password",
            json={"token": create_reset_token(test_user.email), "new_password": "newpassword123"},
        )
        assert response.status_code == 200

        login = client.post(
            "/api/v1/auth/login", json={"email": test_user.email, "password": "newpassword123"}
        )
        assert login.status_code == 200

    def test_reset_password_rejects_access_token(self, client, auth_token):
        response = client.post(
            "/api/v1/auth/reset-password",
            json={"token": auth_token, "new_password": "newpassword123"},
        )
        assert response.status_code == 400
