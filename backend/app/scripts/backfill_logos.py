"""
Clear broken SVG data URLs from logo_url so the frontend falls back
to the initials renderer.

Run once:
    python -m scripts.clear_broken_logos
    python -m scripts.clear_broken_logos --dry-run
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

from app.core.firebase import db


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

logger = logging.getLogger("payla.clear_broken_logos")

# Any logo_url that begins with one of these prefixes was set by the
# avatar generator and renders as a black circle in the frontend.
BROKEN_PREFIXES = (
    "data:image/svg+xml;charset=utf-8,",
    "data:image/svg+xml;base64,",
)


def _is_broken(value) -> bool:
    if not isinstance(value, str):
        return False
    return any(value.startswith(prefix) for prefix in BROKEN_PREFIXES)


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    if dry_run:
        logger.info("Dry run — no writes will occur.")

    cleared = 0
    scanned = 0

    users_ref = db.collection("users")

    for doc in users_ref.stream():
        scanned += 1
        data = doc.to_dict() or {}

        if not _is_broken(data.get("logo_url")):
            continue

        if dry_run:
            logger.info("[dry-run] would clear logo_url on user %s", doc.id)
        else:
            users_ref.document(doc.id).update({
                "logo_url": None,
                "updated_at": datetime.now(timezone.utc),
            })
            logger.info("Cleared logo_url on user %s", doc.id)

        cleared += 1

    logger.info("Done. Scanned=%d Cleared=%d", scanned, cleared)
    return 0


if __name__ == "__main__":
    sys.exit(main())