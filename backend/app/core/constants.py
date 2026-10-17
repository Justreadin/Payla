# app/core/constants.py
"""
Business constants shared across Payla modules.

Values that are business rules rather than configuration belong here.
Environment-tunable values belong in app/core/config.py instead.
"""

import re

# ============================================================
# FOUNDING OFFER
# ============================================================

# Total slots in the founding offer. Fixed by the offer itself and
# never changes.
FOUNDING_LIMIT = 200

# How long a founding member's complimentary Silver lasts.
FOUNDING_TRIAL_DAYS = 365

# How long a founding slot is reserved during a subscription checkout
# before it expires and is released.
FOUNDING_RESERVATION_HOURS = 24


# ============================================================
# USERNAME RULES
# ============================================================

# The single source of truth for username format across signup,
# onboarding, paylink editing, and public URL routing.
#
# 3-20 characters, lowercase letters, digits, hyphens, underscores.
# Case is normalized by the callers before validation.
USERNAME_PATTERN = re.compile(r"^[a-z0-9_-]{3,20}$")

USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 20

# Usernames that must never be issued to a user because they would
# collide with application routes, brand names, or reserved paths.
RESERVED_USERNAMES = frozenset({
    "admin",
    "api",
    "dashboard",
    "founding",
    "help",
    "login",
    "me",
    "onboarding",
    "payla",
    "register",
    "settings",
    "signup",
    "support",
    "system",
})

# Substrings that must never appear in a username. Checked against
# the lowercased username.
INAPPROPRIATE_WORDS = frozenset({
    "bitch",
    "cunt",
    "fuck",
    "nigga",
    "nigger",
    "shit",
})