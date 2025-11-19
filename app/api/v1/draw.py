import logging
from typing import Optional, List
from app.models import get_db, User
from sqlalchemy.orm import Session
from app.api.deps import get_current_user_optional, get_current_user
from app.schemas.draw import (
    ManualDrawCreate, ManualDrawResponse,
    DynamicDrawCreate, DynamicDrawResponse,
    DrawPublicInfo, ParticipantJoinRequest,
    DrawDetailResponse, ParticipantDetail, UpdateDrawSchedule,
    DrawListItem
)
from fastapi import APIRouter, Depends, HTTPException, status
from app.models.draw import Draw, DrawStatus, DrawType, Participant, Language
from app.utils.link_generator import generate_invite_code

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/draws/manual", response_model=ManualDrawResponse, status_code=status.HTTP_201_CREATED)
async def create_manual_draw(
        draw_data: ManualDrawCreate,
        db: Session = Depends(get_db),
        current_user: Optional[User] = Depends(get_current_user_optional)
):
    """
    Create a manual draw with specified participants.
    This endpoint allows the creation of a manual draw by providing participant details.
    The draw will be processed asynchronously.
    Parameters:
    - draw_data: ManualDrawCreate - The data required to create the manual draw, including
        participant details and requirements for address and phone number.
    - db: Session - The database session dependency.
    - current_user: Optional[User] - The currently authenticated user, if any.
    Returns:
    - ManualDrawResponse: The response containing the draw ID and success message.
    Raises:
    - HTTPException: If there is an error during draw creation or processing.
    """
    try:
        new_draw = Draw(
            creator_id=current_user.id if current_user else None,
            draw_type=DrawType.MANUAL.value,
            status=DrawStatus.IN_PROGRESS.value,
            require_address=draw_data.address_required,
            require_phone=draw_data.phone_number_required,
            draw_date=None,
            language=draw_data.language
        )
        db.add(new_draw)
        db.flush()

        participants_data = [
            Participant(
                draw_id=new_draw.id,
                first_name=p.first_name,
                last_name=p.last_name,
                email=p.email,
                address=p.address,
                phone=p.phone
            )
            for p in draw_data.participants
        ]
        db.bulk_save_objects(participants_data)
        db.commit()

        # from app.tasks.draw import process_manual_draw_task
        # process_manual_draw_task.delay(new_draw.id)

        logger.info(f"Manual draw created: draw_id={new_draw.id}, creator_id={new_draw.creator_id}")

        return ManualDrawResponse(
            success=True,
            message="Draw created successfully and is being processed.",
            draw_id=new_draw.id
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Error while creating draw {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error while creating draw: {str(e)}"
        )


@router.post("/draws/dynamic", response_model=DynamicDrawResponse, status_code=status.HTTP_201_CREATED)
async def create_dynamic_draw(
    draw_data: DynamicDrawCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a dynamic draw with a shareable invite code.
    
    - **Authentication Required:** Only authenticated users can create dynamic draws
    - The organizer is the first (and only) participant in the initial list
    - A unique invite_code is generated for others to join
    - Draw can be scheduled for a specific time (exact hour only) or executed manually later
    
    Parameters:
    - draw_data: DynamicDrawCreate - Draw settings and organizer information
    - db: Session - Database session dependency
    - current_user: User - Currently authenticated user (required)
    
    Returns:
    - DynamicDrawResponse: Contains draw ID and invite code
    
    Raises:
    - HTTPException: If there's an error during draw creation
    """
    try:
        invite_code = generate_invite_code(db)
        
        new_draw = Draw(
            creator_id=current_user.id,
            draw_type=DrawType.DYNAMIC.value,
            status=DrawStatus.ACTIVE.value,
            require_address=draw_data.address_required,
            require_phone=draw_data.phone_number_required,
            draw_date=draw_data.draw_date,
            invite_code=invite_code,
            language=draw_data.language
        )
        db.add(new_draw)
        db.flush()
        
        organizer = draw_data.participants[0]
        organizer_participant = Participant(
            draw_id=new_draw.id,
            first_name=organizer.first_name,
            last_name=organizer.last_name,
            email=organizer.email,
            address=organizer.address,
            phone=organizer.phone
        )
        db.add(organizer_participant)
        db.commit()
        
        logger.info(
            f"Dynamic draw created: draw_id={new_draw.id}, "
            f"creator_id={current_user.id}, invite_code={invite_code}"
        )
        
        return DynamicDrawResponse(
            success=True,
            message="Draw created successfully. Share the invite code with participants.",
            draw_id=new_draw.id,
            invite_code=invite_code
        )
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error while creating dynamic draw: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error while creating draw: {str(e)}"
        )


@router.get("/draws/join/{invite_code}", response_model=DrawPublicInfo)
async def get_draw_public_info(
    invite_code: str,
    db: Session = Depends(get_db)
):
    """
    Get public information about a draw using its invite code.
    
    - **No Authentication Required:** This is a public endpoint
    - Returns basic draw information for participants to view before joining
    - Does not expose sensitive information (creator details, participant details)
    
    Parameters:
    - invite_code: str - The unique invite code of the draw
    - db: Session - Database session dependency
    
    Returns:
    - DrawPublicInfo: Public draw information
    
    Raises:
    - HTTPException 404: If draw not found
    """
    draw = db.query(Draw).filter(Draw.invite_code == invite_code).first()
    
    if not draw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Draw not found"
        )
    
    participant_count = db.query(Participant).filter(
        Participant.draw_id == draw.id
    ).count()
    
    return DrawPublicInfo(
        id=draw.id,
        require_address=draw.require_address,
        require_phone=draw.require_phone,
        draw_date=draw.draw_date,
        status=draw.status,
        participant_count=participant_count,
        language=draw.language
    )


@router.post("/draws/join/{invite_code}", status_code=status.HTTP_201_CREATED)
async def join_draw(
    invite_code: str,
    participant_data: ParticipantJoinRequest,
    db: Session = Depends(get_db)
):
    """
    Join a draw using its invite code.
    
    - **No Authentication Required:** Anyone with the invite code can join
    - Email uniqueness is enforced (cannot join twice with same email)
    - Required fields are validated based on draw settings
    - Participant is immediately added to the draw
    
    Parameters:
    - invite_code: str - The unique invite code of the draw
    - participant_data: ParticipantJoinRequest - Participant information
    - db: Session - Database session dependency
    
    Returns:
    - Success message with participant info
    
    Raises:
    - HTTPException 404: If draw not found
    - HTTPException 400: If draw is not active
    - HTTPException 409: If email already registered in this draw
    - HTTPException 400: If required fields are missing
    """
    draw = db.query(Draw).filter(Draw.invite_code == invite_code).first()
    
    if not draw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Draw not found"
        )
    
    # Check if draw is active
    if draw.status != DrawStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Draw is not active. Current status: {draw.status}"
        )
    
    # Check email uniqueness in this draw
    existing_participant = db.query(Participant).filter(
        Participant.draw_id == draw.id,
        Participant.email == participant_data.email
    ).first()
    
    if existing_participant:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email is already registered for this draw"
        )
    
    # Validate required fields
    if draw.require_address:
        if not participant_data.address or not participant_data.address.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Address is required for this draw"
            )
    
    if draw.require_phone:
        if not participant_data.phone or not participant_data.phone.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phone number is required for this draw"
            )
    
    try:
        new_participant = Participant(
            draw_id=draw.id,
            first_name=participant_data.first_name,
            last_name=participant_data.last_name,
            email=participant_data.email,
            address=participant_data.address,
            phone=participant_data.phone
        )
        db.add(new_participant)
        db.commit()
        db.refresh(new_participant)
        
        logger.info(
            f"Participant joined draw: draw_id={draw.id}, "
            f"participant_id={new_participant.id}, email={participant_data.email}"
        )
        
        return {
            "success": True,
            "message": "Successfully joined the draw",
            "participantId": new_participant.id,
            "drawId": draw.id
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error while joining draw: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error while joining draw: {str(e)}"
        )


# Organizer Draw Management Endpoints

@router.get("/draws", response_model=List[DrawListItem])
async def get_draws_list(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get list of draws created by the authenticated user.
    
    - **Authentication Required:** Only authenticated users can access
    - Returns all draws created by the current user
    - Draws are sorted by creation date (newest first)
    - Includes participant count for each draw
    
    Parameters:
    - db: Session - Database session dependency
    - current_user: User - Currently authenticated user
    
    Returns:
    - List[DrawListItem]: List of draws created by the user
    """
    draws = (
        db.query(Draw)
        .filter(Draw.creator_id == current_user.id)
        .order_by(Draw.created_at.desc())
        .all()
    )
    
    draw_items = []
    for draw in draws:
        participant_count = db.query(Participant).filter(
            Participant.draw_id == draw.id
        ).count()
        
        draw_items.append(
            DrawListItem(
                id=draw.id,
                draw_type=draw.draw_type,
                status=draw.status,
                invite_code=draw.invite_code,
                participant_count=participant_count,
                created_at=draw.created_at,
                draw_date=draw.draw_date,
                language=draw.language
            )
        )
    
    logger.info(f"Draw list retrieved: user_id={current_user.id}, count={len(draw_items)}")
    
    return draw_items


@router.get("/draws/{draw_id}", response_model=DrawDetailResponse)
async def get_draw_detail(
    draw_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get draw details with participants list (organizer only).
    
    - **Authentication Required:** Only the organizer can access
    - Returns full draw information including all participants
    - Organizer can see all participant details
    
    Parameters:
    - draw_id: int - The draw ID
    - db: Session - Database session dependency
    - current_user: User - Currently authenticated user
    
    Returns:
    - DrawDetailResponse: Full draw details with participants
    
    Raises:
    - HTTPException 404: If draw not found
    - HTTPException 403: If user is not the organizer
    """
    draw = db.query(Draw).filter(Draw.id == draw_id).first()
    
    if not draw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Draw not found"
        )
    
    if draw.creator_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to access this draw"
        )
    
    participants = db.query(Participant).filter(
        Participant.draw_id == draw_id
    ).all()
    
    participant_details = [
        ParticipantDetail(
            id=p.id,
            first_name=p.first_name,
            last_name=p.last_name,
            email=p.email,
            address=p.address,
            phone=p.phone,
            created_at=p.created_at
        )
        for p in participants
    ]
    
    return DrawDetailResponse(
        id=draw.id,
        draw_type=draw.draw_type,
        status=draw.status,
        invite_code=draw.invite_code,
        require_address=draw.require_address,
        require_phone=draw.require_phone,
        draw_date=draw.draw_date,
        created_at=draw.created_at,
        language=draw.language,
        participants=participant_details
    )


@router.delete("/draws/{draw_id}/participants/{participant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_participant(
    draw_id: int,
    participant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete a participant from a draw (organizer only).
    
    - **Authentication Required:** Only the organizer can delete
    - Cannot delete if draw is completed
    - Cannot delete the organizer themselves
    
    Parameters:
    - draw_id: int - The draw ID
    - participant_id: int - The participant ID to delete
    - db: Session - Database session dependency
    - current_user: User - Currently authenticated user
    
    Raises:
    - HTTPException 404: If draw or participant not found
    - HTTPException 403: If user is not the organizer
    - HTTPException 400: If draw is completed or trying to delete organizer
    """
    draw = db.query(Draw).filter(Draw.id == draw_id).first()
    
    if not draw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Draw not found"
        )
    
    if draw.creator_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to modify this draw"
        )
    
    if draw.status == DrawStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete participants from a completed draw"
        )
    
    participant = db.query(Participant).filter(
        Participant.id == participant_id,
        Participant.draw_id == draw_id
    ).first()
    
    if not participant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Participant not found in this draw"
        )
    
    # Check if this is the organizer (first participant)
    first_participant = db.query(Participant).filter(
        Participant.draw_id == draw_id
    ).order_by(Participant.created_at).first()
    
    if participant.id == first_participant.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the organizer from the draw"
        )
    
    db.delete(participant)
    db.commit()
    
    logger.info(
        f"Participant deleted: participant_id={participant_id}, "
        f"draw_id={draw_id}, by_user={current_user.id}"
    )


@router.put("/draws/{draw_id}/schedule")
async def update_draw_schedule(
    draw_id: int,
    schedule_data: UpdateDrawSchedule,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update draw schedule date (organizer only).
    
    - **Authentication Required:** Only the organizer can update
    - Cannot update if draw is completed
    - Date must be in the future and at exact hour
    
    Parameters:
    - draw_id: int - The draw ID
    - schedule_data: UpdateDrawSchedule - New schedule data
    - db: Session - Database session dependency
    - current_user: User - Currently authenticated user
    
    Returns:
    - Success message with updated date
    
    Raises:
    - HTTPException 404: If draw not found
    - HTTPException 403: If user is not the organizer
    - HTTPException 400: If draw is completed
    """
    draw = db.query(Draw).filter(Draw.id == draw_id).first()
    
    if not draw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Draw not found"
        )
    
    if draw.creator_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to modify this draw"
        )
    
    if draw.status == DrawStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot update schedule of a completed draw"
        )
    
    draw.draw_date = schedule_data.draw_date
    db.commit()
    
    logger.info(
        f"Draw schedule updated: draw_id={draw_id}, "
        f"new_date={schedule_data.draw_date}, by_user={current_user.id}"
    )
    
    return {
        "success": True,
        "message": "Draw schedule updated successfully",
        "drawDate": draw.draw_date
    }


@router.post("/draws/{draw_id}/execute")
async def execute_draw(
    draw_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Manually trigger draw execution (organizer only).
    
    - **Authentication Required:** Only the organizer can execute
    - Cannot execute if draw is already completed
    - Minimum 3 participants required
    - Triggers the draw process asynchronously
    
    Parameters:
    - draw_id: int - The draw ID
    - db: Session - Database session dependency
    - current_user: User - Currently authenticated user
    
    Returns:
    - Success message
    
    Raises:
    - HTTPException 404: If draw not found
    - HTTPException 403: If user is not the organizer
    - HTTPException 400: If draw is completed or insufficient participants
    """
    draw = db.query(Draw).filter(Draw.id == draw_id).first()
    
    if not draw:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Draw not found"
        )
    
    if draw.creator_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to execute this draw"
        )
    
    if draw.status == DrawStatus.COMPLETED.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Draw is already completed"
        )
    
    participant_count = db.query(Participant).filter(
        Participant.draw_id == draw_id
    ).count()
    
    if participant_count < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Minimum 3 participants required. Current: {participant_count}"
        )
    
    # Update status to IN_PROGRESS
    draw.status = DrawStatus.IN_PROGRESS.value
    db.commit()
    
    # Trigger Celery task
    from app.tasks.draw import process_manual_draw_task
    process_manual_draw_task.delay(draw_id)
    
    logger.info(
        f"Draw execution triggered: draw_id={draw_id}, by_user={current_user.id}"
    )
    
    return {
        "success": True,
        "message": "Draw execution started. Results will be sent via email."
    }
