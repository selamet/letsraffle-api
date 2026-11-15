"""
Print the .env line that sets the admin panel password.

Usage: python -m scripts.hash_admin_password
"""

import sys
from getpass import getpass

from app.models.user import User

MIN_LENGTH = 12


def main() -> int:
    password = getpass("Admin password: ")
    if len(password) < MIN_LENGTH:
        print(f"Password must be at least {MIN_LENGTH} characters.", file=sys.stderr)
        return 1
    if getpass("Repeat: ") != password:
        print("Passwords do not match.", file=sys.stderr)
        return 1

    print(f"ADMIN_PASSWORD_HASH='{User.hash_password(password)}'")
    print(
        "# Keep the single quotes: without them Docker Compose treats the $ signs as variables.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
