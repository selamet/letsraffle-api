"""
Manual draw endpoint tests
"""

import pytest
from app.models.draw import Draw, DrawType, DrawStatus, Language


@pytest.mark.manual_draw
class TestManualDraw:
    """Test manual draw creation endpoint"""
    
    def test_create_manual_draw_authenticated(self, client, auth_headers, test_db):
        """Test creating manual draw with authentication"""
        response = client.post(
            "/api/v1/draws/manual",
            headers=auth_headers,
            json={
                "addressRequired": False,
                "phoneNumberRequired": False,
                "participants": [
                    {"firstName": "Alice", "lastName": "Smith", "email": "alice@example.com"},
                    {"firstName": "Bob", "lastName": "Jones", "email": "bob@example.com"},
                    {"firstName": "Carol", "lastName": "White", "email": "carol@example.com"}
                ]
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert "drawId" in data
        
        # Verify in database
        draw = test_db.query(Draw).filter(Draw.id == data["drawId"]).first()
        assert draw is not None
        assert draw.draw_type == DrawType.MANUAL.value
        assert draw.status == DrawStatus.IN_PROGRESS.value
        assert len(draw.participants) == 3
        assert draw.language == Language.TR.value  # Default language
    
    def test_create_manual_draw_anonymous(self, client, test_db):
        """Test creating manual draw without authentication"""
        response = client.post(
            "/api/v1/draws/manual",
            json={
                "addressRequired": False,
                "phoneNumberRequired": False,
                "participants": [
                    {"firstName": "User1", "lastName": "Test", "email": "user1@test.com"},
                    {"firstName": "User2", "lastName": "Test", "email": "user2@test.com"},
                    {"firstName": "User3", "lastName": "Test", "email": "user3@test.com"}
                ]
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        
        # Verify creator_id is None for anonymous
        draw = test_db.query(Draw).filter(Draw.id == data["drawId"]).first()
        assert draw.creator_id is None
    
    def test_create_manual_draw_min_participants_validation(self, client):
        """Test validation for minimum 3 participants"""
        response = client.post(
            "/api/v1/draws/manual",
            json={
                "addressRequired": False,
                "phoneNumberRequired": False,
                "participants": [
                    {"firstName": "Alice", "lastName": "Smith", "email": "alice@example.com"},
                    {"firstName": "Bob", "lastName": "Jones", "email": "bob@example.com"}
                ]
            }
        )
        
        assert response.status_code == 422
        assert "at least 3" in str(response.json())
    
    def test_create_manual_draw_address_required(self, client):
        """Test address requirement validation"""
        response = client.post(
            "/api/v1/draws/manual",
            json={
                "addressRequired": True,
                "phoneNumberRequired": False,
                "participants": [
                    {"firstName": "Alice", "lastName": "Smith", "email": "alice@example.com", "address": "123 Main St"},
                    {"firstName": "Bob", "lastName": "Jones", "email": "bob@example.com"},  # Missing address
                    {"firstName": "Carol", "lastName": "White", "email": "carol@example.com", "address": "789 Oak Ave"}
                ]
            }
        )
        
        assert response.status_code == 422
        assert "address is required" in str(response.json()).lower()
    
    def test_create_manual_draw_phone_required(self, client):
        """Test phone requirement validation"""
        response = client.post(
            "/api/v1/draws/manual",
            json={
                "addressRequired": False,
                "phoneNumberRequired": True,
                "participants": [
                    {"firstName": "Alice", "lastName": "Smith", "email": "alice@example.com", "phone": "+1234567890"},
                    {"firstName": "Bob", "lastName": "Jones", "email": "bob@example.com", "phone": "+9876543210"},
                    {"firstName": "Carol", "lastName": "White", "email": "carol@example.com"}  # Missing phone
                ]
            }
        )
        
        assert response.status_code == 422
        assert "phone is required" in str(response.json()).lower()
    
    def test_create_manual_draw_whitespace_address(self, client):
        """Test that whitespace-only address is rejected"""
        response = client.post(
            "/api/v1/draws/manual",
            json={
                "addressRequired": True,
                "phoneNumberRequired": False,
                "participants": [
                    {"firstName": "Alice", "lastName": "Smith", "email": "alice@example.com", "address": "Valid Address"},
                    {"firstName": "Bob", "lastName": "Jones", "email": "bob@example.com", "address": "   "},
                    {"firstName": "Carol", "lastName": "White", "email": "carol@example.com", "address": "Another Valid"}
                ]
            }
        )
        
        assert response.status_code == 422
    
    def test_create_manual_draw_invalid_email(self, client):
        """Test validation with invalid email"""
        response = client.post(
            "/api/v1/draws/manual",
            json={
                "addressRequired": False,
                "phoneNumberRequired": False,
                "participants": [
                    {"firstName": "Alice", "lastName": "Smith", "email": "invalid-email"},
                    {"firstName": "Bob", "lastName": "Jones", "email": "bob@example.com"},
                    {"firstName": "Carol", "lastName": "White", "email": "carol@example.com"}
                ]
            }
        )
        
        assert response.status_code == 422
    
    def test_create_manual_draw_with_language_tr(self, client, auth_headers, test_db):
        """Test creating manual draw with TR language"""
        response = client.post(
            "/api/v1/draws/manual",
            headers=auth_headers,
            json={
                "addressRequired": False,
                "phoneNumberRequired": False,
                "language": "TR",
                "participants": [
                    {"firstName": "Alice", "lastName": "Smith", "email": "alice@example.com"},
                    {"firstName": "Bob", "lastName": "Jones", "email": "bob@example.com"},
                    {"firstName": "Carol", "lastName": "White", "email": "carol@example.com"}
                ]
            }
        )
        
        assert response.status_code == 201
        draw = test_db.query(Draw).filter(Draw.id == response.json()["drawId"]).first()
        assert draw.language == Language.TR.value
    
    def test_create_manual_draw_with_language_en(self, client, auth_headers, test_db):
        """Test creating manual draw with EN language"""
        response = client.post(
            "/api/v1/draws/manual",
            headers=auth_headers,
            json={
                "addressRequired": False,
                "phoneNumberRequired": False,
                "language": "EN",
                "participants": [
                    {"firstName": "Alice", "lastName": "Smith", "email": "alice@example.com"},
                    {"firstName": "Bob", "lastName": "Jones", "email": "bob@example.com"},
                    {"firstName": "Carol", "lastName": "White", "email": "carol@example.com"}
                ]
            }
        )
        
        assert response.status_code == 201
        draw = test_db.query(Draw).filter(Draw.id == response.json()["drawId"]).first()
        assert draw.language == Language.EN.value
    
    def test_create_manual_draw_invalid_language(self, client):
        """Test validation with invalid language"""
        response = client.post(
            "/api/v1/draws/manual",
            json={
                "addressRequired": False,
                "phoneNumberRequired": False,
                "language": "FR",
                "participants": [
                    {"firstName": "Alice", "lastName": "Smith", "email": "alice@example.com"},
                    {"firstName": "Bob", "lastName": "Jones", "email": "bob@example.com"},
                    {"firstName": "Carol", "lastName": "White", "email": "carol@example.com"}
                ]
            }
        )
        
        assert response.status_code == 422
        assert "language must be either 'TR' or 'EN'" in str(response.json())

