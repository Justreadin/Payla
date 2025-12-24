from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse
from datetime import datetime, timezone
from app.core.firebase import db
import logging

router = APIRouter()
logger = logging.getLogger("payla")

@router.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe(email: str = Query(..., description="The email to unsubscribe")):
    """
    Handle marketing unsubscriptions with an elegant Payla-branded response.
    """
    try:
        # 1. Update suppression list in Firestore
        db.collection("suppression_list").document(email).set({
            "unsubscribed_at": datetime.now(timezone.utc),
            "reason": "marketing_conversion",
            "status": "opt_out"
        })
        
        logger.info(f"🚫 Suppression: {email} unsubscribed from marketing.")

        # 2. Return Elegant HTML
        return f"""
        <html>
            <head>
                <title>Unsubscribed | Payla</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body {{ background: #0A0A0A; color: #FDFDFD; font-family: 'Inter', -apple-system, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }}
                    .card {{ text-align: center; padding: 40px; border: 1px solid rgba(232,180,184,0.2); border-radius: 24px; max-width: 400px; width: 90%; background: #0F0F0F; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }}
                    h1 {{ color: #E8B4B8; font-size: 24px; margin-bottom: 16px; font-weight: 600; }}
                    p {{ color: #B8B8B8; line-height: 1.6; font-size: 15px; margin-bottom: 24px; }}
                    .btn {{ display: inline-block; color: #0A0A0A; background: #E8B4B8; text-decoration: none; padding: 12px 24px; border-radius: 12px; font-size: 14px; font-weight: 600; transition: opacity 0.2s; }}
                    .btn:hover {{ opacity: 0.9; }}
                </style>
            </head>
            <body>
                <div class="card">
                    <h1>Preferences Updated</h1>
                    <p>We've removed <strong>{email}</strong> from our marketing list. You'll still receive receipts and transactional updates for your payments.</p>
                    <p>Layla will miss you, but we respect your inbox.</p>
                    <a href="https://payla.ng" class="btn">Back to Payla</a>
                </div>
            </body>
        </html>
        """
    except Exception as e:
        logger.error(f"Unsubscribe error: {e}")
        return HTMLResponse(content="<h1>Something went wrong.</h1>", status_code=500)