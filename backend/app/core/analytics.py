# core/analytics.py
from datetime import datetime, timezone
from collections import defaultdict
from typing import Dict, Any
import logging

from google.cloud import firestore
from app.core.firebase import db  # your Firestore client

logger = logging.getLogger("payla.analytics")


# -------------------------------
# Increment counters for a paylink
# -------------------------------
def increment_paylink_metric(paylink_id: str, metric: str):
    """
    Increment a simple counter (page_views or transfer_clicks)
    in the paylink_analytics document.
    """
    if metric not in ("page_views", "transfer_clicks"):
        raise ValueError(f"Unsupported metric: {metric}")

    doc_ref = db.collection("paylink_analytics").document(paylink_id)
    try:
        doc_ref.set(
            {
                metric: firestore.Increment(1),
                "last_updated": datetime.now(timezone.utc)
            },
            merge=True
        )
        logger.debug(f"Incremented {metric} for paylink_id={paylink_id}")
    except Exception as e:
        logger.error(f"Failed to increment {metric} for {paylink_id}: {e}")


# -------------------------------
# Log granular events
# -------------------------------
def log_paylink_event(paylink_id: str, event_type: str):
    """
    Log an event for a paylink.
    Example event_type: 'page_view', 'transfer_click'
    """
    if event_type not in ("page_view", "transfer_click"):
        raise ValueError(f"Unsupported event_type: {event_type}")

    try:
        db.collection("paylink_analytics_events").add({
            "paylink_id": paylink_id,
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc)
        })
        logger.debug(f"Logged event {event_type} for paylink_id={paylink_id}")
    except Exception as e:
        logger.error(f"Failed to log event {event_type} for {paylink_id}: {e}")


# -------------------------------
# Increment daily counters
# -------------------------------
def increment_daily_metric(paylink_id: str, metric: str):
    """
    Track daily aggregates in the document for analytics trends.
    Stored as a map: daily_page_views = { '2025-11-26': 12 }
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc_ref = db.collection("paylink_analytics").document(paylink_id)

    try:
        field = f"daily_{metric}"
        doc_ref.set({
            field: {today: firestore.Increment(1)},
            "last_updated": datetime.now(timezone.utc)
        }, merge=True)
        logger.debug(f"Incremented daily {metric} for {paylink_id} on {today}")
    except Exception as e:
        logger.error(f"Failed to increment daily {metric} for {paylink_id}: {e}")


# -------------------------------
# Fetch analytics for a paylink
# -------------------------------
def get_paylink_analytics(paylink_id: str) -> Dict[str, Any]:
    """
    Return aggregated metrics for a paylink.
    """
    doc_ref = db.collection("paylink_analytics").document(paylink_id)
    doc = doc_ref.get()
    if not doc.exists:
        return {
            "page_views": 0,
            "transfer_clicks": 0,
            "daily_page_views": {},
            "daily_transfer_clicks": {}
        }

    data = doc.to_dict()
    return {
        "page_views": data.get("page_views", 0),
        "transfer_clicks": data.get("transfer_clicks", 0),
        "daily_page_views": data.get("daily_page_views", {}),
        "daily_transfer_clicks": data.get("daily_transfer_clicks", {}),
        "last_updated": data.get("last_updated")
    }


# -------------------------------
# Fetch analytics over a date range
# -------------------------------
def get_analytics_summary(paylink_id: str, start_date: str, end_date: str) -> Dict[str, int]:
    """
    Get daily metrics between start_date and end_date (YYYY-MM-DD)
    Returns counts for page_views and transfer_clicks.
    """
    analytics = get_paylink_analytics(paylink_id)
    daily_views = analytics.get("daily_page_views", {})
    daily_transfers = analytics.get("daily_transfer_clicks", {})

    filtered_views = {k: v for k, v in daily_views.items() if start_date <= k <= end_date}
    filtered_transfers = {k: v for k, v in daily_transfers.items() if start_date <= k <= end_date}

    return {
        "page_views": sum(filtered_views.values()),
        "transfer_clicks": sum(filtered_transfers.values()),
        "daily_page_views": filtered_views,
        "daily_transfer_clicks": filtered_transfers
    }