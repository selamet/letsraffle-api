"""
Helpers for exposing participant names publicly without leaking full identities.
"""


def public_display_name(first_name: str, last_name: str) -> str:
    """
    Return the first name plus the last-name initial (e.g. "Ayşe D.").

    Used on public endpoints where the full surname and email must stay private.
    """
    first = (first_name or "").strip()
    last = (last_name or "").strip()
    if not last:
        return first
    return f"{first} {last[0].upper()}."


def draw_display_name(invite_code: str) -> str:
    """
    Turn an invite code into a readable draw name: "miskin-penguen-53" -> "Miskin Penguen No. 53".

    Codes without a trailing number are simply title-cased.
    """
    parts = [part for part in (invite_code or "").split("-") if part]
    if not parts:
        return ""
    number = parts.pop() if parts[-1].isdigit() and len(parts) > 1 else None
    name = " ".join(part.capitalize() for part in parts)
    return f"{name} No. {number}" if number else name
