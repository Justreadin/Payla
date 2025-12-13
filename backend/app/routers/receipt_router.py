# routers/receipt_router.py → PERSONAL BRANDED PDF RECEIPTS
from app.core.subscription import require_silver
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from app.core.auth import get_current_user
from io import BytesIO
from datetime import datetime
import httpx

from app.core.firebase import db
from app.models.user_model import User
from app.core.auth import get_current_user
from app.core.config import Settings

router = APIRouter(prefix="/receipt", tags=["Receipts"])

styles = getSampleStyleSheet()
title_style = ParagraphStyle(
    'CustomTitle',
    parent=styles['Heading1'],
    fontSize=28,
    spaceAfter=30,
    textColor=colors.HexColor("#1a1a1a"),
    alignment=1  # Center
)
subtitle_style = ParagraphStyle(
    'Subtitle',
    parent=styles['Normal'],
    fontSize=12,
    textColor=colors.grey,
    alignment=1
)

async def fetch_logo(url: str) -> BytesIO:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return BytesIO(resp.content)
    except:
        pass
    return None


@router.get("/paylink/{reference}.pdf")
async def generate_paylink_receipt(reference: str,  current_user: User = Depends(require_silver)):
    # Get transaction
    txn_doc = db.collection("paylink_transactions").document(reference).get()
    if not txn_doc.exists:
        raise HTTPException(404, "Transaction not found")
    
    txn = txn_doc.to_dict()
    if txn.get("status") != "success":
        raise HTTPException(400, "Payment not successful")

    # Get paylink owner
    user_doc = db.collection("users").document(txn["user_id"]).get()
    if not user_doc.exists:
        raise HTTPException(404, "User not found")
    user = user_doc.to_dict()

    # Get paylink
    paylink_doc = db.collection("paylinks").document(txn["paylink_id"]).get()
    paylink = paylink_doc.to_dict() if paylink_doc.exists else {}

    # Build receipt
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1*inch, bottomMargin=1*inch)
    story = []

    # Logo
    logo_url = user.get("logo_url")
    if logo_url:
        logo_data = await fetch_logo(logo_url)
        if logo_data:
            try:
                img = Image(logo_data, width=2*inch, height=2*inch)
                img.hAlign = 'CENTER'
                story.append(img)
                story.append(Spacer(1, 20))
            except:
                pass

    # Business Name
    business_name = user.get("business_name") or user.get("full_name") or "Payla Merchant"
    story.append(Paragraph(business_name, title_style))
    story.append(Paragraph("Payment Receipt", subtitle_style))
    story.append(Spacer(1, 40))

    # Receipt Details Table
    data = [
        ["Receipt ID", reference[:12].upper()],
        ["Date", datetime.fromtimestamp(txn["created_at"].timestamp() if hasattr(txn["created_at"], "timestamp") else txn["created_at"]).strftime("%B %d, %Y at %I:%M %p")],
        ["Amount Paid", f"₦{txn['amount_paid']:,.2f}"],
        ["Payment Method", "Bank Transfer via Paystack"],
        ["Status", "PAID"],
    ]

    if txn.get("payer_name"):
        data.append(["Paid By", txn["payer_name"]])
    if txn.get("payer_email"):
        data.append(["Email", txn["payer_email"]])

    table = Table(data, colWidths=[3*inch, 3.5*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f0f0f0")),
        ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor("#1a1a1a")),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 12),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('BACKGROUND', (0,1), (-1,-1), colors.white),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('BOX', (0,0), (-1,-1), 1, colors.black),
    ]))
    story.append(table)
    story.append(Spacer(1, 40))

    # Thank you note
    thank_you = f"""
    <font size="14" color="#1a1a1a"><b>Thank you for your payment!</b></font><br/><br/>
    <font size="11">
    This is an official receipt from <b>{business_name}</b>.<br/>
    Your payment has been received successfully via Payla.
    </font>
    """
    story.append(Paragraph(thank_you, styles["Normal"]))
    story.append(Spacer(1, 60))

    # Footer
    footer = f"""
    <font size="10" color="grey">
    Powered by <b>Payla</b> • {paylink.get("link_url", "https://payla.vip")}<br/>
    Need help? Contact: {user.get("email", "support@payla.ng")}
    </font>
    """
    story.append(Paragraph(footer, ParagraphStyle('Footer', alignment=1)))

    # Build PDF
    doc.build(story)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="receipt_{reference[:8]}.pdf"',
            "Cache-Control": "no-cache"
        }
    )

# ADD THIS TO receipt_router.py → INVOICE RECEIPT
@router.get("/invoice/{invoice_id}.pdf")
async def generate_invoice_receipt(invoice_id: str, current_user: User = Depends(require_silver)):
    # Get invoice
    inv_doc = db.collection("invoices").document(invoice_id).get()
    if not inv_doc.exists:
        raise HTTPException(404, "Invoice not found")
    
    inv = inv_doc.to_dict()
    if inv.get("status") != "paid":
        raise HTTPException(400, "Invoice not paid")

    # Get sender (merchant)
    user_doc = db.collection("users").document(inv["sender_id"]).get()
    if not user_doc.exists:
        raise HTTPException(404, "Merchant not found")
    user = user_doc.to_dict()

    # Build PDF
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=1*inch, bottomMargin=1*inch)
    story = []
    styles = getSampleStyleSheet()

    # Logo
    logo_url = user.get("logo_url")
    if logo_url:
        logo_data = await fetch_logo(logo_url)
        if logo_data:
            try:
                img = Image(logo_data, width=2*inch, height=2*inch)
                img.hAlign = 'CENTER'
                story.append(img)
                story.append(Spacer(1, 20))
            except:
                pass

    # Business Name
    business_name = user.get("business_name") or user.get("full_name") or "Payla Merchant"
    story.append(Paragraph(business_name, title_style))
    story.append(Paragraph("Official Invoice Receipt", subtitle_style))
    story.append(Spacer(1, 40))

    # Invoice Details
    paid_at = inv.get("paid_at")
    if isinstance(paid_at, datetime):
        date_str = paid_at.strftime("%B %d, %Y at %I:%M %p")
    else:
        date_str = "Date not recorded"

    data = [
        [
        ["Invoice ID", invoice_id.upper()],
        ["Issue Date", inv.get("created_at", "N/A") if isinstance(inv.get("created_at"), str) else inv.get("created_at", "N/A")],
        ["Paid Date", date_str],
        ["Amount Paid", f"₦{inv['amount']:,.2f}"],
        ["Description", inv.get("description", "Service payment")],
        ["Payment Status", "PAID"],
    ]]

    if inv.get("client_phone"):
        data.append(["Paid By", inv["client_phone"]])
    if inv.get("client_email"):
        data.append(["Client Name", inv["client"]])

    table = Table(data, colWidths=[3*inch, 3.5*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#f0f0f0")),
        ('TEXTCOLOR', (0,0), (-1,-1), colors.HexColor("#1a1a1a")),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 12),
        ('BOTTOMPADDING', (0,0), (-1,0), 12),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('BOX', (0,0), (-1,-1), 1, colors.black),
    ]))
    story.append(table)
    story.append(Spacer(1, 40))

    # Thank you
    thank_you = f"""
    <font size="14" color="#1a1a1a"><b>Payment Received – Thank You!</b></font><br/><br/>
    <font size="11">
    This is your official receipt from <b>{business_name}</b>.<br/>
    We appreciate your prompt payment.
    </font>
    """
    story.append(Paragraph(thank_you, styles["Normal"]))
    story.append(Spacer(1, 60))

    # Footer
    footer = f"""
    <font size="10" color="grey">
    Powered by <b>Payla</b> • {Settings.FRONTEND_URL}<br/>
    Questions? Contact: {user.get("email", "support@payla.ng")}
    </font>
    """
    story.append(Paragraph(footer, ParagraphStyle('Footer', alignment=1)))

    doc.build(story)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="invoice-receipt-{invoice_id}.pdf"',
        }
    )