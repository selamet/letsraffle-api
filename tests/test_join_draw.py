"""
Public join draw endpoint tests
"""

import pytest
from app.models.draw import Draw, Participant, DrawStatus


@pytest.mark.dynamic_draw
class TestDrawPublicInfo:
    """Test getting public draw information"""
    
    def test_get_public_info_success(self, client, auth_headers, test_db):
        """Test getting public info with valid invite code"""
        # Create a dynamic draw first
        create_response = client.post(
            "/api/v1/draws/dynamic",
            headers=auth_headers,
            json={
                "addressRequired": True,
                "phoneNumberRequired": False,
                "participants": [{
                    "firstName": "Org",
                    "lastName": "Test",
                    "email": "org@test.com",
                    "address": "123 Main St"
                }]
            }
        )
        
        invite_code = create_response.json()["inviteCode"]
        
        # Get public info
        response = client.get(f"/api/v1/draws/join/{invite_code}")
        
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert data["requireAddress"] is True
        assert data["requirePhone"] is False
        assert data["status"] == "active"
        assert data["participantCount"] == 1
        assert "language" in data
        assert data["language"] in ["TR", "EN"]
    
    def test_get_public_info_invalid_code(self, client):
        """Test getting public info with invalid invite code"""
        response = client.get("/api/v1/draws/join/invalid-code-123")
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


@pytest.mark.dynamic_draw
class TestJoinDraw:
    """Test joining a draw via invite code"""
    
    def test_join_draw_success(self, client, auth_headers, test_db):
        """Test successfully joining a draw"""
        # Create draw
        create_response = client.post(
            "/api/v1/draws/dynamic",
            headers=auth_headers,
            json={
                "addressRequired": False,
                "phoneNumberRequired": False,
                "participants": [{
                    "firstName": "Organizer",
                    "lastName": "Test",
                    "email": "org@test.com"
                }]
            }
        )
        
        invite_code = create_response.json()["inviteCode"]
        draw_id = create_response.json()["drawId"]
        
        # Join draw
        response = client.post(
            f"/api/v1/draws/join/{invite_code}",
            json={
                "firstName": "Participant",
                "lastName": "One",
                "email": "participant1@example.com"
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["drawId"] == draw_id
        assert "participantId" in data
        
        # Verify participant count increased
        draw = test_db.query(Draw).filter(Draw.id == draw_id).first()
        assert len(draw.participants) == 2
    
    def test_join_draw_duplicate_email(self, client, auth_headers):
        """Test that same email cannot join twice"""
        # Create draw
        create_response = client.post(
            "/api/v1/draws/dynamic",
            headers=auth_headers,
            json={
                "addressRequired": False,
                "phoneNumberRequired": False,
                "participants": [{
                    "firstName": "Org",
                    "lastName": "Test",
                    "email": "org@test.com"
                }]
            }
        )
        
        invite_code = create_response.json()["inviteCode"]
        
        # First join
        response1 = client.post(
            f"/api/v1/draws/join/{invite_code}",
            json={
                "firstName": "Participant",
                "lastName": "One",
                "email": "duplicate@example.com"
            }
        )
        assert response1.status_code == 201
        
        # Try to join again with same email
        response2 = client.post(
            f"/api/v1/draws/join/{invite_code}",
            json={
                "firstName": "Another",
                "lastName": "Name",
                "email": "duplicate@example.com"
            }
        )
        
        assert response2.status_code == 409
        assert "already registered" in response2.json()["detail"].lower()
    
    def test_join_draw_address_required(self, client, auth_headers):
        """Test that address is required when draw requires it"""
        # Create draw with address required
        create_response = client.post(
            "/api/v1/draws/dynamic",
            headers=auth_headers,
            json={
                "addressRequired": True,
                "phoneNumberRequired": False,
                "participants": [{
                    "firstName": "Org",
                    "lastName": "Test",
                    "email": "org@test.com",
                    "address": "Org Address"
                }]
            }
        )
        
        invite_code = create_response.json()["inviteCode"]
        
        # Try to join without address
        response = client.post(
            f"/api/v1/draws/join/{invite_code}",
            json={
                "firstName": "Participant",
                "lastName": "One",
                "email": "participant@example.com"
                # Missing address
            }
        )
        
        assert response.status_code == 400
        assert "address is required" in response.json()["detail"].lower()
    
    def test_join_draw_phone_required(self, client, auth_headers):
        """Test that phone is required when draw requires it"""
        # Create draw with phone required
        create_response = client.post(
            "/api/v1/draws/dynamic",
            headers=auth_headers,
            json={
                "addressRequired": False,
                "phoneNumberRequired": True,
                "participants": [{
                    "firstName": "Org",
                    "lastName": "Test",
                    "email": "org@test.com",
                    "phone": "+1234567890"
                }]
            }
        )
        
        invite_code = create_response.json()["inviteCode"]
        
        # Try to join without phone
        response = client.post(
            f"/api/v1/draws/join/{invite_code}",
            json={
                "firstName": "Participant",
                "lastName": "One",
                "email": "participant@example.com"
                # Missing phone
            }
        )
        
        assert response.status_code == 400
        assert "phone" in response.json()["detail"].lower()
    
    def test_join_draw_invalid_invite_code(self, client):
        """Test joining with invalid invite code"""
        response = client.post(
            "/api/v1/draws/join/invalid-code-999",
            json={
                "firstName": "Test",
                "lastName": "User",
                "email": "test@example.com"
            }
        )
        
        assert response.status_code == 404
    
    def test_join_draw_whitespace_validation(self, client, auth_headers):
        """Test that whitespace-only address/phone is rejected"""
        # Create draw with requirements
        create_response = client.post(
            "/api/v1/draws/dynamic",
            headers=auth_headers,
            json={
                "addressRequired": True,
                "phoneNumberRequired": True,
                "participants": [{
                    "firstName": "Org",
                    "lastName": "Test",
                    "email": "org@test.com",
                    "address": "Valid Address",
                    "phone": "+123"
                }]
            }
        )
        
        invite_code = create_response.json()["inviteCode"]
        
        # Try to join with whitespace-only address
        response = client.post(
            f"/api/v1/draws/join/{invite_code}",
            json={
                "firstName": "Test",
                "lastName": "User",
                "email": "test@example.com",
                "address": "   ",
                "phone": "+456"
            }
        )
        
        assert response.status_code == 400

