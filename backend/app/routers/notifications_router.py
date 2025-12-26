from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timedelta, timezone

from app.core.firebase import db
from app.core.auth import get_current_user
from app.models.user_model import User
from google.cloud.firestore_v1.base_query import FieldFilter
router = APIRouter(prefix="/dashboard/notifications", tags=["Notifications"])


@router.get("/")
async def get_notifications(current_user: User = Depends(get_current_user)):
    if current_user is None:
        raise HTTPException(401, "Authentication required")

    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)

    notifs_query = (
        db.collection("notifications")
        .where(filter=FieldFilter("user_id", "==", current_user.id))
        .where(filter=FieldFilter("created_at", ">=", seven_days_ago))
        .order_by(filter=FieldFilter("created_at", direction="DESCENDING"))
        .limit(10)
        .stream()
    )

    return [{"id": n.id, **n.to_dict()} for n in notifs_query]



@router.patch("/{notif_id}/read")
async def mark_notification_read(notif_id: str, current_user: User = Depends(get_current_user)):
    ref = db.collection("notifications").document(notif_id)
    doc = ref.get()

    if not doc.exists or doc.to_dict().get("user_id") != current_user.id:
        raise HTTPException(404, "Notification not found")

    ref.update({
        "read": True,
        "read_at": datetime.now(timezone.utc)
    })

    return {"message": "Marked as read"}
