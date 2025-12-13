# routers/subscription_router.py → FINAL RECURRING (MONTHLY + YEARLY)
from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import get_current_user
from app.models.user_model import User
from app.core.firebase import db
from datetime import datetime, timezone, timedelta
import uuid
from app.core.config import settings

router = APIRouter(prefix="/subscription", tags=["Subscription"])

# Pricing
PLANS = {
    "silver_monthly": {
        "name": "Payla Silver (Monthly)",
        "amount_ngn": 7500,
        "amount_kobo": 750000,
        "interval": "monthly",
        "description": "₦7,500 per month"
    },
    "silver_yearly": {
        "name": "Payla Silver (Yearly)",
        "amount_ngn": 75000,
        "amount_kobo": 7500000,
        "interval": "yearly",
        "description": "₦75,000 per year (Save ₦15,000!)"
    }
}

@router.get("/status")
async def get_status(user: User = Depends(get_current_user)):
    doc = db.collection("users").document(user.id).get()
    data = doc.to_dict()

    plan = data.get("plan", "free")
    trial_end = data.get("trial_end_date")

    # Active silver subscription
    if plan == "silver":
        return {
            "plan": "silver",
            "billing": data.get("billing_cycle", "monthly"),
            "is_active": True,
            "message": f"Payla Silver Active — Billed {data.get('billing_cycle', 'monthly')}",
            "next_billing": data.get("next_billing_date"),
            "can_use_premium": True
        }

    # Trial logic
    if not trial_end:
        trial_end_dt = datetime.now(timezone.utc) + timedelta(days=14)
        db.collection("users").document(user.id).update({
            "trial_end_date": trial_end_dt,
            "plan": "free"
        })
        days_left = 14
    else:
        # Convert to datetime safely
        if hasattr(trial_end, "to_datetime"):
            end_dt = trial_end.to_datetime()
        elif isinstance(trial_end, int):
            # Assume seconds timestamp
            end_dt = datetime.fromtimestamp(trial_end, tz=timezone.utc)
        elif isinstance(trial_end, float):
            # Some Firestore exports use float seconds
            end_dt = datetime.fromtimestamp(int(trial_end), tz=timezone.utc)
        else:
            end_dt = trial_end  # Already datetime

        # Compute days left
        days_left = max(0, (end_dt - datetime.now(timezone.utc)).days)

    is_active = days_left > 0

    return {
        "plan": "free",
        "is_active": is_active,
        "trial_days_left": days_left,
        "message": "Free trial active" if is_active else "Trial expired — Upgrade to continue",
        "can_use_premium": is_active
    }



@router.get("/plans")
async def get_plans():
    return {"plans": PLANS}


@router.post("/start/{plan_code}")
async def start_subscription(plan_code: str, user: User = Depends(get_current_user)):
    if plan_code not in PLANS:
        raise HTTPException(400, detail="Invalid plan")

    if user.plan == "silver":
        raise HTTPException(400, detail="Already subscribed")

    plan = PLANS[plan_code]
    ref = f"sub_{plan_code}_{user.id}_{uuid.uuid4().hex[:8]}"

    # Save pending subscription
    db.collection("pending_subscriptions").document(ref).set({
        "user_id": user.id,
        "email": user.email,
        "plan": "silver",
        "plan_code": plan_code,
        "amount": plan["amount_ngn"],
        "reference": ref,
        "status": "pending",
        "created_at": datetime.now(timezone.utc)
    })

    return {
        "success": True,
        "reference": ref,
        "amount_kobo": plan["amount_kobo"],
        "email": user.email,
        "public_key": settings.PAYSTACK_PUBLIC_KEY,
        "metadata": {
            "user_id": user.id,
            "plan": "silver",
            "plan_code": plan_code,
            "type": "subscription_initial"
        }
    }