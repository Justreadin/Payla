import asyncio
import httpx
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings

async def test_account_resolution():
    headers = {
        "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}"
    }

    params = {
        "account_number": "0832137807",
        "bank_code": "058",
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            "https://api.paystack.co/bank/resolve",
            headers=headers,
            params=params,
        )

        print("HTTP status:", response.status_code)
        print("Rate-limit remaining:",
              response.headers.get("x-ratelimit-remaining"))
        print("Retry-After:",
              response.headers.get("Retry-After"))
        print("Response:", response.text)

if __name__ == "__main__":
    asyncio.run(test_account_resolution())