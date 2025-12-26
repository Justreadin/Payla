# routers/presell.py
import logging
import csv
import uuid
import hmac
import hashlib
import json
from datetime import datetime, timezone
from io import StringIO
from typing import Optional, Dict, Any
from firebase_admin import auth as firebase_auth

from fastapi import APIRouter, HTTPException, BackgroundTasks, Header, Request, status
from fastapi.responses import StreamingResponse
import httpx
from pydantic import BaseModel, EmailStr, validator
from google.cloud.firestore_v1.base_query import FieldFilter
from app.core.firebase import db
from app.core.config import settings
from app.core.notifications import create_notification
from app.utils.presell_email import send_layla_email
from app.services.email_service import send_presell_reward_email

logger = logging.getLogger("payla.presell")

router = APIRouter(prefix="/presell", tags=["Presell"])


# ===== MODELS =====
class LockYearRequest(BaseModel):
    fullName: str
    email: EmailStr
    expectations: Optional[str] = None
    payment_reference: str
    amount: int = 5000
    currency: str = "NGN"

    @validator('fullName')
    def validate_full_name(cls, v):
        if len(v.strip()) < 2:
            raise ValueError('Full name must be at least 2 characters')
        return v.strip()

    @validator('email')
    def validate_email(cls, v):
        return v.lower().strip()


class InitPresellPaymentRequest(BaseModel):
    fullName: str
    email: EmailStr
    amount: int  # in kobo
    reference: str

    @validator("fullName")
    def validate_name(cls, v):
        return v.strip()

    @validator("email")
    def validate_email(cls, v):
        return v.lower().strip()



# ===== HELPER FUNCTIONS =====
def create_presell_user(data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a presell user entry with special presell tag"""
    try:
        presell_id = str(uuid.uuid4())
        user_data = {
            "_id": presell_id,
            "presell_id": presell_id,
            "full_name": data['fullName'],
            "email": data['email'],
            "expectations": data.get('expectations'),
            "payment_reference": data['payment_reference'],
            "amount": data['amount'],
            "currency": data['currency'],
            "payment_status": "pending",
            "presell_tag": "founding_creator_2025",
            "presell_reward": "1_year_free",
            "joined_at": datetime.now(timezone.utc),
            "type": "presell_payment",
            "source": "presell_page",
            "status": "pending_verification"
        }
        
        # Save to presell_users collection
        db.collection("presell_users").document(presell_id).set(user_data)
        
        # Also save reference by email for easy lookup
        db.collection("presell_emails").document(data['email']).set({
            "presell_id": presell_id,
            "joined_at": datetime.now(timezone.utc)
        })
        
        logger.info(f"Presell user created: {data['email']}")
        
        return user_data
        
    except Exception as e:
        logger.error(f"Failed to create presell user: {e}")
        raise


def update_presell_user_payment(presell_id: str, payment_data: Dict[str, Any]) -> None:
    """Update presell user with payment verification details"""
    try:
        update_data = {
            "payment_status": "verified",
            "verified_at": datetime.now(timezone.utc),
            "paystack_data": payment_data,
            "status": "active",
            "presell_reward_claimed": False,
            "presell_reward_claimable_after": datetime.now(timezone.utc).replace(year=2025, month=6, day=1)  # Launch date
        }
        
        db.collection("presell_users").document(presell_id).update(update_data)
        
        logger.info(f"Presell user payment verified: {presell_id}")
        
    except Exception as e:
        logger.error(f"Failed to update presell user payment: {e}")
        raise


# ===== WEBHOOK HANDLER =====
@router.post("/webhook/paystack", status_code=status.HTTP_200_OK)
async def presell_paystack_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Fixed webhook - only grants 1-year subscription to PAID presell users
    """
    body = await request.body()
    signature = request.headers.get("x-paystack-signature")

    # Validate signature
    if not signature or not hmac.compare_digest(
        hmac.new(settings.PAYSTACK_SECRET_KEY.encode(), body, hashlib.sha512).hexdigest(),
        signature
    ):
        logger.warning("Invalid Paystack webhook signature for presell")
        raise HTTPException(400, "Invalid signature")

    try:
        event_data = json.loads(body)
    except json.JSONDecodeError:
        logger.error("Invalid JSON in presell webhook")
        raise HTTPException(400, "Invalid JSON")

    event = event_data.get("event")
    data = event_data.get("data", {})
    metadata = data.get("metadata", {})
    
    logger.info(f"Presell webhook received: {event}")

    if event == "charge.success":
        ref = data.get("reference")
        if not ref:
            return {"status": "ignored"}

        amount_kobo = data.get("amount", 0)
        amount = amount_kobo / 100
        presell_type = metadata.get("presell_type")
        
        # ✅ ONLY process if this is a presell payment
        if presell_type != "founding_creator_2025":
            logger.info(f"Not a presell payment: {ref}")
            return {"status": "ignored"}
        
        # ✅ VERIFY amount is exactly ₦5,000 (or 500000 kobo)
        if amount_kobo != 500000:  # 5000 * 100
            logger.warning(f"Invalid presell amount: {amount} (expected ₦5,000)")
            return {"status": "invalid_amount"}
        
        # Find pending presell payment
        pending_ref = db.collection("presell_references").document(ref).get()
        if not pending_ref.exists:
            logger.warning(f"Presell payment not found: {ref}")
            return {"status": "ignored"}
        
        pending_data = pending_ref.to_dict()
        pending_id = pending_data["pending_id"]
        
        pending_details = db.collection("presell_pending").document(pending_id).get()
        if not pending_details.exists:
            logger.error(f"Pending details not found: {pending_id}")
            return {"status": "ignored"}
        
        payment_details = pending_details.to_dict()
        email = payment_details['email'].lower().strip()
        
        logger.info(f"✅ VALID PRESELL PAYMENT → {ref} | ₦{amount:,.0f} | Email: {email}")
        
        try:
            # Create presell user record
            presell_id = str(uuid.uuid4())
            presell_user_data = {
                "_id": presell_id,
                "presell_id": presell_id,
                "full_name": payment_details['fullName'],
                "email": email,
                "expectations": payment_details.get('expectations'),
                "payment_reference": ref,
                "amount": amount,
                "currency": payment_details['currency'],
                "payment_status": "verified",
                "presell_tag": "founding_creator_2025",
                "presell_reward": "1_year_free",
                "joined_at": datetime.now(timezone.utc),
                "verified_at": datetime.now(timezone.utc),
                "type": "presell_payment",
                "source": "presell_page",
                "status": "active",
                "presell_reward_claimed": False,
                "presell_reward_claimable": True,  # Can be claimed when they sign up
                "paystack_data": data
            }
            
            db.collection("presell_users").document(presell_id).set(presell_user_data)
            
            # Save email reference for lookup
            db.collection("presell_emails").document(email).set({
                "presell_id": presell_id,
                "email": email,
                "joined_at": datetime.now(timezone.utc),
                "payment_verified": True,
                "amount_paid": amount,
                "reference": ref,
                "current_spot": current_spot
            })
            
            # ⚠️ IMPORTANT: Check if user already exists
            # If they do, grant them the subscription immediately
            existing_users = db.collection("users").where(filter=FieldFilter("email", "==", email)).limit(1).get()
            
            if existing_users:
                user_doc = existing_users[0]
                user_id = user_doc.id
                
                logger.info(f"🎉 User exists! Granting 1-year subscription to {user_id}")
                
                # Grant 1-year subscription
                subscription_end = datetime.now(timezone.utc) + timedelta(days=365)
                
                db.collection("users").document(user_id).update({
                    "plan": "silver",
                    "subscription_end": subscription_end,
                    "presell_claimed": True,
                    "presell_eligible": True,
                    "presell_id": presell_id,
                    "updated_at": datetime.now(timezone.utc)
                })
                
                create_notification(
                    user_id=user_id,
                    title="Welcome, Founding Creator!",
                    message="You've received Payla Silver for 1 year! 🎉",
                    type="success",
                    link="/dashboard"
                )
            
            # Clean up pending records
            db.collection("presell_pending").document(pending_id).delete()
            db.collection("presell_references").document(ref).delete()
            
            # Send welcome email
            background_tasks.add_task(
                send_layla_email,
                "presell_success",
                email
            )
            
            logger.info(f"✅ Presell user created successfully: {presell_id}")
            
        except Exception as e:
            logger.error(f"Failed to process presell payment: {e}", exc_info=True)
            
    return {"status": "success"}


# ===== API ENDPOINTS =====
@router.get("/counter")
async def get_presell_counter():
    """Get current presell counter (paid users count) - Starting from 127"""
    try:
        # Count verified presell users
        verified_users = db.collection("presell_users")\
            .where(filter=FieldFilter("payment_status", "==", "verified"))\
            .count()\
            .get()
        
        # Get the count from Firestore (0 if no users)
        firestore_count = verified_users[0][0].value if verified_users else 0
        
        # Add 127 as base count
        paid_count = firestore_count + 127
        
        # Calculate spots left (500 total spots)
        TOTAL_SPOTS = 500
        spots_left = max(TOTAL_SPOTS - paid_count, 0)
        
        return {
            "paid_count": paid_count,
            "total_count": paid_count,  # For JS compatibility
            "spots_left": spots_left,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get counter: {e}")
        # Return default values starting from 127
        return {
            "paid_count": 127,
            "total_count": 127,
            "spots_left": 373,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }


@router.post("/save-pending")
async def save_pending_payment(request: LockYearRequest):
    """Save pending payment before Paystack redirect, with retry logic."""
    try:
        email = request.email.lower().strip()
        now_ts = datetime.now(timezone.utc).timestamp()

        # =======================================
        # 1. Fetch existing pending for this email
        # =======================================
        pending_docs = db.collection("presell_pending")\
            .where(filter=FieldFilter("email", "==", email))\
            .get()

        for doc in pending_docs:
            data = doc.to_dict()
            status_ = data.get("status", "pending")
            expires = data.get("expires_at", 0)
            ref = data.get("payment_reference")

            # CASE A — ACTIVE pending + SAME reference → allow retry
            if status_ == "pending" and expires > now_ts and ref == request.payment_reference:
                return {
                    "success": True,
                    "pending_id": data["_id"],
                    "payment_reference": request.payment_reference,
                    "message": "Retry allowed"
                }

            # CASE B — ACTIVE pending + DIFFERENT reference → block
            if status_ == "pending" and expires > now_ts and ref != request.payment_reference:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="You already have a pending payment"
                )

            # CASE C — EXPIRED OR FAILED → delete & allow new
            db.collection("presell_pending").document(doc.id).delete()

        # =======================================
        # 2. Prevent duplicate paid user
        # =======================================
        email_paid = db.collection("presell_emails").document(email).get()
        if email_paid.exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You've already reserved your spot"
            )

        # =======================================
        # 3. Create NEW pending record
        # =======================================
        pending_id = f"pending_{int(now_ts)}_{uuid.uuid4().hex[:8]}"

        pending_data = {
            "_id": pending_id,
            "fullName": request.fullName,
            "email": email,
            "expectations": request.expectations,
            "payment_reference": request.payment_reference,
            "amount": request.amount,
            "currency": request.currency,
            "status": "pending",
            "created_at": datetime.now(timezone.utc),
            "expires_at": now_ts + (24 * 60 * 60),  # 24 hours
        }

        db.collection("presell_pending").document(pending_id).set(pending_data)

        # =======================================
        # 4. Reference lookup
        # =======================================
        db.collection("presell_references").document(request.payment_reference).set({
            "pending_id": pending_id,
            "email": email,
            "created_at": datetime.now(timezone.utc)
        })

        # =======================================
        # 5. Response
        # =======================================
        return {
            "success": True,
            "pending_id": pending_id,
            "payment_reference": request.payment_reference,
            "message": "Payment details saved. Proceed to payment."
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Failed to save pending payment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save payment details. Please try again."
        )


@router.post("/init-payment")
async def init_presell_payment(request: InitPresellPaymentRequest):
    """
    Initializes a Paystack hosted checkout with prefilled email & metadata.
    Frontend will redirect to the returned authorization_url.
    """
    try:
        headers = {
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_PAYLA}",
            "Content-Type": "application/json",
        }

        payload = {
            "email": request.email,
            "amount": request.amount,  # already in kobo
            "reference": request.reference,
            "currency": "NGN",
            "metadata": {
                "full_name": request.fullName,
                "presell_type": "founding_creator_2025",
            },
            # optional but recommended
            "callback_url": f"{settings.FRONTEND_URL}/thank-you"
        }

        async with httpx.AsyncClient(timeout=15) as client:
            ps = await client.post(
                "https://api.paystack.co/transaction/initialize",
                json=payload,
                headers=headers,
            )

        result = ps.json()

        if ps.status_code != 200 or not result.get("status"):
            logger.error(f"Paystack init failed: {result}")
            raise HTTPException(
                status_code=400,
                detail=result.get("message", "Unable to initialize payment")
            )

        return {
            "authorization_url": result["data"]["authorization_url"],
            "reference": result["data"]["reference"],
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Init payment error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Payment initialization failed"
        )



@router.get("/user/{email}")
async def get_presell_user_status(email: str):
    """Check if a user has paid for presell"""
    try:
        email = email.lower().strip()
        
        # Check if paid user
        paid_user = db.collection("presell_emails").document(email).get()
        if paid_user.exists:
            paid_data = paid_user.to_dict()
            user_details = db.collection("presell_users").document(paid_data["presell_id"]).get()
            
            if user_details.exists:
                user_data = user_details.to_dict()
                return {
                    "status": "paid",
                    "user": {
                        "presell_tag": user_data.get("presell_tag"),
                        "presell_reward": user_data.get("presell_reward"),
                        "joined_at": user_data.get("joined_at"),
                        "payment_status": user_data.get("payment_status")
                    }
                }
        
        return {
            "status": "not_found",
            "message": "User not found in presell"
        }
        
    except Exception as e:
        logger.error(f"Failed to get user status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check user status"
        )


from datetime import timedelta

@router.post("/verify-payment")
async def verify_payment(payload: dict, background_tasks: BackgroundTasks):
    """Instant, idempotent, real-time Paystack verification."""
    reference = payload.get("reference")
    
    if not reference:
        raise HTTPException(400, "Missing payment reference")

    try:
        # ======================================================
        # 1. Lookup pending via reference
        # ======================================================
        ref_doc = db.collection("presell_references").document(reference).get()
        if not ref_doc.exists:
            raise HTTPException(400, "Invalid reference")

        pending_id = ref_doc.to_dict().get("pending_id")
        pending_doc = db.collection("presell_pending").document(pending_id).get()
        
        if not pending_doc.exists:
            raise HTTPException(400, "Pending record not found")

        pending = pending_doc.to_dict()
        email = pending["email"].lower().strip()

        # Idempotency: if already completed, return success immediately
        if pending.get("status") == "completed":
            return {
                "success": True,
                "message": "Payment already verified",
                "user": {
                    "fullName": pending["fullName"],
                    "email": email,
                }
            }

        # ======================================================
        # 2. CALL PAYSTACK VERIFY API
        # ======================================================
        headers = {
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
            "Accept": "application/json",
        }
        verify_url = f"https://api.paystack.co/transaction/verify/{reference}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            ps = await client.get(verify_url, headers=headers)

        if ps.status_code != 200:
            raise HTTPException(400, "Could not verify payment")

        ps_data = ps.json()
        status_ = ps_data["data"]["status"]
        amount_paid = ps_data["data"]["amount"] / 100 

        # ======================================================
        # 3. CHECK FOR FAILURE / ABANDONED
        # ======================================================
        if status_ not in ["success", "completed"]:
            db.collection("presell_pending").document(pending_id).update({
                "status": "failed",
                "updated_at": datetime.now(timezone.utc)
            })
            return {
                "success": False,
                "status": status_,
                "message": "Payment not successful. Try again."
            }

        # ======================================================
        # 4. VALIDATE AMOUNT (₦5,000)
        # ======================================================
        if amount_paid < pending["amount"]:
            raise HTTPException(400, "Amount mismatch. Contact support.")

        # ======================================================
        # 5. MARK USER AS PAID (ATOMICS)
        # ======================================================
        batch = db.batch()
        now = datetime.now(timezone.utc)
        one_year_expiry = now + timedelta(days=365)

        # A. Update pending → completed
        batch.update(
            db.collection("presell_pending").document(pending_id),
            {"status": "completed", "updated_at": now}
        )

        # B. Get counter to calculate current spot
        counter_response = await get_presell_counter()
        current_spot = counter_response["paid_count"] + 1
        spots_left = max(500 - current_spot, 0)

        # C. Create/Update the master email record (Crucial for Auth system)
        batch.set(
            db.collection("presell_emails").document(email),
            {
                "email": email,
                "fullName": pending["fullName"],
                "reference": reference,
                "payment_verified": True, # <--- Used by auth.py
                "current_spot": current_spot,
                "joined_at": now,
                "amount_paid": amount_paid
            }
        )

        # D. IF USER EXISTS: Upgrade them immediately to Silver until 2026
        existing_users = db.collection("users").where(filter=FieldFilter("email", "==", email)).limit(1).get()
        if existing_users:
            user_doc = existing_users[0]
            batch.update(db.collection("users").document(user_doc.id), {
                "plan": "silver",
                "subscription_end": one_year_expiry, # Sets to Dec 2026
                "presell_eligible": True,
                "presell_claimed": True,
                "updated_at": now
            })
            
            # Create in-app notification
            create_notification(
                user_id=user_doc.id,
                title="Founding Creator Active! 🎉",
                message="Your 1-year Payla Silver subscription is now active.",
                type="success",
                link="/dashboard"
            )

        batch.commit()

        # ======================================================
        # 6. TRIGGER LAYLA'S EMAIL (No name passed to avoid KeyError)
        # ======================================================
        background_tasks.add_task(send_layla_email, "presell_success", email)

        # ======================================================
        # 7. GENERATE ACCESS TOKEN & RESPONSE
        # ======================================================
        try:
            firebase_token = firebase_auth.create_custom_token(email)
            access_token = firebase_token.decode() if isinstance(firebase_token, bytes) else firebase_token
        except Exception:
            access_token = f"presell_{uuid.uuid4().hex}"

        return {
            "success": True,
            "status": "success",
            "message": "Payment verified and rewards granted",
            "access_token": access_token,
            "spots_left": spots_left,
            "user": {
                "fullName": pending["fullName"],
                "email": email,
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PAYSTACK VERIFY ERROR: {e}")
        raise HTTPException(500, "Verification error occurred")

@router.get("/thank-you")
async def get_thank_you_info(email: str):
    """
    Returns the user's current spot and remaining spots for the thank-you page.
    """
    try:
        if not email:
            raise HTTPException(status_code=400, detail="Email is required")

        # Query user by email
        user_docs = db.collection("presell_users").where(filter=FieldFilter("email", "==", email.lower())).limit(1).get()
        if not user_docs:
            raise HTTPException(status_code=404, detail="User not found")

        user_doc = user_docs[0]
        user_data = user_doc.to_dict()

        # Get counter to get current spot
        counter_response = await get_presell_counter()
        paid_count = counter_response["paid_count"]
        
        # Since the counter starts from 127, we need to calculate the user's actual position
        # Get all verified presell users sorted by joined_at
        all_users = db.collection("presell_users")\
            .where(filter=FieldFilter("payment_status", "==", "verified"))\
            .order_by("joined_at")\
            .stream()

        all_users_list = list(all_users)
        
        # Find user's position in the list (0-based)
        user_position = next(
            (idx for idx, u in enumerate(all_users_list) if u.id == user_doc.id),
            None
        )
        
        if user_position is not None:
            # Add 128 because counter starts from 127 and position is 0-based
            current_spot = user_position + 128
        else:
            # Fallback: use the current paid count
            current_spot = paid_count

        # Calculate spots left
        TOTAL_SPOTS = 500
        spots_left = max(TOTAL_SPOTS - current_spot, 0)

        return {
            "email": user_data.get("email"),
            "full_name": user_data.get("full_name"),
            "current_spot": current_spot,
            "spots_left": spots_left,
            "joined_at": user_data.get("joined_at"),
            "payment_status": user_data.get("payment_status"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get thank-you info: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch thank-you info. Please try again."
        )


@router.post("/claim")
async def claim_presell_reward(request: Request, authorization: str = Header(...)):
    """
    Fixed claim - only grants subscription to users who PAID ₦5,000
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid token")

    id_token = authorization.split(" ")[1]

    try:
        decoded_token = firebase_auth.verify_id_token(id_token)
        user_id = decoded_token['user_id']
        email = decoded_token['email'].lower().strip()
    except Exception as e:
        raise HTTPException(401, f"Invalid token: {e}")

    # Fetch user
    user_ref = db.collection("users").document(user_id)
    user_doc = user_ref.get()
    if not user_doc.exists:
        raise HTTPException(404, "User not found")

    user_data = user_doc.to_dict()

    # Check if already claimed
    if user_data.get("presell_claimed"):
        return {
            "success": False, 
            "message": "You've already claimed your founding creator reward"
        }

    # ✅ VERIFY user actually PAID for presell
    presell_email_doc = db.collection("presell_emails").document(email).get()
    
    if not presell_email_doc.exists:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "presell_not_paid",
                "message": "You haven't paid for the founding creator offer. Please pay ₦5,000 to unlock 1 year free."
            }
        )
    
    presell_email_data = presell_email_doc.to_dict()
    
    # Verify payment was actually verified
    if not presell_email_data.get("payment_verified"):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "payment_not_verified",
                "message": "Your payment is still pending verification. Please try again in a few minutes."
            }
        )
    
    # ✅ User paid and verified - grant 1-year subscription
    logger.info(f"✅ Granting 1-year subscription to {user_id} (paid ₦{presell_email_data.get('amount_paid', 0)})")
    
    subscription_end = datetime.now(timezone.utc) + timedelta(days=365)
    
    user_ref.update({
        "plan": "silver",
        "subscription_end": subscription_end,
        "presell_claimed": True,
        "presell_eligible": True,
        "presell_id": presell_email_data.get("presell_id"),
        "updated_at": datetime.now(timezone.utc)
    })

    # Send email confirmation
    send_presell_reward_email(email, user_data.get("full_name", ""))

    # Create notification
    create_notification(
        user_id=user_id,
        title="Founding Creator Reward Claimed! 🎉",
        message="You've received Payla Silver for 1 year! Welcome to the founding crew.",
        type="success",
        link="/dashboard"
    )

    updated_user = user_ref.get().to_dict()
    return {
        "success": True, 
        "user": updated_user,
        "message": "Congratulations! You now have Payla Silver for 1 year."
    }


@router.get("/check-eligibility/{email}")
async def check_presell_eligibility(email: str):
    """
    Check if an email has paid for presell and is eligible for 1-year subscription
    Call this during signup/login to auto-grant subscription
    """
    try:
        email = email.lower().strip()
        
        # Check if paid for presell
        presell_doc = db.collection("presell_emails").document(email).get()
        
        if not presell_doc.exists:
            return {
                "eligible": False,
                "message": "Email not found in founding creators list"
            }
        
        presell_data = presell_doc.to_dict()
        
        if not presell_data.get("payment_verified"):
            return {
                "eligible": False,
                "message": "Payment not yet verified"
            }
        
        # Check if already claimed
        users = db.collection("users").where(filter=FieldFilter("email", "==", email)).limit(1).get()
        if users:
            user_data = users[0].to_dict()
            if user_data.get("presell_claimed"):
                return {
                    "eligible": False,
                    "already_claimed": True,
                    "message": "Reward already claimed"
                }
        
        return {
            "eligible": True,
            "presell_id": presell_data.get("presell_id"),
            "amount_paid": presell_data.get("amount_paid"),
            "payment_date": presell_data.get("joined_at"),
            "message": "User is eligible for 1-year free subscription"
        }
        
    except Exception as e:
        logger.error(f"Error checking eligibility: {e}")
        return {
            "eligible": False,
            "error": str(e)
        }