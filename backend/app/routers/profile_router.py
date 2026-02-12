# routers/profile_router.py → FINAL FIXED & BULLETPROOF (2025)
from datetime import datetime, timedelta, timezone
from app.core.subscription import require_silver
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel
from app.core.auth import get_current_user
from app.core.firebase import db
from app.models.user_model import User
from typing import Optional
import uuid
import cloudinary
import cloudinary.uploader
from app.core.config import settings
import logging

# Initialize logger
logger = logging.getLogger("payla")

router = APIRouter(prefix="/profile", tags=["Profile"])

# ─── CLOUDINARY CONFIGURATION ───
cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True
)


class ProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    business_name: Optional[str] = None
    username: Optional[str] = None
    phone_number: Optional[str] = None
    tagline: Optional[str] = None

    class Config:
        populate_by_name = True  # Pydantic v2 fix


# =============================
# GET PROFILE — FIXED
# =============================
@router.get("/", response_model=dict)
async def get_profile(current_user: Optional[User] = Depends(get_current_user)):
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_doc = db.collection("users").document(current_user.id).get()
    if not user_doc.exists:
        raise HTTPException(status_code=404, detail="User not found")

    return user_doc.to_dict()


# =============================
# UPDATE PROFILE — FIXED
# =============================
@router.post("/update")
async def update_profile(
    data: ProfileUpdateRequest,
    current_user: User = Depends(require_silver)
):
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_ref = db.collection("users").document(current_user.id)
    user_data = user_ref.get().to_dict()
    
    update_data = data.dict(exclude_unset=True, exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No data provided")

    # ── USERNAME CHANGE LOGIC (The "Once Per Year" Gate) ──
    requested_username = update_data.get("username")
    current_username = user_data.get("username")

    if requested_username and requested_username != current_username:
        # 1. Check Plan Eligibility (require_silver already handles most of this)
        # 2. Check Timing
        last_change = user_data.get("last_username_change")

        if last_change:
            # Firestore already returns aware UTC datetime
            one_year_ago = datetime.now(timezone.utc) - timedelta(days=365)

            if last_change > one_year_ago:
                days_to_wait = (
                    last_change + timedelta(days=365) - datetime.now(timezone.utc)
                ).days

                raise HTTPException(
                    status_code=403,
                    detail=f"Username can only be changed once a year. Please wait {days_to_wait} more days."
                )

        # Update the timestamp since username is changing
        update_data["last_username_change"] = datetime.now(timezone.utc)

    # ── EXECUTE UPDATE ──
    user_ref.update(update_data)

    # Sync Paylink (keep your existing paylink logic here)
    paylink_ref = db.collection("paylinks").document(current_user.id)
    if paylink_ref.get().exists:
        paylink_ref.update({
            "display_name": update_data.get("business_name") or user_data.get("business_name"),
            "username": requested_username or current_username,
            "updated_at": datetime.now(timezone.utc)
        })

    return {"message": "Profile updated successfully", "username_changed": requested_username != current_username}


# =============================
# UPLOAD LOGO — CLOUDINARY FIXED
# =============================
@router.post("/upload-logo")
async def upload_logo(
    file: UploadFile = File(...),
    current_user: User = Depends(require_silver)
):
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Debug Config (Check if Env Vars are actually loaded)
    logger.debug(f"DEBUG: CloudName: {settings.CLOUDINARY_CLOUD_NAME}")
    logger.debug(f"DEBUG: APIKey Loaded: {bool(settings.CLOUDINARY_API_KEY)}")

    allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/webp", "image/svg+xml"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Invalid file type.")

    try:
        # CRITICAL: Rewind the file pointer to the start
        file.file.seek(0)
        
        logger.info(f"📤 Attempting Cloudinary upload for user: {current_user.id}")

        upload_result = cloudinary.uploader.upload(
            file.file,
            folder="payla/logos",
            public_id=f"user_{current_user.id}_logo",
            overwrite=True,
            resource_type="auto"
        )

        logo_url = upload_result.get("secure_url")

        if not logo_url:
            # This logs the full response from Cloudinary if URL is missing
            logger.error(f"❌ Cloudinary Response missing URL. Full Result: {upload_result}")
            raise Exception("Cloudinary did not return a secure URL.")

        db.collection("users").document(current_user.id).update({
            "logo_url": logo_url,
            "updated_at": datetime.now(timezone.utc)
        })

        logger.info(f"✅ Successful Upload: {logo_url}")

        return {
            "message": "Logo uploaded successfully", 
            "logo_url": logo_url
        }

    except Exception as e:
        # Capture the full traceback for the logs
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"❌ CLOUDINARY CRASH: {str(e)}\n{error_details}")
        
        # Check for specific "General Error" triggers
        if "Errno -2" in str(e) or "gaierror" in str(e):
             detail_msg = "DNS/Connection Error: Check if your server has internet access."
        elif "Must supply" in str(e):
             detail_msg = "Config Error: Cloudinary credentials are missing from your environment variables."
        else:
             detail_msg = f"Cloud upload failed: {str(e)}"
             
        raise HTTPException(status_code=500, detail=detail_msg)