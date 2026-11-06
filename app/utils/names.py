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
