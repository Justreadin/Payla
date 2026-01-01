import asyncio
import logging
from datetime import datetime, timezone
import firebase_admin
from firebase_admin import firestore, credentials
from app.core.firebase import db
logger = logging.getLogger("payla")

# Firestore client
try:
    db = firestore.client()
    logger.info("✅ Firestore client ready")
except Exception as e:
    logger.error(f"❌ Failed to initialize Firestore client: {e}")
    raise

from app.routers.payout_router import queue_payout

# Setup logging to see what's happening in terminal
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("payla_sync")
db = firestore.client()

async def sync_missing_invoice_payouts():
    print("🚀 Starting manual sync for paid invoices...")
    
    # 1. Find all paid invoices
    invoices = db.collection("invoices").where("status", "==", "paid").stream()
    
    synced_count = 0
    found_count = 0
    
    for inv in invoices:
        found_count += 1
        data = inv.to_dict()
        reference = data.get("transaction_reference")
        user_id = data.get("sender_id")
        amount = data.get("amount", 0)
        
        if not reference or not user_id:
            print(f"⚠️ Skipping Invoice {inv.id}: Missing reference or user_id")
            continue

        # 2. Check if this transaction is already in the payout ledger
        payout_check = db.collection("payouts").document(reference).get()
        
        if not payout_check.exists:
            print(f"🔄 Syncing missing payout for Invoice: {inv.id} (Amount: ₦{amount})")
            
            # 3. Trigger the logic to update user balance and payout history
            await queue_payout(
                user_id=user_id,
                amount=amount,
                reference=reference,
                payout_type="invoice",
                manual_payout=False
            )
            synced_count += 1
        else:
            print(f"✅ Invoice {inv.id} already exists in payouts. Skipping.")
            
    print(f"\n--- SYNC COMPLETE ---")
    print(f"Total Paid Invoices Found: {found_count}")
    print(f"New Payouts Created: {synced_count}")

if __name__ == "__main__":
    # This is the line that actually starts the script!
    asyncio.run(sync_missing_invoice_payouts())