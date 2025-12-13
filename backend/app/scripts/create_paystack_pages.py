import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime

# Ensure Python can find `app` module
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from app.core.firebase import db
from app.core.paystack import create_permanent_payment_page

# Logging setup
logger = logging.getLogger("payla")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

async def create_missing_paystack_pages():
    paylinks_ref = db.collection("paylinks")
    docs = paylinks_ref.get()

    created_count = 0
    skipped_count = 0
    failed_count = 0

    for doc in docs:
        data = doc.to_dict()
        paylink_id = doc.id
        username = data.get("username")
        display_name = data.get("display_name", "Payla User")

        if not username or not display_name:
            logger.warning(f"Invalid paylink {paylink_id} — missing username/display_name")
            failed_count += 1
            continue

        # Skip if Paystack page already exists
        if data.get("paystack_page_url") and data.get("paystack_reference"):
            logger.info(f"Paystack page exists for @{username} — skipping")
            skipped_count += 1
            continue

        try:
            # Call Paystack API — only 2 arguments
            page_data = await create_permanent_payment_page(username, display_name)

            # Save to Firestore
            paylinks_ref.document(paylink_id).update({
                "paystack_page_url": page_data["url"],
                "paystack_reference": page_data["reference"],
                "updated_at": datetime.utcnow()
            })

            logger.info(f"SUCCESS: Paystack page created for @{username} → {page_data['url']}")
            created_count += 1

        except Exception as e:
            logger.error(f"FAILED for @{username}: {e}")
            failed_count += 1

    # Final summary
    logger.info("====== FINAL SUMMARY ======")
    logger.info(f"Total Paylinks processed : {len(docs)}")
    logger.info(f"Created successfully     : {created_count}")
    logger.info(f"Skipped (already exists) : {skipped_count}")
    logger.info(f"Failed                    : {failed_count}")


if __name__ == "__main__":
    asyncio.run(create_missing_paystack_pages())
