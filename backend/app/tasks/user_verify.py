# tasks.py or wherever your Celery tasks are

from celery import shared_task
from firebase_admin import auth
from datetime import datetime
import logging
from datetime import datetime
from app.core.firebase import db
from app.core.config import settings

logger = logging.getLogger("payla")
@shared_task
def delete_unverified_user(firebase_uid: str):
    """
    Deletes a Firebase Auth user and Firestore document if unverified.
    """
    try:
        user_doc = db.collection("users").document(firebase_uid).get()
        if not user_doc.exists:
            logger.info(f"❌ No Firestore user found for UID {firebase_uid}, skipping deletion")
            return

        user_data = user_doc.to_dict()
        if user_data.get("email_verified", False):
            logger.info(f"✅ User {firebase_uid} is verified, skipping deletion")
            return

        # Delete from Auth
        auth.delete_user(firebase_uid)
        # Delete Firestore document
        db.collection("users").document(firebase_uid).delete()
        logger.info(f"🗑️ Deleted unverified user {firebase_uid}")
    except Exception as e:
        logger.error(f"🔥 Failed to delete unverified user {firebase_uid}: {e}")
