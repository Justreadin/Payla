from fastapi import APIRouter, Depends
from datetime import datetime, timezone

from app.core.firebase import db
from app.core.auth import get_current_user
from app.core.analytics import get_paylink_analytics
from app.core.subscription import require_silver   # ← ADD THIS
from app.models.user_model import User
from google.cloud.firestore_v1.base_query import FieldFilter
router = APIRouter(prefix="/dashboard/analytics", tags=["Analytics"])

async def fetch_full_analytics(current_user: User):
    user_id = current_user.id
    username = current_user.username  # We need this to check both possibilities

    # 1. Fetch the Paylink document
    # Using user_id as document ID is standard in your setup
    paylink_ref = db.collection("paylinks").document(user_id)
    paylink_doc = paylink_ref.get()
    
    if not paylink_doc.exists:
        return {
            "total_received": 0,
            "total_transactions": 0,
            "success_rate": "0%",
            "page_views": 0
        }

    # 2. Fetch Transactions
    # We check for both user_id or username to be safe
    txns_query = db.collection("paylink_transactions").where(
        filter=FieldFilter("paylink_id", "in", [user_id, username])
    ).stream()

    total_received = 0.0
    successful_txns = 0
    total_attempts = 0

    for t in txns_query:
        data = t.to_dict()
        total_attempts += 1
        
        # Check for successful status (Paystack 'success' or your internal 'paid')
        if data.get("status") in ["success", "paid"]:
            successful_txns += 1
            # Ensure we handle both 'amount' and 'amount_paid' keys
            amount = data.get("amount_paid") or data.get("amount") or 0
            total_received += float(amount)

    # 3. Calculate Success Rate
    success_rate = 0
    if total_attempts > 0:
        success_rate = round((successful_txns / total_attempts) * 100, 1)

    if total_received == 0 and current_user.total_earned > 0:
        total_received = current_user.total_earned
    
    # 4. Get Click/View Data
    analytics_data = get_paylink_analytics(user_id)

    return {
        "total_received": total_received,
        "total_transactions": successful_txns,
        "success_rate": f"{success_rate}%",
        "page_views": analytics_data.get("page_views", 0),
        "transfer_clicks": analytics_data.get("transfer_clicks", 0),
        "daily_page_views": analytics_data.get("daily_page_views", {}),
        "last_updated": datetime.now(timezone.utc).isoformat()
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
