# routers/profile_router.py → FINAL FIXED & BULLETPROOF (2025)
from datetime import datetime
from app.core.subscription import require_silver
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from app.core.auth import get_current_user
from app.core.firebase import db
from app.models.user_model import User
from typing import Optional
import os
import shutil
import uuid

router = APIRouter(prefix="/profile", tags=["Profile"])

# Directory to store uploaded logos
UPLOAD_DIR = "uploads/logos"
os.makedirs(UPLOAD_DIR, exist_ok=True)


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

    update_data = data.dict(exclude_unset=True, exclude_none=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No data provided")

    # Update the user's profile
    db.collection("users").document(current_user.id).update(update_data)

    # -------------------------
    # Update corresponding paylink
    # -------------------------
    paylink_ref = db.collection("paylinks").document(current_user.id)
    paylink_doc = paylink_ref.get()
    if paylink_doc.exists:
        paylink_data = paylink_doc.to_dict()
        
        # Determine new display_name and description
        new_display_name = update_data.get("business_name") or current_user.full_name
        new_description = update_data.get("tagline") or paylink_data.get("description") or "Fast, secure payments via Payla"
        
        paylink_ref.update({
            "display_name": new_display_name,
            "description": new_description,
            "updated_at": datetime.utcnow()
        })

    return {"message": "Profile updated successfully and paylink synced"}



# =============================
# UPLOAD LOGO — FIXED
# =============================
@router.post("/upload-logo")
async def upload_logo(
    file: UploadFile = File(...),
    current_user: User = Depends(require_silver)
):
    if current_user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")

    if file.content_type not in ["image/jpeg", "image/jpg", "image/png", "image/webp", "image/svg+xml"]:
        raise HTTPException(status_code=400, detail="Invalid file type. Only images allowed.")

    try:
        file_ext = file.filename.split(".")[-1].lower()
        if file_ext not in ["jpg", "jpeg", "png", "webp", "svg"]:
            raise HTTPException(status_code=400, detail="Invalid file extension")

        filename = f"{current_user.id}_{uuid.uuid4().hex[:12]}.{file_ext}"
        file_path = os.path.join(UPLOAD_DIR, filename)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        logo_url = f"/uploads/logos/{filename}"
        db.collection("users").document(current_user.id).update({"logo_url": logo_url})

        return {"message": "Logo uploaded successfully", "logo_url": logo_url}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")