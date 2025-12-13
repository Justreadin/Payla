# utils/notifications.py
from app.core.firebase import db
from datetime import datetime, timezone

def create_notification(user_id: str, title: str, message: str, type: str = "info", link: str = None):
    notif = {
        "user_id": user_id,
        "title": title,
        "message": message,
        "type": type,
        "link": link,
        "read": False,
        "created_at": datetime.now(timezone.utc)
    }
    db.collection("notifications").add(notif)