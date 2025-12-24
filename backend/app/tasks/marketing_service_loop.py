import asyncio
import logging
from datetime import datetime, timezone, timedelta
from firebase_admin import firestore
from app.tasks.reminder_service_loop import send_single_channel
from app.utils.marketing import generate_marketing_content, MARKETING_TEMPLATES

db = firestore.client()
logger = logging.getLogger("payla.marketing")

async def get_spots_left():
    """Dynamically calculate remaining Founding Creator spots"""
    try:
        total_limit = 500
        count_query = db.collection("users").where("presell_claimed", "==", True).count()
        result = await asyncio.to_thread(count_query.get)
        count = result[0][0].value
        return max(total_limit - count, 7)
    except:
        return 373

async def process_conversion(email: str, user_id: str, spots: int, doc_id: str, collection_name: str):
    """Logic to check Client status and send the pitch"""
    email_clean = email.lower().strip()
    
    # 1. Safety Checks: Is Client already a User? OR on your suppression_list?
    is_user_query = db.collection("users").where("email", "==", email_clean).limit(1).get()
    is_suppressed = db.collection("suppression_list").document(email_clean).get()

    if not is_user_query and not is_suppressed.exists:
        
        # 2. Get the generated Client name from the User's CRM sub-collection
        crm_ref = db.collection("users").document(user_id).collection("clients").document(email_clean)
        crm_doc = await asyncio.to_thread(crm_ref.get)
        crm_data = crm_doc.to_dict() if crm_doc.exists else {}

        # 3. Get User (Merchant) Info from User Model for context
        user_doc = await asyncio.to_thread(db.collection("users").document(user_id).get)
        u_data = user_doc.to_dict() if user_doc.exists else {}
        user_name = u_data.get("business_name") or u_data.get("full_name") or "a creator"

        # 4. Prepare Context
        context = {
            "display_name": crm_data.get("display_name") or "there",
            "business_name": user_name,
            "spots_left": spots,
            "unsubscribe_link": f"https://payla.ng/unsubscribe?email={email_clean}" # Points to your existing endpoint
        }
        
        # 5. Generate and Send Pitch
        subject = MARKETING_TEMPLATES["client_conversion"]["subject"].format(**context)
        html = generate_marketing_content("client_conversion", context)

        await send_single_channel(
            method="email",
            invoice={"client_email": email_clean},
            msg="",
            subject=subject,
            html=html,
            email_type="marketing_conversion"
        )
        logger.info(f"🎯 Conversion pitch sent to Client: {email_clean}")

    # 6. Mark as processed everywhere so we don't repeat the check
    batch = db.batch()
    batch.update(db.collection(collection_name).document(doc_id), {"conversion_pitched": True})
    
    # Also update the Client record under the User
    client_ref = db.collection("users").document(user_id).collection("clients").document(email_clean)
    batch.update(client_ref, {"conversion_pitched": True})
    
    await asyncio.to_thread(batch.commit)

async def marketing_loop():
    logger.info("📈 Marketing & Conversion Loop started")
    while True:
        try:
            now = datetime.now(timezone.utc)
            target_time = now - timedelta(days=3)
            spots = await get_spots_left()

            # --- PART A: INVOICES ---
            recent_invoices = db.collection("invoices")\
                .where("status", "==", "paid")\
                .where("conversion_pitched", "==", False)\
                .where("paid_at", "<=", target_time)\
                .limit(20).stream()

            for doc in recent_invoices:
                inv = doc.to_dict()
                if inv.get("client_email"):
                    await process_conversion(
                        email=inv["client_email"],
                        user_id=inv["sender_id"],
                        spots=spots,
                        doc_id=doc.id,
                        collection_name="invoices"
                    )

            # --- PART B: PAYLINKS ---
            recent_paylinks = db.collection("paylink_transactions")\
                .where("status", "==", "success")\
                .where("conversion_pitched", "==", False)\
                .where("created_at", "<=", target_time)\
                .limit(20).stream()

            for doc in recent_paylinks:
                txn = doc.to_dict()
                if txn.get("payer_email"):
                    await process_conversion(
                        email=txn["payer_email"],
                        user_id=txn["user_id"],
                        spots=spots,
                        doc_id=doc.id,
                        collection_name="paylink_transactions"
                    )

        except Exception as e:
            logger.error(f"Error in marketing loop: {e}")
            
        await asyncio.sleep(3600 * 4) # Runs every 4 hours