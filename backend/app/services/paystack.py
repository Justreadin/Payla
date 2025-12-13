import httpx
from app.core.config import settings

PAYSTACK_SECRET_KEY = settings.PAYSTACK_SECRET_KEY
PAYSTACK_BASE_URL = "https://api.paystack.co"

async def initialize_payment(email: str, amount: float, metadata: dict):
    headers = {
        "Authorization": f"Bearer {PAYSTACK_SECRET_KEY}",
        "Content-Type": "application/json",
    }

    data = {
        "email": email,
        "amount": int(amount * 100),  # kobo
        "metadata": metadata,
        "callback_url": "https://payla.ng/verify",  # redirect after payment
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(f"{PAYSTACK_BASE_URL}/transaction/initialize", json=data, headers=headers)
        response.raise_for_status()
        return response.json()

async def verify_payment(reference: str):
    headers = {"Authorization": f"Bearer {PAYSTACK_SECRET_KEY}"}
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{PAYSTACK_BASE_URL}/transaction/verify/{reference}", headers=headers)
        response.raise_for_status()
        return response.json()
