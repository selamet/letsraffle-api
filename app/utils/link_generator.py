"""
Invite code generator utility for creating unique, fun invite codes
"""

import random
from sqlalchemy.orm import Session


# Turkish words are written without special letters (ş, ç, ğ, ı, ö, ü) so codes stay URL- and
# keyboard-friendly, e.g. "sakar-rengeyigi-472", "obur-kardanadam-318".
TR_ADJECTIVES = [
    "neseli", "sakar", "uykucu", "obur", "tombik", "haylaz", "geveze", "telasli",
    "pofuduk", "zipzip", "miskin", "sasirmis", "kikirdayan", "havali", "utangac",
    "cilgin", "dalgin", "sirin", "afacan", "mizmiz", "keyifli",
]
TR_NOUNS = [
    "rengeyigi", "kardanadam", "noelbaba", "kurabiye", "mandalina", "kestane",
    "salep", "kizak", "yilbasiagaci", "penguen", "hindi", "corap", "zil",
    "yildiz", "hediye", "cuce", "kartopu", "simit", "boza", "pamuk",
]
EN_ADJECTIVES = [
    "jolly", "merry", "festive", "bright", "shiny", "sparkly",
    "cheerful", "happy", "cozy", "magical", "snowy", "frosty",
    "gleaming", "twinkling", "radiant", "dazzling", "glowing", "beaming",
]
EN_NOUNS = [
    "reindeer", "snowman", "gift", "star", "bell", "tree",
    "santa", "elf", "candy", "sleigh", "angel", "wreath",
    "snowflake", "gingerbread", "stocking", "ornament", "mistletoe", "carol",
]


def generate_invite_code(db: Session, max_retries: int = 5, language: str = "EN") -> str:
    """
    Generate a fun, memorable invite code using word combinations.
    Format: adjective-noun-number, in the draw's language
    (EN: jolly-reindeer-742, TR: sakar-rengeyigi-472).

    Raises:
        RuntimeError: If unable to generate unique code after max_retries
    """
    from app.models.draw import Draw

    turkish = (language or "").upper() == "TR"
    adjectives = TR_ADJECTIVES if turkish else EN_ADJECTIVES
    nouns = TR_NOUNS if turkish else EN_NOUNS

    for attempt in range(max_retries):
        adj = random.choice(adjectives)
        noun = random.choice(nouns)
        num = random.randint(100, 999)

        invite_code = f"{adj}-{noun}-{num}"

        existing = db.query(Draw).filter(Draw.invite_code == invite_code).first()

        if not existing:
            return invite_code

    raise RuntimeError(f"Failed to generate unique invite code after {max_retries} attempts")
