# routers/onboarding.py

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from google.cloud.firestore_v1.base_query import FieldFilter

from app.core.auth import get_current_user, onboarding_guard
from app.core.firebase import db
from app.core.paystack import create_paystack_subaccount
from app.models.onboarding_model import OnboardingPayload
from app.models.user_model import User
from app.routers.payout_router import resolve_account_name
from app.services.layla_service import LaylaOnboardingService
from app.core.constants import USERNAME_PATTERN
from app.core.payla_urls import paylink_url


logger = logging.getLogger("payla")

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])


def normalize_username(value: str) -> str:
    return value.strip().lower()


def validate_username_format(username: str) -> None:
    if not USERNAME_PATTERN.fullmatch(username):
        raise HTTPException(
            status_code=400,
            detail=(
                "Username must be 3-20 characters using lowercase "
                "letters, numbers, hyphens, or underscores"
            ),
        )


def username_is_valid_for_user(username: str, user_id: str) -> bool:
    """
    Check the users and paylinks collections.

    Existing records belonging to this user are allowed.
    Records belonging to other users are conflicts.
    """
    user_docs = (
        db.collection("users")
        .where(filter=FieldFilter("username", "==", username))
        .get()
    )

    for doc in user_docs:
        if doc.id != user_id:
            return False

    paylink_docs = (
        db.collection("paylinks")
        .where(filter=FieldFilter("username", "==", username))
        .get()
    )

    for doc in paylink_docs:
        doc_data = doc.to_dict() or {}

        if doc_data.get("user_id") != user_id:
            return False

    return True


@router.get("/me", response_model=User)
async def get_current_onboarding_user(
    user: User = Depends(get_current_user),
):
    """
    Return the authenticated user's onboarding information.

    Presell lookup and username assignment have been removed.
    """
    return user


@router.post("/", response_model=User)
async def complete_onboarding(
    payload: OnboardingPayload,
    user: User = Depends(onboarding_guard),
):
    if getattr(user, "onboarding_complete", False):
        raise HTTPException(
            status_code=400,
            detail="Onboarding already completed",
        )

    username = normalize_username(payload.username)
    now = datetime.now(timezone.utc)

    # 1. Validate username format.
    validate_username_format(username)

    # 2. Check username availability on the server.
    if not username_is_valid_for_user(username, user.id):
        raise HTTPException(
            status_code=400,
            detail="Username already taken",
        )

    # 3. Verify the payout account.
    # Preserve HTTP errors from resolve_account_name so temporary
    # provider failures are not misreported as invalid account details.
    try:
        resolved = await resolve_account_name(
            payload.payout_bank,
            payload.payout_account_number,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Unexpected payout verification error for user %s",
            user.id,
        )
        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to verify your payout account right now. "
                "Please try again."
            ),
        )

    if not isinstance(resolved, dict) or not resolved.get("account_name"):
        raise HTTPException(
            status_code=502,
            detail=(
                "The payout verification provider returned "
                "an incomplete response."
            ),
        )

    account_name = resolved["account_name"]

    # 4. Create the Paystack subaccount.
    # The helper returns None on failure, so check its result.
    try:
        subaccount_code = await create_paystack_subaccount(
            business_name=account_name,
            bank_code=payload.payout_bank,
            account_number=payload.payout_account_number,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "Unexpected Paystack subaccount error for user %s",
            user.id,
        )
        raise HTTPException(
            status_code=502,
            detail=(
                "Unable to set up your payout account right now. "
                "Please try again."
            ),
        )

    if not subaccount_code:
        raise HTTPException(
            status_code=502,
            detail=(
                "Paystack could not set up your payout account. "
                "Please try again later."
            ),
        )

    # 5. Prepare the user update.
    business_name = (
        payload.business_name.strip()
        or user.full_name
        or account_name
    ).title()

    update_data = {
        "username": username,
        "payout_bank": payload.payout_bank,
        "payout_account_number": payload.payout_account_number,
        "payout_account_name": account_name,
        "payout_bank_name": resolved.get("bank_name", "Unknown Bank"),
        "payout_verified": True,
        "business_name": business_name,
        "onboarding_complete": True,
        "updated_at": now,

        # Onboarding grants only permanent Free.
        "plan": "free",
        "subscription_status": "inactive",
        "trial_end_date": None,
        "presell_end_date": None,
        "subscription_end": None,

        # Required for creator payment routing.
        "paystack_subaccount_code": subaccount_code,
    }

    # 6. Update the user document.
    user_ref = db.collection("users").document(user.id)
    user_ref.update(update_data)

    # 7. Create or update the user's paylink.
    paylink_ref = db.collection("paylinks").document(user.id)
    existing_paylink = paylink_ref.get()
    existing_data = existing_paylink.to_dict() or {}

    paylink_data = {
        "user_id": user.id,
        "username": username,
        "display_name": business_name,
        "paystack_subaccount_code": subaccount_code,
        "description": "Your Payment Identity.",
        "currency": "NGN",
        "active": True,
        "link_url": paylink_url(username),
        "preferred_domain": "ng",
        "total_received": existing_data.get("total_received", 0.0),
        "total_transactions": existing_data.get("total_transactions", 0),
        "created_at": (
            existing_data.get("created_at", now)
            if existing_paylink.exists
            else now
        ),
        "updated_at": now,
    }

    if existing_paylink.exists:
        paylink_ref.update(paylink_data)
    else:
        paylink_ref.set(paylink_data)

    # 8. Retrieve the updated user.
    updated_doc = user_ref.get()

    if not updated_doc.exists:
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve the updated user profile.",
        )

    user_data = updated_doc.to_dict() or {}
    user_data["_id"] = user.id

    fresh_user = User(**user_data)

    # 9. Send the welcome message.
    # A messaging failure must not undo completed onboarding.
    try:
        layla = LaylaOnboardingService()
        layla.send_immediate_welcome(fresh_user)
    except Exception:
        logger.exception(
            "Failed to send onboarding welcome message for user %s",
            user.id,
        )

    return fresh_user


@router.get("/validate-username")
async def validate_username(
    username: str = Query(...),
    current_user_id: str | None = Query(
        default=None,
        description="Optional user ID to exclude from availability checks",
    ),
):
    """
    Preliminary username availability check.

    current_user_id is only a client-supplied exclusion hint, not proof
    of identity. The authenticated onboarding route performs its own
    authoritative availability check.
    """
    username = normalize_username(username)

    try:
        validate_username_format(username)
    except HTTPException as exc:
        return {
            "available": False,
            "message": exc.detail,
        }

    user_docs = (
        db.collection("users")
        .where(filter=FieldFilter("username", "==", username))
        .get()
    )

    for doc in user_docs:
        if not current_user_id or doc.id != current_user_id:
            return {
                "available": False,
                "message": "Username already taken",
            }

    paylink_docs = (
        db.collection("paylinks")
        .where(filter=FieldFilter("username", "==", username))
        .get()
    )

    for doc in paylink_docs:
        doc_data = doc.to_dict() or {}

        if (
            not current_user_id
            or doc_data.get("user_id") != current_user_id
        ):
            return {
                "available": False,
                "message": "Username already taken",
            }

    return {
        "available": True,
        "message": "Username is available",
    }