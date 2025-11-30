"""
Draw date utility functions for timezone handling and validation
"""

from datetime import datetime, timezone
from typing import Optional

# Timezone support - use zoneinfo (Python 3.9+) or fallback
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo


def normalize_and_validate_draw_date(
    draw_date: Optional[datetime],
    language: str
) -> Optional[datetime]:
    """
    Normalize draw_date timezone and validate for database storage.
    
    Important: Server runs in UTC. User-submitted dates without timezone are interpreted
    based on draw language:
    - TR draw: Treat as Europe/Istanbul (Turkey local time), then convert to UTC
    - EN draw: Treat as UTC (server timezone), no conversion needed
    
    Process:
    - If timezone-aware is None: Assign timezone based on language (TR→Europe/Istanbul, EN→UTC)
    - If timezone-aware is set: Use as-is, then convert to UTC
    - Always returns UTC datetime for database storage (server timezone)
    - Validates that date is in future (UTC), same year (UTC), and exact hour
    
    Args:
        draw_date: Datetime to normalize and validate (can be None)
        language: Language code ('TR' or 'EN')
                   - TR: timezone-naive dates treated as Europe/Istanbul
                   - EN: timezone-naive dates treated as UTC
        
    Returns:
        UTC datetime ready for database storage, or None
        
    Raises:
        ValueError: If validation fails (past date, wrong year, not exact hour)
    """
    if draw_date is None:
        return None
    
    now = datetime.now(timezone.utc)
    
    # If timezone-aware is None, assign timezone based on language
    if draw_date.tzinfo is None:
        if language.upper() == 'TR':
            # TR draw: Treat as Europe/Istanbul (Turkey local time)
            draw_date = draw_date.replace(tzinfo=ZoneInfo("Europe/Istanbul"))
        else:
            # EN draw: Treat as UTC (server timezone)
            draw_date = draw_date.replace(tzinfo=timezone.utc)
    
    # Convert to UTC (database stores in UTC)
    draw_date = draw_date.astimezone(timezone.utc)
    
    if draw_date <= now:
        raise ValueError("drawDate must be in the future")
    
    if draw_date.year != now.year:
        raise ValueError(f"drawDate must be in the current year ({now.year})")
    
    if draw_date.minute != 0 or draw_date.second != 0:
        raise ValueError("drawDate must be at exact hour (e.g., 13:00, not 13:33)")
    
    return draw_date

