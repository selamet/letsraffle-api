"""
Organizer management endpoint tests
"""

import pytest
from app.models.draw import Draw, Participant, DrawStatus


@pytest.mark.organizer
class TestGetDrawDetail:
    """Test getting draw details (organizer only)"""
    
    def test_get_draw_detail_success(self, client, auth_headers, test_db):
        """Test organizer can get draw details"""
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
        
        draw_id = create_response.json()["drawId"]
        invite_code = create_response.json()["inviteCode"]
        
        # Add some participants
        client.post(
            f"/api/v1/draws/join/{invite_code}",
            json={"firstName": "P1", "lastName": "Test", "email": "p1@test.com"}
        )
        
        # Get details
        response = client.get(
            f"/api/v1/draws/{invite_code}",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == draw_id
        assert data["drawType"] == "dynamic"
        assert data["status"] == "active"
        assert data["inviteCode"] == invite_code
        assert "language" in data
        assert data["language"] in ["TR", "EN"]
        assert len(data["participants"]) == 2
    
    def test_get_draw_detail_non_organizer(self, client, auth_headers, second_auth_headers):
        """Test that non-organizer cannot access draw details"""
        # User 1 creates draw
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
        
        # User 2 tries to access
        response = client.get(
            f"/api/v1/draws/{invite_code}",
            headers=second_auth_headers
        )
        
        assert response.status_code == 403
        assert "not authorized" in response.json()["detail"].lower()
    
    def test_get_draw_detail_without_auth(self, client, auth_headers):
        """Test that draw details require authentication"""
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
        
        draw_id = create_response.json()["drawId"]
        invite_code = create_response.json()["inviteCode"]
        
        # Try without auth
        response = client.get(f"/api/v1/draws/{invite_code}")
        
        assert response.status_code == 401
    
    def test_get_draw_detail_not_found(self, client, auth_headers):
        """Test getting non-existent draw"""
        response = client.get(
            "/api/v1/draws/non-existent-code",
            headers=auth_headers
        )
        
        assert response.status_code == 404


@pytest.mark.organizer
class TestDeleteParticipant:
    """Test deleting participants from a draw"""
    
    def test_delete_participant_success(self, client, auth_headers, test_db):
        """Test organizer can delete a participant"""
        # Create draw and add participants
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
        join_response = client.post(
            f"/api/v1/draws/join/{invite_code}",
            json={"firstName": "P1", "lastName": "Test", "email": "p1@test.com"}
        )
        
        participant_id = join_response.json()["participantId"]
        
        # Delete participant
        response = client.delete(
            f"/api/v1/draws/{draw_id}/participants/{participant_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 204
        
        # Verify deleted
        draw = test_db.query(Draw).filter(Draw.id == draw_id).first()
        assert len(draw.participants) == 1
    
    def test_delete_participant_cannot_delete_organizer(self, client, auth_headers, test_db):
        """Test that organizer cannot delete themselves"""
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
        
        draw_id = create_response.json()["drawId"]
        invite_code = create_response.json()["inviteCode"]
        
        # Get organizer ID (first participant)
        detail_response = client.get(f"/api/v1/draws/{invite_code}", headers=auth_headers)
        organizer_id = detail_response.json()["participants"][0]["id"]
        
        # Try to delete organizer
        response = client.delete(
            f"/api/v1/draws/{draw_id}/participants/{organizer_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 400
        assert "cannot delete the organizer" in response.json()["detail"].lower()
    
    def test_delete_participant_completed_draw(self, client, auth_headers, test_db):
        """Test that participants cannot be deleted from completed draw"""
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
        
        draw_id = create_response.json()["drawId"]
        invite_code = create_response.json()["inviteCode"]
        
        # Add participant
        join_response = client.post(
            f"/api/v1/draws/join/{invite_code}",
            json={"firstName": "P1", "lastName": "Test", "email": "p1@test.com"}
        )
        participant_id = join_response.json()["participantId"]
        
        # Mark draw as completed
        draw = test_db.query(Draw).filter(Draw.id == draw_id).first()
        draw.status = DrawStatus.COMPLETED.value
        test_db.commit()
        
        # Try to delete
        response = client.delete(
            f"/api/v1/draws/{draw_id}/participants/{participant_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 400
        assert "completed" in response.json()["detail"].lower()
    
    def test_delete_participant_non_organizer(self, client, auth_headers, second_auth_headers):
        """Test that non-organizer cannot delete participants"""
        # User 1 creates draw
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
        
        # User 2 tries to delete
        response = client.delete(
            f"/api/v1/draws/{draw_id}/participants/999",
            headers=second_auth_headers
        )
        
        assert response.status_code == 403


@pytest.mark.organizer
class TestUpdateDrawSchedule:
    """Test updating draw schedule"""
    
    def test_update_schedule_success(self, client, auth_headers, test_db):
        """Test organizer can update schedule"""
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
        
        draw_id = create_response.json()["drawId"]
        
        # Update schedule
        response = client.put(
            f"/api/v1/draws/{draw_id}/schedule",
            headers=auth_headers,
            json={"drawDate": "2025-12-31T20:00:00Z"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "2025-12-31" in data["drawDate"]
    
    def test_update_schedule_invalid_hour(self, client, auth_headers):
        """Test that schedule must be at exact hour"""
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
        
        draw_id = create_response.json()["drawId"]
        
        # Try to update with non-exact hour
        response = client.put(
            f"/api/v1/draws/{draw_id}/schedule",
            headers=auth_headers,
            json={"drawDate": "2025-12-31T20:45:00Z"}
        )
        
        assert response.status_code == 422
        assert "exact hour" in str(response.json()).lower()
    
    def test_update_schedule_completed_draw(self, client, auth_headers, test_db):
        """Test that completed draw schedule cannot be updated"""
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
        
        draw_id = create_response.json()["drawId"]
        
        # Mark as completed
        draw = test_db.query(Draw).filter(Draw.id == draw_id).first()
        draw.status = DrawStatus.COMPLETED.value
        test_db.commit()
        
        # Try to update
        response = client.put(
            f"/api/v1/draws/{draw_id}/schedule",
            headers=auth_headers,
            json={"drawDate": "2025-12-31T20:00:00Z"}
        )
        
        assert response.status_code == 400
        assert "completed" in response.json()["detail"].lower()


@pytest.mark.organizer
class TestExecuteDraw:
    """Test manual draw execution"""
    
    def test_execute_draw_success(self, client, auth_headers, test_db):
        """Test successful draw execution"""
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
        
        draw_id = create_response.json()["drawId"]
        invite_code = create_response.json()["inviteCode"]
        
        # Add 2 more participants (total 3)
        client.post(f"/api/v1/draws/join/{invite_code}", json={"firstName": "P1", "lastName": "Test", "email": "p1@test.com"})
        client.post(f"/api/v1/draws/join/{invite_code}", json={"firstName": "P2", "lastName": "Test", "email": "p2@test.com"})
        
        # Execute draw
        response = client.post(
            f"/api/v1/draws/{draw_id}/execute",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        
        # Verify status changed to IN_PROGRESS
        draw = test_db.query(Draw).filter(Draw.id == draw_id).first()
        assert draw.status == DrawStatus.IN_PROGRESS.value
    
    def test_execute_draw_min_participants(self, client, auth_headers):
        """Test that minimum 3 participants required"""
        # Create draw with only organizer
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
        
        # Try to execute with only 1 participant
        response = client.post(
            f"/api/v1/draws/{draw_id}/execute",
            headers=auth_headers
        )
        
        assert response.status_code == 400
        assert "minimum 3 participants" in response.json()["detail"].lower()
    
    def test_execute_draw_already_completed(self, client, auth_headers, test_db):
        """Test that completed draw cannot be executed again"""
        # Create draw with 3 participants
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
        
        # Mark as completed
        draw = test_db.query(Draw).filter(Draw.id == draw_id).first()
        draw.status = DrawStatus.COMPLETED.value
        test_db.commit()
        
        # Try to execute
        response = client.post(
            f"/api/v1/draws/{draw_id}/execute",
            headers=auth_headers
        )
        
        assert response.status_code == 400
        assert "already completed" in response.json()["detail"].lower()
    
    def test_execute_draw_non_organizer(self, client, auth_headers, second_auth_headers):
        """Test that non-organizer cannot execute draw"""
        # User 1 creates draw with 3 participants
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
        
        # Add 2 more participants
        client.post(f"/api/v1/draws/join/{invite_code}", json={"firstName": "P1", "lastName": "Test", "email": "p1@test.com"})
        client.post(f"/api/v1/draws/join/{invite_code}", json={"firstName": "P2", "lastName": "Test", "email": "p2@test.com"})
        
        # User 2 tries to execute
        response = client.post(
            f"/api/v1/draws/{draw_id}/execute",
            headers=second_auth_headers
        )
        
        assert response.status_code == 403

