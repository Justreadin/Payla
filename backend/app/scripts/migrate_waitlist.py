# scripts/migrate_waitlist.py
import csv
import os
from datetime import datetime
from app.core.firebase import db
import logging

logger = logging.getLogger("migrate_waitlist")

def migrate():
    csv_path = "waitlist.csv"
    if not os.path.exists(csv_path):
        logger.info("waitlist.csv not found — skipping migration.")
        return

    count = 0
    with open(csv_path, newline="") as f:s
    reader = csv.reader(f)
    for row in reader:
            email = row[0].strip().lower()
            if not email:
                continue

            doc_ref = db.collection("waitlist").document(email)
            if not doc_ref.get().exists:
                doc_ref.set({
                    "email": email,
                    "joined_at": datetime.utcnow(),
                    "verified": True
                })
                logger.info(f"Added: {email}")
                count += 1
            else:
                logger.info(f"Skipped (exists): {email}")

    logger.info(f"Waitlist migration complete: {count} users added.")
    # DO NOT DELETE CSV — keep for audit