import requests
import json
from app.core.config import settings

# --- CONFIGURATION ---
PAYSTACK_SECRET_KEY = settings.PAYSTACK_SECRET_KEY
SUBACCOUNT_CODE = "ACCT_ef4pm6rr9q5i2pf" 
USER_BVN = "22748030792" 

url = f"https://api.paystack.co/subaccount/{SUBACCOUNT_CODE}"

headers = {
    "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
    "Content-Type": "application/json"
}

# 1. 'OPAY' code is 999992
# 2. business_name should be the FULL legal name on the BVN
payload = {
    "business_name": "Akintoye Favour Truth", 
    "settlement_bank": "999992", 
    "account_number": "7063749513",
    "metadata": {
        "bvn": USER_BVN,
        "custom_fields": [
            {
                "display_name": "BVN",
                "variable_name": "bvn",
                "value": USER_BVN
            }
        ]
    }
}

try:
    print(f"--- Sending Update Request for {SUBACCOUNT_CODE} ---")
    # Using PUT as per Paystack Subaccount docs
    response = requests.put(url, headers=headers, json=payload)
    res_data = response.json()

    if response.status_code == 200:
        print("✅ API accepted the request!")
        # Access data safely
        data = res_data.get('data', {})
        print(f"Subaccount Name: {data.get('business_name')}")
        print(f"Status in Response: {data.get('status')}")
        print("\nCHECK DASHBOARD: If the name matches the BVN, status will flip to 'active'.")
    else:
        print("❌ Failed to update.")
        print(f"Status Code: {response.status_code}")
        print(f"Error Message: {res_data.get('message')}")
except Exception as e:
    print(f"An error occurred: {e}")