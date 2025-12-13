from fastapi import APIRouter, Depends
from datetime import datetime, timezone

from app.core.firebase import db
from app.core.auth import get_current_user
from app.core.analytics import get_paylink_analytics
from app.core.subscription import require_silver   # ← ADD THIS
from app.models.user_model import User

router = APIRouter(prefix="/dashboard/analytics", tags=["Analytics"])


async def fetch_full_analytics(current_user: User):
    user_id = current_user.id

    # --------------------------
    # 1. Get Paylink
    # --------------------------
    doc = db.collection("paylinks").document(user_id).get()
    if not doc.exists:
        return {
            "total_received": 0,
            "total_transactions": 0,
            "total_requested": 0,
            "page_views": 0,
            "transfer_clicks": 0,
            "daily_page_views": {},
            "daily_transfer_clicks": {}
        }

    paylink = doc.to_dict()
    paylink_id = doc.id

    # --------------------------
    # 2. Fetch transactions
    # --------------------------
    txns = db.collection("paylink_transactions").where("paylink_id", "==", paylink_id).stream()

    total_received = 0.0
    total_transactions = 0
    total_requested = 0.0

    for t in txns:
        data = t.to_dict()
        total_requested += float(data.get("amount_requested", 0))
        if data.get("status") == "success":
            total_transactions += 1
            total_received += float(data.get("amount_paid", 0))

    # --------------------------
    # 3. Fetch analytics counters
    # --------------------------
    analytics = get_paylink_analytics(paylink_id)

    return {
        "total_received": total_received,
        "total_transactions": total_transactions,
        "total_requested": total_requested,
        "page_views": analytics.get("page_views", 0),
        "transfer_clicks": analytics.get("transfer_clicks", 0),
        "daily_page_views": analytics.get("daily_page_views", {}),
        "daily_transfer_clicks": analytics.get("daily_transfer_clicks", {}),
        "last_updated": analytics.get("last_updated")
    }


# ------------------------------
# GET with trailing slash
# ------------------------------
@router.get("/")
async def get_analytics_slash(
    current_user: User = Depends(require_silver)  # ← ENFORCES TRIAL + SILVER ONLY
):
    return await fetch_full_analytics(current_user)


# ------------------------------
# GET without trailing slash
# ------------------------------
@router.get("")
async def get_analytics_no_slash(
    current_user: User = Depends(require_silver)  # ← SAME ENFORCEMENT
):
    return await fetch_full_analytics(current_user)
