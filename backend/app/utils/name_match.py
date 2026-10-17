"""
Payla — Name matching utility.

Fuzzy comparison between a user's full name and a
bank-confirmed account name.

Rules:
  - Case-insensitive
  - Order-independent
  - Punctuation-insensitive
  - Match if 2+ meaningful name tokens overlap
    (meaningful = 3+ characters, to avoid initials)
  - Superset in either direction counts as a match

Returns one of: 'matched' | 'mismatch' | 'pending'
"""

import re
from typing import Literal

MatchStatus = Literal["matched", "mismatch", "pending"]

MIN_TOKEN_LENGTH = 3
MIN_OVERLAP = 2


def _normalize_tokens(name: str | None) -> list[str]:
    """
    Normalize a name into a list of lowercase tokens.
    Strips punctuation, collapses whitespace.

    Unicode-aware: keeps accented letters, numbers, and spaces.
    """
    if not name or not isinstance(name, str):
        return []

    # Keep only letters, numbers, and spaces
    cleaned = re.sub(r"[^\w\s]", "", name.lower(), flags=re.UNICODE)
    return [t for t in cleaned.split() if t]


def match_name(
    user_full_name: str | None,
    bank_account_name: str | None,
) -> MatchStatus:
    """
    Compare a user's full name to a bank account name.

    Returns:
        'matched'  — 2+ meaningful tokens overlap, or one is a subset
        'mismatch' — tokens exist but don't overlap meaningfully
        'pending'  — either side is empty or unusable
    """
    if not user_full_name or not bank_account_name:
        return "pending"

    user_tokens = _normalize_tokens(user_full_name)
    bank_tokens = _normalize_tokens(bank_account_name)

    if not user_tokens or not bank_tokens:
        return "pending"

    user_set = set(user_tokens)
    bank_set = set(bank_tokens)

    common = user_set & bank_set
    meaningful = {t for t in common if len(t) >= MIN_TOKEN_LENGTH}

    if len(meaningful) >= MIN_OVERLAP:
        return "matched"

    # Superset check — the entire shorter side is contained in the longer
    user_is_subset = user_set.issubset(bank_set)
    bank_is_subset = bank_set.issubset(user_set)

    if user_is_subset or bank_is_subset:
        return "matched"

    return "mismatch"


def is_verified(status: str | None) -> bool:
    """Convenience helper for callers that only need a boolean."""
    return status == "matched"