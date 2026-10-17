
"""Legacy trial cleanup.

Payla no longer uses expiring trials. This task intentionally does not change
user plans or grant paid access. It is safe to remove its scheduler entry once
all callers have been identified.
"""

import logging

logger = logging.getLogger("payla")


def check_expired_trials() -> int:
    """Compatibility no-op; permanent Free users are never auto-upgraded."""
    logger.info(
        "check_expired_trials skipped: trial expiration is disabled; "
        "Free remains Free until a verified subscription payment."
    )
    return 0
