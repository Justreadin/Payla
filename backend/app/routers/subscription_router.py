# routers/subscription_router.py → FINAL RECURRING (MONTHLY + YEARLY)
from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import get_current_user
from app.models.user_model import User
from app.core.firebase import db
from datetime import datetime, timezone, timedelta
import uuid
import httpx 

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
    # 1. Get fresh data from Firestore
    doc = db.collection("users").document(user.id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="User not found")
    
    data = doc.to_dict()
    from app.core.subscription import parse_firestore_datetime, has_active_subscription, is_trial_active
    
    # Create User object and attach dynamic fields
    current_user = User(**data)
    if "subscription_end" in data:
        setattr(current_user, "subscription_end", data["subscription_end"])

    now = datetime.now(timezone.utc)

    # --- 1. Check Presell Status ---
    if current_user.plan == "presell":
        p_end = parse_firestore_datetime(getattr(current_user, "presell_end_date", None))
        if p_end and p_end > now:
            return {
                "plan": "presell",
                "is_active": True,
                "trial_used": True,
                "message": f"Presell Active ({(p_end - now).days} days left)",
                "next_billing": p_end,
                "can_use_premium": True,
                "billing": "yearly"
            }

    # --- 2. Check Paid Subscription (Silver/Gold/Opal) ---
    # This uses your core.subscription logic (including 7-day grace period)
    is_paid_active = has_active_subscription(current_user)
    
    if is_paid_active:
        return {
            "plan": data.get("plan", "silver"), 
            "is_active": True,
            "trial_used": True,
            "message": f"Payla {data.get('plan', 'Silver').capitalize()} Active",
            "next_billing": data.get("subscription_end"),
            "can_use_premium": True,
            "billing": data.get("billing_cycle", "monthly")
        }

    # --- 3. Check Trial Logic ---
    trial_end_dt = parse_firestore_datetime(getattr(current_user, "trial_end_date", None))
    
    # Repair missing trial dates if necessary
    if not trial_end_dt:
        created_at = parse_firestore_datetime(data.get("created_at")) or now
        trial_end_dt = created_at + timedelta(days=14)
        db.collection("users").document(user.id).update({"trial_end_date": trial_end_dt})

    trial_active = trial_end_dt > now
    trial_used = trial_end_dt < now # If it's in the past, they've used it

    # If they aren't paying and trial is over, they are officially 'free'
    return {
        "plan": "free-trial" if trial_active else "free",
        "is_active": trial_active,
        "trial_used": trial_used,
        "trial_days_left": max(0, (trial_end_dt - now).days),
        "message": "Free trial active" if trial_active else "Subscription expired",
        "can_use_premium": trial_active,
        "billing": None
    }
    
@router.get("/plans")
async def get_plans():
    return {"plans": PLANS}


@router.post("/start/{plan_code}")
async def start_subscription(plan_code: str, user: User = Depends(get_current_user)):
    """
    Initiates a Paystack subscription flow.
    Checks if the user is already on a paid plan to prevent double billing.
    """
    # 1. Validate Plan Choice
    if plan_code not in PLANS:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid plan code. Choose from: {', '.join(PLANS.keys())}"
        )

    # 2. Check current status using your User model helper
    # We allow them to start if they are 'free' (even if trial is active)
    # but block if they already have a paid 'silver/gold' active subscription.
    if user.plan != "free" and user.is_subscription_active():
        raise HTTPException(
            status_code=400, 
            detail="You already have an active paid subscription."
        )

    plan_info = PLANS[plan_code]
    
    # 3. Generate a Unique Reference
    # Format: sub_[interval]_[userid]_[random]
    ref = f"sub_{plan_info['interval']}_{user.id}_{uuid.uuid4().hex[:8]}"

    # 4. Save Pending Transaction to Firestore
    # This allows us to verify the intent when the webhook hits
    pending_data = {
        "user_id": user.id,
        "email": user.email,
        "plan": "silver",  # The target tier
        "plan_code": plan_code,
        "interval": plan_info["interval"],
        "amount_ngn": plan_info["amount_ngn"],
        "reference": ref,
        "status": "pending",
        "created_at": datetime.now(timezone.utc),
        "metadata": {
            "user_id": user.id,
            "plan_code": plan_code,
            "billing_cycle": plan_info["interval"]
        }
    }

    try:
        db.collection("pending_subscriptions").document(ref).set(pending_data)
    except Exception as e:
        logger.error(f"Firestore Error saving pending sub: {e}")
        raise HTTPException(status_code=500, detail="Database error. Please try again.")

    # 5. Return Paystack Configuration to Frontend
    return {
        "success": True,
        "message": "Subscription initialized",
        "reference": ref,
        "amount_kobo": plan_info["amount_kobo"],
        "email": user.email,
        "public_key": settings.PAYSTACK_PUBLIC_KEY,
        "metadata": {
            "user_id": user.id,
            "plan": "silver",
            "plan_code": plan_code,
            "billing_cycle": plan_info["interval"],
            "type": "subscription_initial"
        }
    }

@router.get("/verify/{reference}")
async def verify_subscription(reference: str, user: User = Depends(get_current_user)):
    # 1. Check if this reference exists in pending_subscriptions
    pending_doc = db.collection("pending_subscriptions").document(reference).get()
    if not pending_doc.exists:
        raise HTTPException(status_code=404, detail="Transaction reference not found")
    
    pending_data = pending_doc.to_dict()
    
    # 2. Verify with Paystack API
    headers = {"Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"}
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://api.paystack.co/transaction/verify/{reference}", 
            headers=headers
        )
        resp_data = response.json()

    # 3. If successful, update the User's plan in Firestore
    if resp_data.get("status") and resp_data["data"]["status"] == "success":
        plan_code = pending_data["plan_code"]
        interval = pending_data["interval"]
        
        # Calculate new end date
        days = 30 if interval == "monthly" else 365
        new_end_date = datetime.now(timezone.utc) + timedelta(days=days)
        
        update_data = {
            "plan": "silver",
            "is_active": True,
            "subscription_end": new_end_date,
            "billing_cycle": interval,
            "subscription_id": resp_data["data"]["id"], # Paystack ID
            "last_payment_ref": reference
        }
        
        db.collection("users").document(user.id).update(update_data)
        db.collection("pending_subscriptions").document(reference).delete()
        
        return {
            "success": True, 
            "status": {
                "plan": "silver",
                "is_active": True,
                "message": "Payla Silver Active",
                "can_use_premium": True
            }
        }
    
    raise HTTPException(status_code=400, detail="Payment verification failed")