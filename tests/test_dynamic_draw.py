"""
Dynamic draw endpoint tests
"""

import pytest
from datetime import datetime, timezone, timedelta
from app.models.draw import Draw, DrawType, DrawStatus, Language


@pytest.mark.dynamic_draw
class TestDynamicDrawCreate:
    """Test dynamic draw creation endpoint"""
    
    def test_create_dynamic_draw_success(self, client, auth_headers, test_db):
        """Test successful dynamic draw creation"""
        response = client.post(
            "/api/v1/draws/dynamic",
            headers=auth_headers,
            json={
                "addressRequired": True,
                "phoneNumberRequired": True,
                "drawDate": "2025-12-25T20:00:00Z",
                "participants": [{
                    "firstName": "Organizer",
                    "lastName": "Test",
                    "email": "organizer@example.com",
                    "address": "123 Main St",
                    "phone": "+1234567890"
                }]
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert "inviteCode" in data
        assert "drawId" in data
        
        # Verify in database
        draw = test_db.query(Draw).filter(Draw.id == data["drawId"]).first()
        assert draw is not None
        assert draw.draw_type == DrawType.DYNAMIC.value
        assert draw.status == DrawStatus.ACTIVE.value
        assert draw.invite_code == data["inviteCode"]
        assert len(draw.participants) == 1
        assert draw.language == Language.TR.value  # Default language
    
    def test_create_dynamic_draw_without_auth(self, client):
        """Test that dynamic draw requires authentication"""
        response = client.post(
            "/api/v1/draws/dynamic",
            json={
                "addressRequired": False,
                "phoneNumberRequired": False,
                "participants": [{
                    "firstName": "Test",
                    "lastName": "User",
                    "email": "test@example.com"
                }]
            }
        )
        
        assert response.status_code == 401
    
    def test_create_dynamic_draw_without_schedule(self, client, auth_headers):
        """Test creating dynamic draw without drawDate"""
        response = client.post(
            "/api/v1/draws/dynamic",
            headers=auth_headers,
            json={
                "addressRequired": False,
                "phoneNumberRequired": False,
                "participants": [{
                    "firstName": "Test",
                    "lastName": "User",
                    "email": "test@example.com"
                }]
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
    
    def test_create_dynamic_draw_exact_hour_validation(self, client, auth_headers):
        """Test that drawDate must be at exact hour"""
        response = client.post(
            "/api/v1/draws/dynamic",
            headers=auth_headers,
            json={
                "addressRequired": False,
                "phoneNumberRequired": False,
                "drawDate": "2025-12-25T13:33:00Z",
                "participants": [{
                    "firstName": "Test",
                    "lastName": "User",
                    "email": "test@example.com"
                }]
            }
        )
        
        assert response.status_code == 422
        assert "exact hour" in str(response.json()).lower()
    
    def test_create_dynamic_draw_current_year_validation(self, client, auth_headers):
        """Test that drawDate must be in current year"""
        response = client.post(
            "/api/v1/draws/dynamic",
            headers=auth_headers,
            json={
                "addressRequired": False,
                "phoneNumberRequired": False,
                "drawDate": "2026-01-15T14:00:00Z",
                "participants": [{
                    "firstName": "Test",
                    "lastName": "User",
                    "email": "test@example.com"
                }]
            }
        )
        
        assert response.status_code == 422
        assert "current year" in str(response.json()).lower()
    
    def test_create_dynamic_draw_organizer_address_required(self, client, auth_headers):
        """Test that organizer must have address if required"""
        response = client.post(
            "/api/v1/draws/dynamic",
            headers=auth_headers,
            json={
                "addressRequired": True,
                "phoneNumberRequired": False,
                "participants": [{
                    "firstName": "Test",
                    "lastName": "User",
                    "email": "test@example.com"
                    # Missing address
                }]
            }
        )
        
        assert response.status_code == 422
        assert "address is required" in str(response.json()).lower()
    
    def test_create_dynamic_draw_organizer_phone_required(self, client, auth_headers):
        """Test that organizer must have phone if required"""
        response = client.post(
            "/api/v1/draws/dynamic",
            headers=auth_headers,
            json={
                "addressRequired": False,
                "phoneNumberRequired": True,
                "participants": [{
                    "firstName": "Test",
                    "lastName": "User",
                    "email": "test@example.com"
                    # Missing phone
                }]
            }
        )
        
        assert response.status_code == 422
        assert "phone is required" in str(response.json()).lower()
    
    def test_invite_code_uniqueness(self, client, auth_headers, test_db):
        """Test that invite codes are unique"""
        # Create multiple draws
        invite_codes = set()
        
        for i in range(5):
            response = client.post(
                "/api/v1/draws/dynamic",
                headers=auth_headers,
                json={
                    "addressRequired": False,
                    "phoneNumberRequired": False,
                    "participants": [{
                        "firstName": "Test",
                        "lastName": f"User{i}",
                        "email": f"test{i}@example.com"
                    }]
                }
            )
            
            assert response.status_code == 201
            invite_code = response.json()["inviteCode"]
            invite_codes.add(invite_code)
        
        # All invite codes should be unique
        assert len(invite_codes) == 5
    
    def test_create_dynamic_draw_with_language_tr(self, client, auth_headers, test_db):
        """Test creating dynamic draw with TR language"""
        response = client.post(
            "/api/v1/draws/dynamic",
            headers=auth_headers,
            json={
                "addressRequired": False,
                "phoneNumberRequired": False,
                "language": "TR",
                "participants": [{
                    "firstName": "Test",
                    "lastName": "User",
                    "email": "test@example.com"
                }]
            }
        )
        
        assert response.status_code == 201
        draw = test_db.query(Draw).filter(Draw.id == response.json()["drawId"]).first()
        assert draw.language == Language.TR.value
    
    def test_create_dynamic_draw_with_language_en(self, client, auth_headers, test_db):
        """Test creating dynamic draw with EN language"""
        response = client.post(
            "/api/v1/draws/dynamic",
            headers=auth_headers,
            json={
                "addressRequired": False,
                "phoneNumberRequired": False,
                "language": "EN",
                "participants": [{
                    "firstName": "Test",
                    "lastName": "User",
                    "email": "test@example.com"
                }]
            }
        )
        
        assert response.status_code == 201
        draw = test_db.query(Draw).filter(Draw.id == response.json()["drawId"]).first()
        assert draw.language == Language.EN.value
    
    def test_create_dynamic_draw_invalid_language(self, client, auth_headers):
        """Test validation with invalid language"""
        response = client.post(
            "/api/v1/draws/dynamic",
            headers=auth_headers,
            json={
                "addressRequired": False,
                "phoneNumberRequired": False,
                "language": "FR",
                "participants": [{
                    "firstName": "Test",
                    "lastName": "User",
                    "email": "test@example.com"
                }]
            }
        )
        
        assert response.status_code == 422
        assert "language must be either 'TR' or 'EN'" in str(response.json())

