"""
One-off: mark every draw that is not completed yet as completed.

Draws marked this way are treated as already held: the scheduler no longer
executes them and they can no longer be deleted.

Usage (uses the same POSTGRES_* settings as the API):
    python -m scripts.mark_all_draws_completed            # dry run, prints what would change
    python -m scripts.mark_all_draws_completed --apply    # performs the update

Equivalent SQL:
    UPDATE draws SET status = 'completed', updated_at = now() WHERE status <> 'completed';
"""
import sys
from collections import Counter

from app.models.database import SessionLocal
from app.models.draw import Draw, DrawStatus


def main(apply: bool) -> None:
    db = SessionLocal()
    try:
        pending = db.query(Draw).filter(Draw.status != DrawStatus.COMPLETED.value).all()
        by_status = Counter(d.status for d in pending)
        total = db.query(Draw).count()
        print(f"Draws total: {total}, not completed: {len(pending)} {dict(by_status)}")
        if not apply:
            print("Dry run - nothing changed. Re-run with --apply to update.")
            return
        for d in pending:
            d.status = DrawStatus.COMPLETED.value
        db.commit()
        print(f"Updated {len(pending)} draws to '{DrawStatus.COMPLETED.value}'.")
    finally:
        db.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv[1:])
