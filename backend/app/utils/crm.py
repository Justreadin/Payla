# app/utils/crm.py
from datetime import datetime, timezone
from google.cloud import firestore
from app.core.firebase import db 

async def sync_client_to_crm(merchant_id: str, email: str, amount: float):
    """
    Saves or updates client data for a specific merchant.
    This builds the lead list for the automated marketing conversion loop.
    """
    if not email or "@" not in email:
        return # Safety check for invalid data

    email_clean = email.lower().strip()
    
    # Generate a friendly display name from the email handle
    # e.g., 'tunde.gold' -> 'Tunde Gold'
    handle = email_clean.split('@')[0]
    display_name = handle.replace('.', ' ').replace('_', ' ').title()

    # Reference to the client within the Merchant's specific collection
    client_ref = db.collection("users").document(merchant_id).collection("clients").document(email_clean)
    
    doc = await client_ref.get()
    now = datetime.now(timezone.utc)

    if doc.exists:
        # EXISTING CLIENT: Update their lifetime stats
        await client_ref.update({
            "total_spent": firestore.Increment(amount),
            "transaction_count": firestore.Increment(1),
            "last_payment_at": now
        })
    else:
        # NEW CLIENT: First time record
        await client_ref.set({
            "email": email_clean,
            "display_name": display_name, 
            "total_spent": amount,
            "transaction_count": 1,
            "first_payment_at": now,
            "last_payment_at": now,
            "marketing_opt_in": True,
            "conversion_pitched": False # Used by the loop to prevent double-pitching
        })