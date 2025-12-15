import json
import base64
import logging
from firebase_admin import credentials, initialize_app, get_app, firestore, storage
from app.core.config import settings  # ✅ import your config

logger = logging.getLogger("payla")


def init_firebase():
    """Initialize Firebase Admin SDK and Firestore/Storage clients using PAYLA_FIREBASE_KEY."""
    try:
        get_app()
        logger.info("✅ Firebase Admin SDK already initialized")
        return
    except ValueError:
        pass

    if not settings.PAYLA_FIREBASE_KEY:
        raise RuntimeError("❌ PAYLA_FIREBASE_KEY not set in settings")

    try:
        decoded_json = base64.b64decode(settings.PAYLA_FIREBASE_KEY).decode("utf-8")
        service_account_info = json.loads(decoded_json)
        logger.info("🔑 Loaded Firebase credentials from PAYLA_FIREBASE_KEY")
    except Exception as e:
        raise RuntimeError(f"❌ Failed to decode PAYLA_FIREBASE_KEY: {e}")

    # -------------------------------
    # Validate service account
    # -------------------------------
    project_id = service_account_info.get("project_id")
    if not project_id:
        raise ValueError("❌ project_id missing in Firebase service account JSON")

    # -------------------------------
    # Initialize Firebase
    # -------------------------------
    cred = credentials.Certificate(service_account_info)

    initialize_app(cred, {
        "projectId": project_id,
        "databaseURL": f"https://firestore.googleapis.com/v1/projects/{project_id}/databases/(default)",
        "storageBucket": f"{project_id}.appspot.com"
    })

    logger.info(f"🔥 Firebase initialized successfully | Project: {project_id}")


# ------------------------------------------------------------
# FIRESTORE CLIENT
# ------------------------------------------------------------
init_firebase()

try:
    db: firestore.Client = firestore.client()
    logger.info("✅ Firestore client ready")
except Exception as e:
    logger.error(f"❌ Failed to initialize Firestore client: {e}")
    raise e

# ------------------------------------------------------------
# STORAGE BUCKET
# ------------------------------------------------------------
try:
    storage_bucket = storage.bucket()
    logger.info("✅ Firebase Storage bucket ready")
except Exception as e:
    logger.error(f"❌ Failed to initialize Firebase Storage bucket: {e}")
    storage_bucket = None
