from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import secrets
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/token", tags=["TokenGate"])

# In-memory temporary store (auto-expires)
TOKEN_STORE = {}

TOKEN_TTL_MINUTES = 5


def clean_expired_tokens():
    now = datetime.utcnow()
    expired = [t for t, data in TOKEN_STORE.items() if data["expires"] < now]
    for t in expired:
        del TOKEN_STORE[t]


@router.post("/generate")
async def generate_access_token():
    """Generate a one-time thank-you access token"""
    clean_expired_tokens()

    token = secrets.token_urlsafe(24)
    TOKEN_STORE[token] = {
        "expires": datetime.utcnow() + timedelta(minutes=TOKEN_TTL_MINUTES)
    }

    return {"token": token, "expires_in": TOKEN_TTL_MINUTES * 60}


@router.get("/verify")
async def verify_access_token(token: str):
    """Verify thank-you token"""
    clean_expired_tokens()

    data = TOKEN_STORE.get(token)
    if not data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    return {"valid": True}
