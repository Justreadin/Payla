# routers/profile_router.py

from datetime import datetime, timedelta, timezone
import logging
import traceback

import cloudinary
import cloudinary.uploader
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.auth import get_current_user
from app.core.config import settings
from app.core.firebase import db
from app.core.subscription import require_silver
from app.models.profile_model import ProfileUpdateRequest
from app.models.user_model import User
from app.utils.name_match import match_name
from app.core.payla_urls import paylink_url


logger = logging.getLogger("payla")

router = APIRouter(prefix="/profile", tags=["Profile"])


# ─── CLOUDINARY CONFIGURATION ───
cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True,
)


# =============================
# GET PROFILE
# =============================
@router.get("/", response_model=dict)
async def get_profile(
    current_user: User | None = Depends(get_current_user),
):
    if current_user is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
        )

    user_ref = db.collection("users").document(current_user.id)
    user_doc = user_ref.get()

    if not user_doc.exists:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    profile = user_doc.to_dict() or {}

    # ── Normalize invoice fee preference for older records ──
    fee_payer = profile.get("default_invoice_fee_payer")
    if fee_payer not in ("merchant", "client"):
        profile["default_invoice_fee_payer"] = "merchant"

    # ── Normalize bank-confirmation state ──
    status = profile.get("bank_confirmation_status")
    if status not in ("matched", "mismatch", "pending", "failed"):
        profile["bank_confirmation_status"] = "pending"

    profile.setdefault("bank_confirmed_name", None)
    profile.setdefault("bank_confirmed_at", None)
    profile.setdefault("bank_confirmed_bank_name", None)
    profile.setdefault("bank_confirmed_account_last4", None)
    profile.setdefault("bank_confirmation_attempted_at", None)
    profile.setdefault("bank_confirmation_retry_count", 0)

    if profile.get("preferred_domain") not in ("ng", "vip"):
        profile["preferred_domain"] = "ng"

    # ── Entitlement block ──
    # Drives the plan card on the profile page. Uses the same method
    # as the dashboard, so the two pages always agree.
    profile["entitlement"] = {
        "has_silver": current_user.can_access_silver_features(),
        "plan": getattr(current_user, "plan", "free") or "free",
        "can_use_vip": current_user.can_access_silver_features(),
    }

    return profile


# =============================
# BANK CONFIRMATION STATUS
# =============================
@router.get("/bank-confirmation")
async def get_bank_confirmation(
    current_user: User | None = Depends(get_current_user),
):
    """
    Return the user's bank-confirmation state and the two names
    being compared. Powers the profile dashboard explanation card.
    """
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_ref = db.collection("users").document(current_user.id)
    user_doc = user_ref.get()

    if not user_doc.exists:
        raise HTTPException(status_code=404, detail="User not found")

    user = user_doc.to_dict() or {}

    status = user.get("bank_confirmation_status")
    if status not in ("matched", "mismatch", "pending", "failed"):
        status = "pending"

    return {
        "status": status,
        "entered_full_name": user.get("full_name"),
        "bank_confirmed_name": user.get("bank_confirmed_name"),
        "bank_confirmed_bank_name": user.get("bank_confirmed_bank_name"),
        "bank_confirmed_account_last4": user.get(
            "bank_confirmed_account_last4"
        ),
        "confirmed_at": user.get("bank_confirmed_at"),
        "attempted_at": user.get("bank_confirmation_attempted_at"),
        "signed_up_at": user.get("created_at"),
    }


# =============================
# UPDATE PROFILE
#
# Free and Silver users can both edit their identity fields. Only
# the logo upload is Silver — that's the branding feature.
# =============================
@router.post("/update")
async def update_profile(
    data: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
):
    if current_user is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
        )

    user_ref = db.collection("users").document(current_user.id)
    user_snapshot = user_ref.get()

    if not user_snapshot.exists:
        raise HTTPException(
            status_code=404,
            detail="User not found",
        )

    user_data = user_snapshot.to_dict() or {}

    update_data = data.model_dump(
        exclude_unset=True,
        exclude_none=True,
    )

    if not update_data:
        raise HTTPException(
            status_code=400,
            detail="No data provided",
        )

    # ── USERNAME CHANGE LOGIC ──
    requested_username = update_data.get("username")
    current_username = user_data.get("username", "")

    username_changing = (
        requested_username is not None
        and requested_username != current_username
    )

    if username_changing:
        last_change = user_data.get("last_username_change")

        if last_change is not None:
            if last_change.tzinfo is None:
                last_change = last_change.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            next_change_at = last_change + timedelta(days=365)

            if now < next_change_at:
                days_to_wait = max(
                    1,
                    (next_change_at - now).days,
                )

                raise HTTPException(
                    status_code=403,
                    detail=(
                        "Username can only be changed once a year. "
                        f"Please wait {days_to_wait} more days."
                    ),
                )

        update_data["last_username_change"] = datetime.now(timezone.utc)

    # ── VALIDATE INVOICE FEE PREFERENCE ──
    fee_payer = update_data.get("default_invoice_fee_payer")
    if fee_payer is not None and fee_payer not in ("merchant", "client"):
        raise HTTPException(
            status_code=422,
            detail="Invalid invoice fee preference.",
        )

     # ── VALIDATE PREFERRED DOMAIN ──
    requested_domain = update_data.get("preferred_domain")

    if requested_domain == "vip":
        if not current_user.can_access_silver_features():
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "silver_required",
                    "message": (
                        "The payla.vip domain is available on Payla Silver."
                    ),
                },
            )

    # ── BANK CONFIRMATION RE-MATCH ──
    full_name_changed = (
        "full_name" in update_data
        and update_data["full_name"] != user_data.get("full_name")
    )

    if full_name_changed:
        existing_bank_name = user_data.get("bank_confirmed_name")

        if existing_bank_name:
            new_status = match_name(
                update_data["full_name"],
                existing_bank_name,
            )
        else:
            new_status = "pending"

        update_data["bank_confirmation_status"] = new_status
        update_data["bank_confirmation_attempted_at"] = datetime.now(
            timezone.utc
        )
        update_data["bank_confirmation_retry_count"] = 0

    update_data["updated_at"] = datetime.now(timezone.utc)

    user_ref.update(update_data)

    # ── SYNC PAYLINK ──
    paylink_ref = db.collection("paylinks").document(current_user.id)

    if paylink_ref.get().exists:
        paylink_updates = {
            "updated_at": datetime.now(timezone.utc),
        }

        if "business_name" in update_data:
            paylink_updates["display_name"] = update_data["business_name"]

        if "username" in update_data:
            paylink_updates["username"] = update_data["username"]

        if "tagline" in update_data:
            paylink_updates["description"] = update_data["tagline"]

        if "preferred_domain" in update_data:
            new_domain = update_data["preferred_domain"]
            paylink_updates["preferred_domain"] = new_domain

            # Keep link_url in sync so the document is never stale.
            # The public route redirects based on preferred_domain,
            # but every other reader of link_url expects the real URL.
            doc_username = user_data.get("username") or ""
            if doc_username:
                paylink_updates["link_url"] = paylink_url(
                    doc_username, new_domain
                )

        for field in (
            "bank_confirmation_status",
            "bank_confirmed_name",
            "bank_confirmed_bank_name",
            "bank_confirmed_account_last4",
        ):
            if field in update_data:
                paylink_updates[field] = update_data[field]

        paylink_ref.update(paylink_updates)

    return {
        "message": "Profile updated successfully",
        "username_changed": username_changing,
        "default_invoice_fee_payer": (
            fee_payer
            if fee_payer is not None
            else user_data.get("default_invoice_fee_payer", "merchant")
        ),
        "bank_confirmation_status": update_data.get(
            "bank_confirmation_status",
            user_data.get("bank_confirmation_status", "pending"),
        ),
        "preferred_domain": update_data.get(
            "preferred_domain",
            user_data.get("preferred_domain", "ng"),
        ),
    }


# =============================
# UPLOAD LOGO — SILVER ONLY
# =============================
@router.post("/upload-logo")
async def upload_logo(
    file: UploadFile = File(...),
    current_user: User = Depends(require_silver),
):
    if current_user is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
        )

    allowed_types = {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
        "image/svg+xml",
    }

    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail="Invalid file type.",
        )

    try:
        file.file.seek(0)

        logger.info(
            "Attempting Cloudinary upload for user: %s",
            current_user.id,
        )

        upload_result = cloudinary.uploader.upload(
            file.file,
            folder="payla/logos",
            public_id=f"user_{current_user.id}_logo",
            overwrite=True,
            resource_type="auto",
        )

        logo_url = upload_result.get("secure_url")

        if not logo_url:
            logger.error(
                "Cloudinary response did not contain a secure URL."
            )
            raise RuntimeError(
                "Cloudinary did not return a secure URL."
            )

        db.collection("users").document(current_user.id).update({
            "logo_url": logo_url,
            "updated_at": datetime.now(timezone.utc),
        })

        logger.info(
            "Logo uploaded successfully for user: %s",
            current_user.id,
        )

        return {
            "message": "Logo uploaded successfully",
            "logo_url": logo_url,
        }

    except Exception as exc:
        logger.error(
            "Cloudinary upload failed for user %s: %s\n%s",
            current_user.id,
            str(exc),
            traceback.format_exc(),
        )

        error_message = str(exc)

        if "Errno -2" in error_message or "gaierror" in error_message:
            detail_msg = (
                "DNS/connection error. Check server internet access."
            )
        elif "Must supply" in error_message:
            detail_msg = (
                "Cloudinary configuration error. "
                "Check the environment credentials."
            )
        else:
            detail_msg = "Logo upload failed. Please try again."

        raise HTTPException(
            status_code=500,
            detail=detail_msg,
        ) from exc

    finally:
        await file.close()