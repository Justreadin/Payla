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

from app.core.firebase import db
from app.core.config import settings
from app.core.notifications import create_notification
from app.utils.presell_email import send_layla_email
from app.services.email_service import send_presell_reward_email

logger = logging.getLogger("payla.presell")

router = APIRouter(prefix="/presell", tags=["Presell"])


# ===== MODELS =====
class WaitlistRequest(BaseModel):
    name: str
    email: EmailStr
    expectations: Optional[str] = None
    source: str = "presell_page"

    @validator('name')
    def validate_name(cls, v):
        if len(v.strip()) < 2:
            raise ValueError('Name must be at least 2 characters')
        return v.strip()

    @validator('email')
    def validate_email(cls, v):
        return v.lower().strip()


class LockYearRequest(BaseModel):
    fullName: str
    email: EmailStr
    username: str
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

    @validator('username')
    def validate_username(cls, v):
        username = v.lower().strip()
        if not username.replace("_", "").isalnum():
            raise ValueError('Username can only contain letters, numbers, and underscores')
        if len(username) < 3:
            raise ValueError('Username must be at least 3 characters')
        if len(username) > 20:
            raise ValueError('Username cannot exceed 20 characters')
        
        # Check for reserved names
        reserved = ["admin", "support", "payla", "help", "system"]
        if username in reserved:
            raise ValueError('This username is reserved')
        
        return username


# ===== HELPER FUNCTIONS =====
def save_to_waitlist_csv(data: Dict[str, Any]) -> None:
    """Append waitlist entry to CSV file in Firebase Storage or local file"""
    try:
        # Get existing waitlist or create new
        waitlist_ref = db.collection("presell_waitlist").document(data['email'])
        
        # Prepare data with timestamp
        waitlist_data = {
            **data,
            "joined_at": datetime.now(timezone.utc),
            "type": "waitlist",
            "source": data.get('source', 'presell_page')
        }
        
        # Save to Firestore
        waitlist_ref.set(waitlist_data)
        
        logger.info(f"Waitlist entry saved: {data['email']}")
        
    except Exception as e:
        logger.error(f"Failed to save waitlist entry: {e}")
        raise


def create_presell_user(data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a presell user entry with special presell tag"""
    try:
        presell_id = str(uuid.uuid4())
        user_data = {
            "_id": presell_id,
            "presell_id": presell_id,
            "full_name": data['fullName'],
            "email": data['email'],
            "username": data['username'],
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
            "username": data['username'],
            "joined_at": datetime.now(timezone.utc)
        })
        
        logger.info(f"Presell user created: {data['email']} -> @{data['username']}")
        
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
    Paystack webhook specifically for presell payments.
    This handles the ₦5,000 lock year payments from the presell page.
    """
    body = await request.body()
    signature = request.headers.get("x-paystack-signature")

    # === 1. Validate Signature ===
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

    # ========================================
    # Handle Presell Lock Year Payments
    # ========================================
    if event in ("charge.success", "charge.failed"):
        ref = data.get("reference")
        if not ref:
            logger.warning("Presell webhook missing reference")
            return {"status": "ignored"}

        amount_kobo = data.get("amount", 0)
        amount = amount_kobo / 100
        status_str = "success" if event == "charge.success" else "failed"
        
        # Get metadata specific to presell
        presell_type = metadata.get("presell_type")
        username = metadata.get("payla_username")
        full_name = metadata.get("full_name")
        
        # Check if this is a presell payment
        if presell_type != "founding_creator_2025":
            logger.info(f"Not a presell payment: {ref}")
            return {"status": "ignored"}
        
        # Find pending presell payment
        pending_ref = db.collection("presell_references").document(ref).get()
        if not pending_ref.exists:
            logger.warning(f"Presell payment not found in pending: {ref}")
            return {"status": "ignored"}
        
        pending_data = pending_ref.to_dict()
        pending_id = pending_data["pending_id"]
        
        # Get pending details
        pending_details = db.collection("presell_pending").document(pending_id).get()
        if not pending_details.exists:
            logger.error(f"Pending details not found: {pending_id}")
            return {"status": "ignored"}
        
        payment_details = pending_details.to_dict()
        
        # ========================================
        # PAYMENT SUCCESS
        # ========================================
        if status_str == "success":
            logger.info(f"Presell payment SUCCESS → {ref} | ₦{amount:,.0f} | Username: {username}")
            
            try:
                # Create presell user
                presell_user = create_presell_user(payment_details)
                
                # Update with payment verification data
                update_presell_user_payment(presell_user["_id"], {
                    "reference": ref,
                    "amount": amount,
                    "status": "success",
                    "paid_at": datetime.now(timezone.utc),
                    "paystack_data": data
                })
                
                # Move from pending to completed
                db.collection("presell_pending").document(pending_id).delete()
                db.collection("presell_references").document(ref).delete()
                
                # Create success notification
                create_notification(
                    user_id=presell_user["_id"],
                    title="Welcome to Payla Founding Creators!",
                    message=f"Your username @{username} has been reserved. You'll get 1 year free when we launch!",
                    type="success",
                    link="/presell/welcome"
                )
                
                # Send welcome email (you can implement this)
                background_tasks.add_task(
                    send_layla_email,
                    "presell_success",
                    payment_details['email'],
                    {
                        "name": payment_details['fullName'].split()[0],
                        "username": payment_details['username']
                    }
                )
                
                logger.info(f"Presell user created successfully: {presell_user['_id']}")
                
            except Exception as e:
                logger.error(f"Failed to process presell payment success: {e}", exc_info=True)
                # Don't delete pending record if processing failed
                
        # ========================================
        # PAYMENT FAILED
        # ========================================
        else:
            logger.warning(f"Presell payment FAILED → {ref} | Username: {username}")
            
            # Update pending record with failure
            db.collection("presell_pending").document(pending_id).update({
                "status": "failed",
                "failed_at": datetime.now(timezone.utc),
                "failure_reason": data.get("gateway_response", "Payment failed")
            })
            
            # Send failure notification (optional)
            # You could email the user to try again
            
    # ========================================
    # Handle Subscription Events (if any)
    # ========================================
    elif event == "subscription.create":
        # Handle presell subscriptions if needed
        logger.info(f"Presell subscription created: {event}")
        
    elif event in ("subscription.disable", "subscription.expire"):
        # Handle subscription cancellation
        logger.info(f"Presell subscription cancelled: {event}")
        
    else:
        logger.info(f"Unhandled presell webhook event: {event}")

    return {"status": "success"}


# ===== EMAIL FUNCTION =====
def send_presell_welcome_email(email: str, username: str, full_name: str):
    """Send welcome email to presell user"""
    # Implement your email sending logic here
    # You can use your existing email service
    logger.info(f"Would send welcome email to {email} for @{username}")
    pass


# ===== API ENDPOINTS =====
@router.get("/counter")
async def get_presell_counter():
    """Get current presell counter (paid users count)"""
    try:
        # Count paid users
        paid_users = db.collection("presell_users")\
            .where("payment_status", "==", "verified")\
            .count()\
            .get()
        
        # Count waitlist users
        waitlist_count = db.collection("presell_waitlist")\
            .count()\
            .get()
        
        return {
            "paid_count": paid_users[0][0].value if paid_users else 0,
            "waitlist_count": waitlist_count[0][0].value if waitlist_count else 0,
            "total_count": (paid_users[0][0].value if paid_users else 0) + 
                          (waitlist_count[0][0].value if waitlist_count else 0),
            "spots_left": 500 - (paid_users[0][0].value if paid_users else 0),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get counter: {e}")
        return {
            "paid_count": 127,  # Default fallback
            "waitlist_count": 0,
            "total_count": 127,
            "spots_left": 373,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }


@router.post("/waitlist")
async def join_waitlist(request: WaitlistRequest, background_tasks: BackgroundTasks):
    """Join the presell waitlist"""
    try:
        # Check if already in waitlist
        existing = db.collection("presell_waitlist").document(request.email).get()
        if existing.exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You're already on the waitlist!"
            )
        
        # Prepare waitlist data
        waitlist_data = {
            "name": request.name,
            "email": request.email,
            "expectations": request.expectations,
            "source": request.source,
            "joined_at": datetime.now(timezone.utc),
            "type": "waitlist"
        }
        
        # Save to waitlist
        background_tasks.add_task(save_to_waitlist_csv, waitlist_data)
        background_tasks.add_task(
            send_layla_email, 
            "waitlist_welcome", 
            request.email, 
            {"name": request.name.split()[0]}
        )

        return {
            "success": True,
            "message": "You're on the waitlist! We'll notify you when we launch.",
            "email": request.email,
            "joined_at": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Waitlist join failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to join waitlist. Please try again."
        )


@router.post("/check-username")
async def check_presell_username(request: dict):
    """Check if username is available for presell"""
    username = request.get("username", "").lower().strip()
    
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    
    if not username.replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="Username: letters, numbers, _ only")
    
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username too short")
    
    if len(username) > 20:
        raise HTTPException(status_code=400, detail="Username too long")
    
    # Check if username exists in paylinks (existing users)
    paylink_query = db.collection("paylinks").where("username", "==", username).limit(1).get()
    
    # Check if username exists in presell users (already reserved)
    presell_query = db.collection("presell_users").where("username", "==", username).limit(1).get()
    
    # Check if username exists in pending presell
    pending_query = db.collection("presell_pending").where("username", "==", username).limit(1).get()
    
    if paylink_query or presell_query or pending_query:
        return {
            "available": False,
            "message": f"@{username} is already taken"
        }
    
    # Check for reserved usernames
    reserved_usernames = ["admin", "support", "payla", "help", "system"]
    if username in reserved_usernames:
        return {
            "available": False,
            "message": "This username is reserved"
        }
    
    # Check for inappropriate usernames
    inappropriate_words = ["fuck", "shit", "ass", "bitch", "nigga", "nigger", "cunt"]
    if any(word in username for word in inappropriate_words):
        return {
            "available": False,
            "message": "Username contains inappropriate content"
        }
    
    return {
        "available": True,
        "username": username,
        "message": f"@{username} is available!"
    }


@router.post("/save-pending")
async def save_pending_payment(request: LockYearRequest):
    """Save pending payment before Paystack redirect, with retry logic."""
    try:
        # =======================================
        # 1. Double-check username availability
        # =======================================
        check_response = await check_presell_username({"username": request.username})
        if not check_response["available"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=check_response["message"]
            )

        email = request.email.lower().strip()
        now_ts = datetime.now(timezone.utc).timestamp()

        # =======================================
        # 2. Fetch existing pending for this email
        # =======================================
        pending_docs = db.collection("presell_pending")\
            .where("email", "==", email)\
            .get()

        matching_pending = None

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
        # 3. Prevent duplicate paid user
        # =======================================
        email_paid = db.collection("presell_emails").document(email).get()
        if email_paid.exists:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You've already reserved a username"
            )

        # =======================================
        # 4. Create NEW pending record
        # =======================================
        pending_id = f"pending_{int(now_ts)}_{uuid.uuid4().hex[:8]}"

        pending_data = {
            "_id": pending_id,
            "fullName": request.fullName,
            "email": email,
            "username": request.username,
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
        # 5. Reference lookup
        # =======================================
        db.collection("presell_references").document(request.payment_reference).set({
            "pending_id": pending_id,
            "email": email,
            "username": request.username,
            "created_at": datetime.now(timezone.utc)
        })

        # =======================================
        # 6. Response
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


@router.get("/user/{email}")
async def get_presell_user_status(email: str):
    """Check if a user has joined presell or waitlist"""
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
                        "username": user_data.get("username"),
                        "presell_tag": user_data.get("presell_tag"),
                        "presell_reward": user_data.get("presell_reward"),
                        "joined_at": user_data.get("joined_at"),
                        "payment_status": user_data.get("payment_status")
                    }
                }
        
        # Check if waitlist user
        waitlist_user = db.collection("presell_waitlist").document(email).get()
        if waitlist_user.exists:
            waitlist_data = waitlist_user.to_dict()
            return {
                "status": "waitlist",
                "user": {
                    "name": waitlist_data.get("name"),
                    "email": waitlist_data.get("email"),
                    "joined_at": waitlist_data.get("joined_at"),
                    "expectations": waitlist_data.get("expectations")
                }
            }
        
        return {
            "status": "not_found",
            "message": "User not found in presell or waitlist"
        }
        
    except Exception as e:
        logger.error(f"Failed to get user status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check user status"
        )


@router.get("/export/waitlist")
async def export_waitlist_csv():
    """Export waitlist as CSV (admin only)"""
    try:
        # Get all waitlist entries
        waitlist_docs = db.collection("presell_waitlist").stream()
        
        # Prepare CSV data
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(["Name", "Email", "Expectations", "Source", "Joined At", "Type"])
        
        # Write data
        for doc in waitlist_docs:
            data = doc.to_dict()
            writer.writerow([
                data.get("name", ""),
                data.get("email", ""),
                data.get("expectations", ""),
                data.get("source", ""),
                data.get("joined_at", "").isoformat() if data.get("joined_at") else "",
                data.get("type", "")
            ])
        
        output.seek(0)
        
        # Create streaming response
        filename = f"payla_waitlist_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
        
        return StreamingResponse(
            output,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        logger.error(f"Failed to export waitlist: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export waitlist"
        )


@router.get("/export/presell-users")
async def export_presell_users_csv():
    """Export presell users as CSV (admin only)"""
    try:
        # Get all presell users
        user_docs = db.collection("presell_users").stream()
        
        # Prepare CSV data
        output = StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            "Presell ID", "Full Name", "Email", "Username", 
            "Payment Reference", "Amount", "Currency", "Payment Status",
            "Presell Tag", "Presell Reward", "Joined At", "Status"
        ])
        
        # Write data
        for doc in user_docs:
            data = doc.to_dict()
            writer.writerow([
                data.get("presell_id", ""),
                data.get("full_name", ""),
                data.get("email", ""),
                data.get("username", ""),
                data.get("payment_reference", ""),
                data.get("amount", ""),
                data.get("currency", ""),
                data.get("payment_status", ""),
                data.get("presell_tag", ""),
                data.get("presell_reward", ""),
                data.get("joined_at", "").isoformat() if data.get("joined_at") else "",
                data.get("status", "")
            ])
        
        output.seek(0)
        
        # Create streaming response
        filename = f"payla_presell_users_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
        
        return StreamingResponse(
            output,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        logger.error(f"Failed to export presell users: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export presell users"
        )
    

@router.post("/verify-payment")
async def verify_payment(payload: dict):
    """Instant, idempotent, real-time Paystack verification."""
    reference = payload.get("reference")
    username = payload.get("username")
    
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

        # Idempotency: if already completed, return success immediately
        if pending.get("status") == "completed":
            return {
                "success": True,
                "message": "Payment already verified",
                "user": {
                    "fullName": pending["fullName"],
                    "email": pending["email"],
                    "username": pending["username"],
                }
            }

        email = pending["email"]
        amount_expected = pending["amount"]

        # ======================================================
        # 2. CALL PAYSTACK VERIFY API  (REAL-TIME CONFIRMATION)
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
        amount_paid = ps_data["data"]["amount"] / 100  # convert kobo → naira

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
        # 4. VALIDATE AMOUNT
        # ======================================================
        if amount_paid < amount_expected:
            raise HTTPException(400, "Amount mismatch. Contact support.")

        # ======================================================
        # 5. MARK USER AS PAID (ATOMICS)
        # ======================================================
        batch = db.batch()

        # A. Update pending → completed
        batch.update(
            db.collection("presell_pending").document(pending_id),
            {
                "status": "completed",
                "updated_at": datetime.now(timezone.utc)
            }
        )

        # B. Create final paid user record
        batch.set(
            db.collection("presell_emails").document(email),
            {
                "email": email,
                "username": pending["username"],
                "fullName": pending["fullName"],
                "reference": reference,
                "created_at": datetime.now(timezone.utc)
            }
        )

        batch.commit()

        # ======================================================
        # 6. RESPONSE
        # ======================================================
        return {
            "success": True,
            "status": "success",
            "message": "Payment verified",
            "user": {
                "fullName": pending["fullName"],
                "email": email,
                "username": pending["username"],
            }
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"PAYSTACK VERIFY ERROR: {e}")
        raise HTTPException(500, "Verification error occurred")

@router.get("/thank-you")
async def get_thank_you_info(username: str):
    """
    Returns the user's current spot and remaining spots for the thank-you page.
    """
    try:
        if not username:
            raise HTTPException(status_code=400, detail="Username is required")

        # Query user by username
        user_docs = db.collection("presell_users").where("username", "==", username.lower()).limit(1).get()
        if not user_docs:
            raise HTTPException(status_code=404, detail="User not found")

        user_doc = user_docs[0]
        user_data = user_doc.to_dict()

        # Get all verified presell users sorted by joined_at
        all_users = db.collection("presell_users")\
            .where("payment_status", "==", "verified")\
            .order_by("joined_at")\
            .stream()

        all_users_list = list(all_users)

        # Determine user's current spot (1-based)
        current_spot = next(
            (idx + 1 for idx, u in enumerate(all_users_list) if u.id == user_doc.id),
            None
        )
        if current_spot is None:
            current_spot = len(all_users_list)  # fallback

        # Calculate spots left
        TOTAL_SPOTS = 500
        spots_left = max(TOTAL_SPOTS - len(all_users_list), 0)

        return {
            "username": user_data.get("username"),
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
    Marks presell reward as claimed and grants Payla Silver for 1 year.
    Sends email notification and creates an in-app notification.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid token")

    id_token = authorization.split(" ")[1]

    try:
        decoded_token = firebase_auth.verify_id_token(id_token)
        user_id = decoded_token['user_id']
        email = decoded_token['email']
    except Exception as e:
        raise HTTPException(401, f"Invalid token: {e}")

    # Fetch user
    user_ref = db.collection("users").document(user_id)
    user_doc = user_ref.get()
    if not user_doc.exists:
        raise HTTPException(404, "User not found")

    user_data = user_doc.to_dict()

    if user_data.get("presell_claimed"):
        return {"success": False, "message": "Already claimed"}

    # Grant Payla Silver
    from datetime import datetime, timedelta
    next_year = datetime.utcnow() + timedelta(days=365)
    user_ref.update({
        "plan": "silver",
        "plan_code": "payla-silver",
        "subscription_end": next_year,
        "presell_claimed": True
    })

    # Send email
    send_presell_reward_email(email, user_data["full_name"])

    # Create dashboard notification
    create_notification(
        user_id=user_id,
        title="Presell Reward Claimed",
        message="You have received Payla Silver for 1 year 🎉",
        type="success",
        link="/dashboard"
    )

    updated_user = user_ref.get().to_dict()
    return {"success": True, "user": updated_user}