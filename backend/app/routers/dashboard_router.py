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


@router.get("/", response_model=Dict[str, Any])
async def get_dashboard_data(current_user: Optional[User] = Depends(get_current_user)):
    redirect = require_login(current_user)
    if redirect:
        return redirect

    user_id = current_user.id
    now = datetime.now(timezone.utc)

    # === 1. User Balance (The Source of Truth) ===
    # Use the pre-calculated total from the user document (updated by webhook)
    # This includes both Invoices AND Paylink earnings.
    official_total_earned = getattr(current_user, "total_earned", 0.0)
    subaccount_id = getattr(current_user, "paystack_subaccount_id", None)

    # === 2. Fetch Invoices ===
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

        if inv_data.get("status") == "draft":
            continue

        inv_data["id"] = doc.id
        inv_data["_id"] = doc.id 

        inv = Invoice(**inv_data)

        if inv.due_date and inv.due_date.tzinfo is None:
            inv.due_date = inv.due_date.replace(tzinfo=timezone.utc)

        # ⏰ Auto-mark overdue invoices
        if (
            inv.status == "pending"
            and inv.due_date
            and inv.due_date < now
        ):
            await firestore_run(
                db.collection("invoices")
                .document(inv.id)
                .update,
                {
                    "status": "overdue",
                    "updated_at": now
                }
            )
            inv.status = "overdue"

        # === Stats aggregation ===
        # Note: We don't calculate total_earned here anymore to avoid missing Paylink money
        if inv.status == "pending":
            pending_amount += inv.amount
            
        elif inv.status == "overdue":
            overdue_amount += inv.amount
            pending_amount += inv.amount
            overdue_count += 1

        invoices.append(inv)

    # === 3. Sort invoices ===
    invoices.sort(
        key=lambda x: (
            0 if x.status == "overdue" else
            1 if x.status == "pending" else
            2 if x.status == "paid" else
            3 if x.status == "failed" else 4,
            -(x.created_at.timestamp() if x.created_at else 0)
        )
    )

    # === 4. Paylink ===
    paylink_doc = await firestore_run(
        db.collection("paylinks").document(user_id).get
    )
    paylink_data = paylink_doc.to_dict() if paylink_doc.exists else {}
    paylink_url = (
        paylink_data.get("link_url")
        if paylink_data
        else f"{settings.BACKEND_URL}/@{current_user.username}"
    )

    return {
        "stats": {
            "total_earned": round(official_total_earned, 2),
            "pending_amount": round(pending_amount, 2),
            "overdue_amount": round(overdue_amount, 2),
            "total_invoices": len(invoices),
            "overdue_count": overdue_count,
            "draft_count": 0,
            "growth_trend": "0%",
            "has_earnings": official_total_earned > 0,
            "is_subaccount_linked": bool(subaccount_id) # Useful for frontend warnings
        },
        "invoices": [
            {
                **inv.dict(by_alias=True),
                "invoice_url": (
                    f"{settings.BACKEND_URL}{inv.invoice_url}"
                    if inv.invoice_url
                    else None
                )
            }
            for inv in invoices[:50]
        ],
        "paylink": {
            "url": paylink_url,
            "total_received": paylink_data.get("total_received", 0)
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