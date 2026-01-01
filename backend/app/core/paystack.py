import httpx
import logging
from app.core.config import settings
from datetime import datetime, timezone

logger = logging.getLogger("payla")

# --- NEW: Create Subaccount ---
async def create_paystack_subaccount(business_name: str, bank_code: str, account_number: str) -> str:
    """
    Creates a Paystack Subaccount for a creator.
    Returns the subaccount_code (e.g., 'ACCT_xxxxxx')
    """
    url = "https://api.paystack.co/subaccount"
    headers = {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "business_name": business_name,
        "settlement_bank": bank_code,
        "account_number": account_number,
        "percentage_charge": 0,  # Payla takes 0%, Creator gets 100% minus Paystack fees
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            res_data = response.json()
            
            if response.status_code in (200, 201) and res_data.get("status"):
                sub_code = res_data["data"]["subaccount_code"]
                logger.info(f"Subaccount created for {business_name}: {sub_code}")
                return sub_code
            
            logger.error(f"Paystack Subaccount error: {res_data.get('message')}")
            return None
    except Exception as e:
        logger.error(f"Failed to create subaccount for {business_name}: {e}")
        return None

# --- UPDATED: Permanent Payment Page ---
async def create_permanent_payment_page(username: str, display_name: str, subaccount_code: str = None) -> dict:
    """
    Creates a Paystack Payment Page. 
    If subaccount_code is provided, money is automatically routed to the creator.
    """
    base_slug = f"payla-{username.lower()}"
    url = "https://api.paystack.co/page"
    headers = {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "name": f"Pay {display_name} (@{username})",
        "description": f"Send money to @{username} via Payla",
        "amount": None,
        "redirect_url": f"{settings.FRONTEND_URL}/payment-success",
    }

    # If user has a subaccount, attach it to the page
    if subaccount_code:
        payload["subaccount"] = subaccount_code
        # 'subaccount' means the creator pays the Paystack fee (1.5% + ₦100)
        # 'account' means Payla (you) pays the fee. 
        payload["bearer"] = "subaccount" 

    # Try numeric suffixes for slug uniqueness
    async with httpx.AsyncClient(timeout=15.0) as client:
        for i in range(10):
            slug = base_slug if i == 0 else f"{base_slug}-{i+2}"
            payload["slug"] = slug

            try:
                response = await client.post(url, json=payload, headers=headers)
                
                if response.status_code in (200, 201):
                    data = response.json()["data"]
                    return {
                        "url": data.get("url") or f"https://paystack.com/pay/{data['slug']}",
                        "reference": str(data["id"]),
                        "slug": data["slug"]
                    }

                if response.status_code == 400:
                    error_msg = response.json().get("message", "")
                    if "slug already exists" in error_msg.lower():
                        continue
                    raise ValueError(error_msg)

                response.raise_for_status()
            except Exception as e:
                logger.error(f"Slug attempt {i} failed for @{username}: {e}")

        # Final Fallback: Timestamp slug
        timestamp_slug = f"{base_slug}-{int(datetime.now(timezone.utc).timestamp())}"
        payload["slug"] = timestamp_slug
        response = await client.post(url, json=payload, headers=headers)
        data = response.json()["data"]
        return {
            "url": data.get("url") or f"https://paystack.com/pay/{data['slug']}",
            "reference": str(data["id"]),
            "slug": data["slug"]
        }