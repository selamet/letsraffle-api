"""
Draw list endpoint tests
"""

import pytest
from datetime import datetime


@pytest.mark.draw_list
class TestDrawList:
    """Test draw list endpoint"""
    
    def test_get_draws_list_success(self, client, auth_headers, test_db):
        """Test authenticated user can get their draws list"""
        # Create multiple draws
        create_response1 = client.post(
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
        
        create_response2 = client.post(
            "/api/v1/draws/dynamic",
            headers=auth_headers,
            json={
                "addressRequired": True,
                "phoneNumberRequired": False,
                "participants": [{
                    "firstName": "Org2",
                    "lastName": "Test",
                    "email": "org2@test.com",
                    "address": "123 Main St"
                }]
            }
        )
        
        # Get draws list
        response = client.get(
            "/api/v1/draws",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2
        
        # Verify draw properties
        draw_ids = [draw["id"] for draw in data]
        assert create_response1.json()["drawId"] in draw_ids
        assert create_response2.json()["drawId"] in draw_ids
        
        # Verify each draw has required fields
        for draw in data:
            assert "id" in draw
            assert "drawType" in draw
            assert "status" in draw
            assert "participantCount" in draw
            assert "createdAt" in draw
            assert "language" in draw
            assert draw["drawType"] in ["manual", "dynamic"]
            assert draw["status"] in ["active", "in_progress", "completed", "cancelled"]
            assert isinstance(draw["participantCount"], int)
            assert draw["language"] in ["TR", "EN"]
    
    def test_get_draws_list_empty(self, client, auth_headers):
        """Test user with no draws gets empty list"""
        response = client.get(
            "/api/v1/draws",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0
    
    def test_get_draws_list_requires_auth(self, client):
        """Test that draw list requires authentication"""
        response = client.get("/api/v1/draws")
        
        assert response.status_code == 401
    
    def test_get_draws_list_only_own_draws(self, client, auth_headers, second_auth_headers, test_db):
        """Test that user only sees their own draws"""
        # User 1 creates a draw
        create_response1 = client.post(
            "/api/v1/draws/dynamic",
            headers=auth_headers,
            json={
                "addressRequired": False,
                "phoneNumberRequired": False,
                "participants": [{
                    "firstName": "Org1",
                    "lastName": "Test",
                    "email": "org1@test.com"
                }]
            }
        )
        
        # User 2 creates a draw
        create_response2 = client.post(
            "/api/v1/draws/dynamic",
            headers=second_auth_headers,
            json={
                "addressRequired": False,
                "phoneNumberRequired": False,
                "participants": [{
                    "firstName": "Org2",
                    "lastName": "Test",
                    "email": "org2@test.com"
                }]
            }
        )
        
        # User 1 gets their draws
        response1 = client.get(
            "/api/v1/draws",
            headers=auth_headers
        )
        
        assert response1.status_code == 200
        data1 = response1.json()
        assert len(data1) == 1
        assert data1[0]["id"] == create_response1.json()["drawId"]
        
        # User 2 gets their draws
        response2 = client.get(
            "/api/v1/draws",
            headers=second_auth_headers
        )
        
        assert response2.status_code == 200
        data2 = response2.json()
        assert len(data2) == 1
        assert data2[0]["id"] == create_response2.json()["drawId"]
    
    def test_get_draws_list_participant_count(self, client, auth_headers, test_db):
        """Test that participant count is correctly calculated"""
        # Create a draw
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
        
        draw_id = create_response.json()["drawId"]
        invite_code = create_response.json()["inviteCode"]
        
        # Add participants
        client.post(
            f"/api/v1/draws/join/{invite_code}",
            json={"firstName": "P1", "lastName": "Test", "email": "p1@test.com"}
        )
        client.post(
            f"/api/v1/draws/join/{invite_code}",
            json={"firstName": "P2", "lastName": "Test", "email": "p2@test.com"}
        )
        
        # Get draws list
        response = client.get(
            "/api/v1/draws",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["participantCount"] == 3  # Organizer + 2 participants
    
    def test_get_draws_list_ordering(self, client, auth_headers, test_db):
        """Test that draws are ordered by creation date (newest first)"""
        # Create first draw
        create_response1 = client.post(
            "/api/v1/draws/dynamic",
            headers=auth_headers,
            json={
                "addressRequired": False,
                "phoneNumberRequired": False,
                "participants": [{
                    "firstName": "Org1",
                    "lastName": "Test",
                    "email": "org1@test.com"
                }]
            }
        )
        
        draw_id1 = create_response1.json()["drawId"]
        
        # Longer delay to ensure different timestamps
        import time
        time.sleep(0.5)
        
        # Create second draw
        create_response2 = client.post(
            "/api/v1/draws/dynamic",
            headers=auth_headers,
            json={
                "addressRequired": False,
                "phoneNumberRequired": False,
                "participants": [{
                    "firstName": "Org2",
                    "lastName": "Test",
                    "email": "org2@test.com"
                }]
            }
        )
        
        draw_id2 = create_response2.json()["drawId"]
        
        # Get draws list
        response = client.get(
            "/api/v1/draws",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        
        # Verify created_at timestamps are in descending order (newest first)
        created_at_first = datetime.fromisoformat(data[0]["createdAt"].replace("Z", "+00:00"))
        created_at_second = datetime.fromisoformat(data[1]["createdAt"].replace("Z", "+00:00"))
        assert created_at_first >= created_at_second, "Draws should be ordered by creation date (newest first)"
        
        # If timestamps are different, verify the order matches
        if created_at_first > created_at_second:
            assert data[0]["id"] == draw_id2, "Most recent draw should be first"
            assert data[1]["id"] == draw_id1, "Older draw should be second"

