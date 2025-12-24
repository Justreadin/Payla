# core/subscription.py - COMPREHENSIVE FIX
from fastapi import Depends, HTTPException, status
from app.core.auth import get_current_user
from app.models.user_model import User
from typing import Optional
from app.core.firebase import db
from datetime import datetime, timezone, timedelta
import logging

logger = logging.getLogger("payla")

# --- GRACE PERIOD CONFIG ---
SUBSCRIPTION_GRACE_DAYS = 7

def parse_firestore_datetime(value) -> Optional[datetime]:
    """Convert various datetime formats from Firestore to timezone-aware datetime"""
    if value is None:
        return None
        
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    
    if hasattr(value, 'to_datetime'):
        dt = value.to_datetime()
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    
    if isinstance(value, dict) and "_seconds" in value:
        return datetime.fromtimestamp(value["_seconds"], tz=timezone.utc)
    
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt
        except:
            pass
    
    logger.warning(f"Could not parse datetime value: {value} (type: {type(value)})")
    return None


def is_trial_active(user: User) -> bool:
    """Check if user's trial is still active"""
    trial_end = getattr(user, "trial_end_date", None)
    
    if trial_end is None:
        return False
    
    trial_end_dt = parse_firestore_datetime(trial_end)
    if trial_end_dt is None:
        return False
    
    now = datetime.now(timezone.utc)
    is_active = trial_end_dt > now
    
    if is_active:
        days_left = (trial_end_dt - now).days
        logger.info(f"User {user.id} trial ACTIVE - {days_left} days remaining")
    else:
        days_expired = (now - trial_end_dt).days
        logger.info(f"User {user.id} trial EXPIRED - {days_expired} days ago")
    
    return is_active


def get_subscription_status(user: User) -> dict:
    """
    Detailed check of subscription status including Grace Period logic.
    Returns: {"is_active": bool, "in_grace_period": bool, "days_left_in_grace": int}
    """
    subscription_end = getattr(user, "subscription_end", None)
    if subscription_end is None:
        return {"is_active": False, "in_grace_period": False, "days_left_in_grace": 0}

    sub_end_dt = parse_firestore_datetime(subscription_end)
    if sub_end_dt is None:
        return {"is_active": False, "in_grace_period": False, "days_left_in_grace": 0}

    now = datetime.now(timezone.utc)
    
    # 1. Standard Active Check (adding 24h buffer for timezone safety)
    if (sub_end_dt + timedelta(hours=24)) > now:
        return {"is_active": True, "in_grace_period": False, "days_left_in_grace": 0}

    # 2. Grace Period Check
    grace_end_dt = sub_end_dt + timedelta(days=SUBSCRIPTION_GRACE_DAYS)
    if grace_end_dt > now:
        days_left = (grace_end_dt - now).days
        return {"is_active": True, "in_grace_period": True, "days_left_in_grace": days_left}

    return {"is_active": False, "in_grace_period": False, "days_left_in_grace": 0}



def has_active_subscription(user: User) -> bool:
    """
    Check if user has an active paid subscription or is within the 7-day grace period.
    """
    sub_status = get_subscription_status(user)
    
    # log the specific status for debugging
    if sub_status["in_grace_period"]:
        logger.info(f"⚠️ User {user.id} in GRACE PERIOD: {sub_status['days_left_in_grace']} days remaining.")
    
    return sub_status["is_active"]

def can_access_silver_features(user: User) -> bool:
    """
    Comprehensive access check for Silver-tier features.
    Hierarchy: Presell > Paid Subscription (inc. Grace) > Active Trial > Manual Override
    """
    now = datetime.now(timezone.utc)

    # Priority 1: Check Presell Status
    if user.plan == "presell":
        presell_end = parse_firestore_datetime(getattr(user, "presell_end_date", None))
        if presell_end and presell_end > now:
            return True

    # Priority 2: Check Paid Subscription (Using the updated logic that includes grace period)
    if has_active_subscription(user):
        return True
    
    # Priority 3: Check for 14-day trial window
    if is_trial_active(user):
        return True
    
    # Priority 4: Check manual overrides
    plan = (user.plan or "free").lower()
    if plan in ["silver", "gold", "opal"] and getattr(user, "subscription_id", None):
        return True
    
    return False


async def require_silver(user: Optional[User] = Depends(get_current_user)) -> User:
    """
    Ensures access only for Silver/Gold/Opal subscribers or active trial.
    Raises 403 error with upgrade message if access denied.
    """
    # 1️⃣ Check authentication
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2️⃣ Fetch fresh user data from Firestore
    user_ref = db.collection("users").document(user.id)
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # 3️⃣ Create User object with fresh data
    user_data = user_doc.to_dict()
    
    # Add subscription_end to User model if not present
    if "subscription_end" in user_data and not hasattr(User, "subscription_end"):
        user_data_with_sub = {**user_data}
    else:
        user_data_with_sub = user_data
    
    current_user = User(**user_data_with_sub)
    
    # Manually add subscription_end if it exists
    if "subscription_end" in user_data:
        setattr(current_user, "subscription_end", user_data["subscription_end"])

    # 4️⃣ Check access with detailed logging
    logger.info(f"🔍 Checking Silver access for user {current_user.id}")
    logger.info(f"   Plan: {current_user.plan}")
    logger.info(f"   Subscription ID: {current_user.subscription_id}")
    logger.info(f"   Subscription End: {getattr(current_user, 'subscription_end', 'N/A')}")
    logger.info(f"   Trial End: {current_user.trial_end_date}")
    
    has_access = can_access_silver_features(current_user)
    
    if has_access:
        logger.info(f"✅ User {current_user.id} granted Silver access")
        return current_user

    # 5️⃣ Access denied - raise 403 with upgrade message
    logger.warning(f"❌ User {current_user.id} denied Silver access")
    
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error": "subscription_required",
            "message": "Your exclusive access has ended. Upgrade to Payla Silver to continue using this feature.",
            "upgrade_to": "silver",
            "cta": "Upgrade now to unlock premium features",
            "upgrade_url": "/subscription",
            "trial_expired": not is_trial_active(current_user),
            "subscription_expired": not has_active_subscription(current_user),
            "current_plan": current_user.plan
        }
    )


async def check_subscription_optional(user: Optional[User] = Depends(get_current_user)) -> dict:
    """
    Optional subscription check - returns status without blocking access
    Useful for showing upgrade prompts without denying access
    """
    if user is None:
        return {"has_access": False, "reason": "not_authenticated"}
    
    user_ref = db.collection("users").document(user.id)
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        return {"has_access": False, "reason": "user_not_found"}
    
    user_data = user_doc.to_dict()
    current_user = User(**user_data)
    
    # Add subscription_end if present
    if "subscription_end" in user_data:
        setattr(current_user, "subscription_end", user_data["subscription_end"])
    
    has_access = can_access_silver_features(current_user)
    
    if has_access:
        return {
            "has_access": True,
            "plan": current_user.plan,
            "trial_active": is_trial_active(current_user),
            "subscription_active": has_active_subscription(current_user)
        }
    
    return {
        "has_access": False,
        "reason": "no_active_subscription",
        "plan": current_user.plan,
        "should_upgrade": True,
        "trial_expired": not is_trial_active(current_user),
        "subscription_expired": not has_active_subscription(current_user)
    }