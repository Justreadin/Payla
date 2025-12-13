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

    # === Fetch invoices ===
    invoices_query = (
        db.collection("invoices")
        .where("sender_id", "==", user_id)
        .stream()
    )

    invoices = []
    total_earned = 0.0
    pending_amount = 0.0
    overdue_count = 0

    for doc in invoices_query:
        inv_data = doc.to_dict()

        # 🔥 CRITICAL FIX: Skip ALL drafts (dashboard must never show drafts)
        if inv_data.get("status") == "draft":
            continue

        inv = Invoice(**inv_data)

        # Ensure due_date has timezone
        if inv.due_date and inv.due_date.tzinfo is None:
            inv.due_date = inv.due_date.replace(tzinfo=timezone.utc)

        # Auto-update overdue invoices
        if inv.status == "pending" and inv.due_date and inv.due_date < now:
            db.collection("invoices").document(inv.id).update({
                "status": "overdue",
                "updated_at": now
            })
            inv.status = "overdue"

        # === Stats ===
        if inv.status == "paid":
            total_earned += inv.amount

        elif inv.status in ("pending", "overdue"):
            pending_amount += inv.amount
            if inv.status == "overdue":
                overdue_count += 1

        invoices.append(inv)

    # === Sort invoices ===
    # pending → overdue → paid → failed (most recent first)
    invoices.sort(
        key=lambda x: (
            0 if x.status == "pending" else
            1 if x.status == "overdue" else
            2 if x.status == "paid" else
            3 if x.status == "failed" else 4,
            -(x.created_at.timestamp() if x.created_at else 0)
        )
    )

    # === Paylink ===
    paylink_doc = db.collection("paylinks").document(user_id).get()
    paylink = paylink_doc.to_dict() if paylink_doc.exists else None
    paylink_url = (
        paylink["link_url"]
        if paylink
        else f"{settings.BACKEND_URL}/@{current_user.username}"
    )

    return {
        "stats": {
            "total_earned": round(total_earned, 2),
            "pending_amount": round(pending_amount, 2),
            "total_invoices": len(invoices),
            "overdue_count": overdue_count,
            "draft_count": 0,  # Drafts are intentionally hidden
            "growth_trend": "0%"
        },
        "invoices": [
            {
                **i.dict(by_alias=True),
                "invoice_url": (
                    f"{settings.BACKEND_URL}{i.invoice_url}"
                    if i.invoice_url else None
                )
            }
            for i in invoices[:20]
        ],
        "paylink": {
            "url": paylink_url
        }
    }


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
        is_quick=True  # <-- ensures invisible in dashboard
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
