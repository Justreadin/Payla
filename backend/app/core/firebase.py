import json
import base64
import logging
from firebase_admin import credentials, initialize_app, get_app, firestore, storage
from app.core.config import settings

logger = logging.getLogger("payla")


def init_firebase():
    try:
        get_app()
        logger.info("✅ Firebase Admin SDK already initialized")
        return
    except ValueError:
        pass

    if not settings.PAYLA_FIREBASE_KEY:
        raise RuntimeError("❌ PAYLA_FIREBASE_KEY environment variable is not set")

    try:
        decoded_json = base64.b64decode(settings.PAYLA_FIREBASE_KEY).decode("utf-8")
        service_account_info = json.loads(decoded_json)
        logger.info("🔑 Successfully loaded Firebase credentials from PAYLA_FIREBASE_KEY")
    except Exception as e:
        raise RuntimeError(f"❌ Failed to decode or parse PAYLA_FIREBASE_KEY: {e}")

    project_id = service_account_info.get("project_id")
    if not project_id:
        raise ValueError("❌ 'project_id' missing in Firebase service account JSON")

    cred = credentials.Certificate(service_account_info)

    # Only include storageBucket — required for storage.bucket() with no args
    # Do NOT include databaseURL or projectId — they can interfere with Auth
    initialize_app(cred, {
        "storageBucket": f"{project_id}.appspot.com"
    })

    logger.info(f"🔥 Firebase Admin SDK initialized successfully | Project: {project_id}")


# Run initialization
init_firebase()

# Firestore client
try:
    db = firestore.client()
    logger.info("✅ Firestore client ready")
except Exception as e:
    logger.error(f"❌ Failed to initialize Firestore client: {e}")
    raise

# Storage bucket
try:
    storage_bucket = storage.bucket()  # Works because storageBucket option is set
    logger.info(f"✅ Firebase Storage bucket ready: {storage_bucket.name}")
except Exception as e:
    logger.error(f"❌ Failed to initialize Firebase Storage bucket: {e}")
    storage_bucket = None


__all__ = ["db", "storage_bucket"]