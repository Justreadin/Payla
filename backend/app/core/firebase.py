import os
import json
import logging
from firebase_admin import credentials, initialize_app, get_app, firestore, storage
from app.core.config import settings  # ✅ import your config

logger = logging.getLogger("payla")


def init_firebase():
    """Initialize Firebase Admin SDK and Firestore/Storage clients."""
    try:
        get_app()
        logger.info("✅ Firebase Admin SDK already initialized")
        return
    except ValueError:
        pass

    cred_path = settings.GOOGLE_APPLICATION_CREDENTIALS
    if not cred_path:
        raise RuntimeError("❌ GOOGLE_APPLICATION_CREDENTIALS not set in settings")

    cred_path = os.path.abspath(cred_path)
    if not os.path.exists(cred_path):
        raise FileNotFoundError(f"❌ Firebase credentials not found: {cred_path}")

    with open(cred_path, "r") as f:
        service_account_info = json.load(f)

    project_id = service_account_info.get("project_id")
    if not project_id:
        raise ValueError("❌ project_id missing in Firebase service account JSON")

    cred = credentials.Certificate(service_account_info)

    # Initialize Firebase app with Firestore and Storage
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
