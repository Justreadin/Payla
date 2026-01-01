import httpx
import asyncio
from app.core.config import settings

# --- CONFIGURATION ---
PAYSTACK_SECRET_KEY = settings.PAYSTACK_SECRET_KEY
BANK_CODE = "058"                    # e.g., 058 for GTBank, 011 for FirstBank
ACCOUNT_NUMBER = "0832137807"        # Your test destination account
AMOUNT_NARA = 1000                   # Amount to test

async def test_paystack_payout():
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        # STEP 1: Create Transfer Recipient
        print("Creating Transfer Recipient...")
        recipient_data = {
            "type": "nuban",
            "name": "Test Payout User",
            "account_number": ACCOUNT_NUMBER,
            "bank_code": BANK_CODE,
            "currency": "NGN"
        }
        
        r_resp = await client.post(
            "https://api.paystack.co/transferrecipient", 
            json=recipient_data, 
            headers=headers
        )
        r_json = r_resp.json()
        
        if not r_json.get("status"):
            print(f"Failed to create recipient: {r_json.get('message')}")
            return

        recipient_code = r_json["data"]["recipient_code"]
        print(f"Recipient Created: {recipient_code}")

        # STEP 2: Initiate Transfer
        print(f"Initiating Transfer of ₦{AMOUNT_NARA}...")
        transfer_data = {
            "source": "balance",
            "amount": AMOUNT_NARA * 100, # Paystack uses Kobo
            "recipient": recipient_code,
            "reason": "Manual Payout Test"
        }

        t_resp = await client.post(
            "https://api.paystack.co/transfer", 
            json=transfer_data, 
            headers=headers
        )
        t_json = t_resp.json()

        if t_json.get("status"):
            print("✅ Transfer Initialized successfully!")
            print(f"Reference: {t_json['data']['reference']}")
            print(f"Status: {t_json['data']['status']}")
        else:
            print(f"❌ Transfer failed: {t_json.get('message')}")

if __name__ == "__main__":
    asyncio.run(test_paystack_payout())