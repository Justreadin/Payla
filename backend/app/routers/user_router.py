from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from firebase_admin import firestore
from datetime import datetime, timezone

from app.core.auth import get_current_user
from app.core.subscription import require_silver
from app.models.user_model import User


db = firestore.client()
router = APIRouter(prefix="/users", tags=["Users"])


# ─── PUBLIC USER FIELD WHITELIST ───
# Only these fields may be returned by the unauthenticated
# GET /users/{user_id} route.
#
# Everything else is private by nature (email, phone, bank details)
# or internal (retry counters, subscription IDs, subscription state).
#
# Note: full_name is public (the user enters it themselves and it's
# often shown on the paylink page). bank_confirmed_name is private
# (retrieved from Paystack, not chosen by the user).
PUBLIC_USER_FIELDS = {
    "id",
    "username",
    "business_name",
    "full_name",
    "tagline",
    "logo_url",
    "plan",
    "created_at",
    "bank_confirmation_status",
}


def _project_public_user(user: dict) -> dict:
    """Strip a user document down to its public fields."""
    return {k: v for k, v in user.items() if k in PUBLIC_USER_FIELDS}


# =============================
# CREATE USER
# =============================
@router.post("/", response_model=User)
def create_user(
    user: User,
    current_user: User = Depends(get_current_user),
):
    """
    Create a user document.

    Only the authenticated user may create their own record,
    and the ID must match.
    """
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if str(current_user.id) != str(user.id):
        raise HTTPException(
            status_code=403,
            detail="You can only create your own user record.",
        )

    user_ref = db.collection("users").document(user.id)

    if user_ref.get().exists:
        raise HTTPException(status_code=400, detail="User already exists")

    user_dict = user.dict(by_alias=True)
    user_dict["created_at"] = datetime.now(timezone.utc)
    user_dict["updated_at"] = datetime.now(timezone.utc)

    user_ref.set(user_dict)

    return user_dict


# =============================
# GET USER BY ID (public, whitelisted)
# =============================
@router.get("/{user_id}")
def get_user(user_id: str):
    """
    Return a user's public profile.

    This route is intentionally unauthenticated so paylink pages can
    render the merchant's public info. Every field returned here is
    safe to expose.

    Private fields — including bank_confirmed_name, email, phone,
    and all internal Firestore state — are stripped.
    """
    user_doc = db.collection("users").document(user_id).get()

    if not user_doc.exists:
        raise HTTPException(status_code=404, detail="User not found")

    return _project_public_user(user_doc.to_dict() or {})


# =============================
# UPDATE USER DETAILS
# =============================
@router.put("/{user_id}", response_model=User)
def update_user(
    user_id: str,
    updates: dict,
    current_user: User = Depends(require_silver),
):
    """
    Update user details.

    Only the authenticated user may update their own record.

    Note: this is a raw field update, intended for internal tooling.
    User-facing profile updates should go through
    POST /api/profile/update, which enforces username-change rules,
    invoice fee preference validation, and bank confirmation
    re-matching.
    """
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if str(current_user.id) != str(user_id):
        raise HTTPException(
            status_code=403,
            detail="You can only update your own user record.",
        )

    user_ref = db.collection("users").document(user_id)

    if not user_ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent internal fields from being set directly.
    protected = {
        "bank_confirmed_name",
        "bank_confirmed_bank_name",
        "bank_confirmed_account_last4",
        "bank_confirmation_status",
        "bank_confirmed_at",
        "bank_confirmation_attempted_at",
        "bank_confirmation_retry_count",
        "subscription_id",
        "paystack_customer_code",
        "paystack_subaccount_code",
        "last_username_change",
        "created_at",
    }

    for field in protected:
        updates.pop(field, None)

    updates["updated_at"] = datetime.now(timezone.utc)
    user_ref.update(updates)

    return _project_public_user(user_ref.get().to_dict() or {})


# =============================
# ADMIN-ONLY ROUTES
# =============================
# These are administrative. They must be gated by an internal
# auth check (API key, service token, or admin role) before being
# re-enabled.
#
# The DELETE route is commented out because, as written, anyone
# could delete any user by ID.
#
# The LIST route is commented out because it streamed every user
# document in the database with no authentication — a full data
# dump.

# @router.delete("/{user_id}")
# def delete_user(user_id: str, admin=Depends(require_admin)):
#     user_ref = db.collection("users").document(user_id)
#     if not user_ref.get().exists:
#         raise HTTPException(status_code=404, detail="User not found")
#     user_ref.delete()
#     return {"message": "User deleted successfully"}

# @router.get("/")
# def list_users(admin=Depends(require_admin)):
#     users = []
#     docs = db.collection("users").stream()
#     for doc in docs:
#         users.append(_project_public_user(doc.to_dict() or {}))
#     return users