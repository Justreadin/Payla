from app.utils.firebase import firestore_run
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import RedirectResponse
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import logging

from app.core.firebase import db
from app.core.auth import get_current_user
from app.models.user_model import User
from app.models.invoice_model import Invoice
from app.core.subscription import require_silver
from app.routers.invoice_router import create_invoice_draft, publish_invoice
from app.core.config import settings
from google.cloud.firestore_v1.base_query import FieldFilter
logger = logging.getLogger("payla")
router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def require_login(user: Optional[User]):
    if user is None:
        return RedirectResponse(url=f"{settings.BACKEND_URL}/entry")
    return None

from app.utils.firebase import firestore_run
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import RedirectResponse
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta
import logging

from app.core.firebase import db
from app.core.auth import get_current_user
from app.models.user_model import User
from app.models.invoice_model import Invoice
from app.core.subscription import require_silver
from app.routers.invoice_router import create_invoice_draft, publish_invoice
from app.core.config import settings
from google.cloud.firestore_v1.base_query import FieldFilter

logger = logging.getLogger("payla")
router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

def require_login(user: Optional[User]):
    if user is None:
        return RedirectResponse(url=f"{settings.BACKEND_URL}/entry")
    return None

@router.get("/", response_model=Dict[str, Any])
async def get_dashboard_data(current_user: Optional[User] = Depends(get_current_user)):
    redirect = require_login(current_user)
    if redirect:
        return redirect

    user_id = current_user.id
    now = datetime.now(timezone.utc)

    # 1. Official Balance & Revenue Breakdown
    # These fields are updated automatically by the queue_payout utility
    total_earned = getattr(current_user, "total_earned", 0.0)
    invoice_revenue = getattr(current_user, "total_invoice_revenue", 0.0)
    paylink_revenue = getattr(current_user, "total_paylink_revenue", 0.0)
    
    subaccount_code = getattr(current_user, "paystack_subaccount_code", None)

    # 2. Fetch Invoices for Aging Analysis (Pending/Overdue)
    invoices_query = await firestore_run(
        db.collection("invoices")
        .where(filter=FieldFilter("sender_id", "==", user_id))
        .stream
    )

    invoices = []
    pending_amount = 0.0
    overdue_amount = 0.0
    overdue_count = 0

    for doc in invoices_query:
        inv_data = doc.to_dict()
        if inv_data.get("status") == "draft": continue

        inv_data["id"] = doc.id
        inv = Invoice(**inv_data)

        # Logic to Sync Overdue Status
        if inv.status == "pending" and inv.due_date:
            due_date_utc = inv.due_date.replace(tzinfo=timezone.utc)
            if due_date_utc < now:
                await firestore_run(
                    db.collection("invoices").document(inv.id).update, 
                    {"status": "overdue", "updated_at": now}
                )
                inv.status = "overdue"

        if inv.status == "pending":
            pending_amount += inv.amount
        elif inv.status == "overdue":
            overdue_amount += inv.amount
            pending_amount += inv.amount # Overdue is still technically "pending" payment
            overdue_count += 1
        
        invoices.append(inv)

    # 3. Paylink Details
    paylink_doc = await firestore_run(db.collection("paylinks").document(user_id).get)
    paylink_data = paylink_doc.to_dict() if paylink_doc.exists else {}
    paylink_url = paylink_data.get("link_url") or f"{settings.FRONTEND_URL}/@{current_user.username}"

    # 4. Settlement Summary (T+1 Logic)
    # Provides transparency on when the 'Total Earned' reaches their bank
    next_settlement = now + timedelta(days=1)
    if now.weekday() >= 4:  # Fri, Sat, Sun settle on Monday
        days_to_monday = (7 - now.weekday()) % 7
        next_settlement = now + timedelta(days=days_to_monday if days_to_monday > 0 else 7)

    return {
        "stats": {
            "total_earned": round(total_earned, 2), # Master balance
            "invoice_revenue": round(invoice_revenue, 2),
            "paylink_revenue": round(paylink_revenue, 2),
            "pending_amount": round(pending_amount, 2),
            "overdue_amount": round(overdue_amount, 2),
            "total_invoices": len(invoices),
            "overdue_count": overdue_count,
            "has_earnings": total_earned > 0,
            "is_subaccount_linked": bool(subaccount_code),
            "next_settlement_estimate": next_settlement.strftime("%Y-%m-%d")
        },
        # Replace the "invoices" list comprehension at the end of get_dashboard_data:
        "invoices": [
            {**inv.dict(by_alias=True), "invoice_url": f"{settings.BACKEND_URL}{inv.invoice_url}" if inv.invoice_url else None}
            for inv in sorted(
                invoices, 
                key=lambda x: (x.created_at if x.created_at.tzinfo else x.created_at.replace(tzinfo=timezone.utc)) if x.created_at else now, 
                reverse=True
            )[:10]
        ],
        "paylink": {
            "url": paylink_url,
            "total_received": round(paylink_revenue, 2)
        }
    }

@router.get("/refresh", response_model=Dict[str, Any])
async def refresh_dashboard_stats(current_user: User = Depends(get_current_user)):
    """Lightweight endpoint for auto-reloading dashboard stats and recent activity."""
    # This calls your existing logic but could be optimized to only fetch 
    # changed data if needed. For now, we reuse your existing logic.
    return await get_dashboard_data(current_user)
    

@router.post("/quick-invoice", response_model=dict)
async def create_quick_invoice(
    payload: dict,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_silver)
):
    from app.models.invoice_model import InvoiceCreate
    from app.core.notifications import create_notification

    logger.info(f"Received payload for quick invoice: {payload}")

    required_fields = ["description", "amount", "due_date"]
    missing_fields = [k for k in required_fields if k not in payload]
    if missing_fields:
        raise HTTPException(400, detail=f"Missing fields: {missing_fields}")

    # Parse due_date
    due_date_str = payload.get("due_date")
    try:
        due_date = datetime.fromisoformat(due_date_str.replace("Z", "+00:00"))
    except Exception:
        try:
            due_date = datetime.strptime(due_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except Exception:
            raise HTTPException(400, detail=f"Invalid due_date format: {due_date_str}")

    # Validate amount
    try:
        amount = float(payload.get("amount"))
        if amount <= 0:
            raise ValueError
    except Exception:
        raise HTTPException(400, detail=f"Invalid amount: {payload.get('amount')}")

    # Create ephemeral draft
    draft = InvoiceCreate(
        description=payload["description"],
        amount=amount,
        currency=payload.get("currency", "NGN"),
        due_date=due_date,
        client_email="client@payla.vip",
        is_quick=True
    )

    draft_invoice = await create_invoice_draft(draft, current_user)

    published = await publish_invoice(
        invoice_id=draft_invoice.id,
        background_tasks=background_tasks,
        current_user=current_user
    )

    base_url = str(settings.BACKEND_URL).rstrip('/')
    invoice_url = f"{base_url}{published.invoice_url}"

    create_notification(
        user_id=current_user.id,
        title="Quick Invoice Sent",
        message=f"Invoice of ₦{amount:,} created",
        type="success",
        link="/dashboard/invoice"
    )

    return {
        "success": True,
        "invoice_id": published.id,
        "invoice_url": invoice_url,
        "message": "Invoice created successfully"
    }