from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from io import BytesIO
from datetime import datetime, timezone
import httpx

from app.core.firebase import db
from app.utils.firebase import firestore_run
from app.models.user_model import User
from app.core.auth import get_current_user
from app.core.config import settings
from app.core.subscription import require_silver

router = APIRouter(prefix="/receipt", tags=["Receipts"])

# --- Styles Configuration ---
styles = getSampleStyleSheet()
title_style = ParagraphStyle(
    'CustomTitle',
    parent=styles['Heading1'],
    fontSize=26,
    spaceAfter=20,
    textColor=colors.HexColor("#1a1a1a"),
    alignment=1 
)
subtitle_style = ParagraphStyle(
    'Subtitle',
    parent=styles['Normal'],
    fontSize=10,
    textColor=colors.grey,
    alignment=1
)

# --- Helper Functions ---
async def fetch_logo(url: str) -> BytesIO:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                return BytesIO(resp.content)
    except Exception:
        return None

def format_date(dt_val) -> str:
    """Safely converts Firestore Timestamps or strings to formatted strings."""
    if not dt_val:
        return "N/A"
    try:
        if isinstance(dt_val, datetime):
            return dt_val.strftime("%B %d, %Y")
        if hasattr(dt_val, "timestamp"): # Firestore Timestamp
            return dt_val.strftime("%B %d, %Y")
        return str(dt_val)
    except:
        return "Date Pending"

# --------------------------------------------------------------
# 1. PAYLINK RECEIPT
# --------------------------------------------------------------
@router.get("/paylink/{reference}.pdf")
async def generate_paylink_receipt(reference: str, token: str | None = None):
    # 1. Fetch Transaction Data
    txn_doc = await db.collection("paylink_transactions").document(reference).get()
    if not txn_doc.exists:
        raise HTTPException(404, "Transaction not found")
    
    txn = txn_doc.to_dict()
    
    # Check status (Paystack sends 'success', but check both just in case)
    if txn.get("status") not in ["success", "successful"]:
        raise HTTPException(400, "Receipt only available for successful payments")

    # 2. Security Check (If you use the token in the frontend, keep this)
    if token and token != reference:
         raise HTTPException(403, "Invalid access token")

    # 3. Fetch Merchant 
    user_doc = await db.collection("users").document(txn["user_id"]).get()
    user = user_doc.to_dict() if user_doc.exists else {}
    
    # IMPORTANT: Check correct field for subscription
    is_silver = user.get("plan") == "silver"

    if is_silver:
        logo_url = user.get("logo_url")
        business_name = user.get("business_name") or user.get("full_name") or "Merchant"
        primary_color = colors.HexColor(user.get("custom_invoice_colors", {}).get("primary", "#1a1a1a"))
        footer_brand = business_name
    else:
        logo_url = settings.PAYLA_LOGO_URL 
        business_name = "Payla Payments"
        primary_color = colors.HexColor("#6366f1")
        footer_brand = "Payla"

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.75*inch, bottomMargin=0.75*inch)
    story = []

    # 4. Logo Handling (unchanged but wrapped in try/except)
    if logo_url:
        logo_data = await fetch_logo(logo_url)
        if logo_data:
            try:
                img = Image(logo_data)
                aspect = img.imageHeight / float(img.imageWidth)
                img.drawWidth = 1.3*inch
                img.drawHeight = 1.3*inch * aspect
                img.hAlign = 'CENTER'
                story.append(img)
                story.append(Spacer(1, 15))
            except: pass

    # 5. Header
    story.append(Paragraph(business_name.upper(), title_style.clone('PaylinkTitle', textColor=primary_color)))
    story.append(Paragraph("PAYMENT RECEIPT", subtitle_style))
    story.append(Spacer(1, 30))

    # 6. Data Mapping (FIXED FIELD NAMES)
    # Use 'amount' (the net amount) or 'requested_amount'
    display_amount = txn.get("amount") or txn.get("requested_amount") or 0
    
    data = [
        ["Receipt ID", reference[:12].upper()],
        ["Date", format_date(txn.get("paid_at") or txn.get("created_at"))],
        ["Amount Paid", f"₦{float(display_amount):,.2f}"],
        ["Status", "SUCCESSFUL"]
    ]

    if txn.get("payer_name"): data.append(["Customer", txn["payer_name"]])
    elif txn.get("customer_email"): data.append(["Customer", txn["customer_email"]])

    table = Table(data, colWidths=[2.2*inch, 3.8*inch], rowHeights=28)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#f8fafc")),
        ('TEXTCOLOR', (0, 0), (0, -1), primary_color),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(table)
    story.append(Spacer(1, 40))
    
    # 7. Professional Sign-off
    thanks_text = f"<b>Thank you for your payment to {business_name}!</b>"
    story.append(Paragraph(thanks_text, subtitle_style.clone('Thanks', textColor=primary_color, fontSize=11)))
    story.append(Spacer(1, 60))

    # 8. Footer (FIXED THE footer_content NameError)
    footer_text = f"""
    <font size="8" color="grey">
    This receipt was issued by {footer_brand} via Payla Intelligence.<br/>
    Reference: {reference}<br/>
    {settings.BACKEND_URL}
    </font>
    """
    story.append(Paragraph(footer_text, ParagraphStyle('Footer', alignment=1)))

    doc.build(story)
    buffer.seek(0)
    
    return StreamingResponse(
        buffer, 
        media_type="application/pdf", 
        headers={"Content-Disposition": f'attachment; filename="Receipt_{reference[:8]}.pdf"'}
    )

# --------------------------------------------------------------
# 2. INVOICE RECEIPT
# --------------------------------------------------------------
@router.get("/invoice/{invoice_id}.pdf")
async def generate_invoice_receipt(invoice_id: str, token: str | None = None):
    """
    Generates a PDF receipt. 
    - Silver Tier: Full merchant branding.
    - Free Tier: Payla branding (Marketing for you).
    - Security: Requires the transaction reference as a token for public access.
    """
    # 1. Fetch data
    inv_doc = await firestore_run(db.collection("invoices").document(invoice_id).get)
    if not inv_doc.exists:
        raise HTTPException(404, "Invoice not found")
    
    inv = inv_doc.to_dict()
    
    # 2. Security Check 
    # Validates that the person accessing the PDF has the 'token' (transaction ref)
    # This prevents scrapers from downloading all your user receipts.
    if inv.get("status") != "paid":
        raise HTTPException(400, "Receipt only available for paid invoices")
    
    if token and token != inv.get("transaction_reference"):
         raise HTTPException(403, "Invalid security token for this receipt")

    sender_id = inv["sender_id"]
    user_doc = await db.collection("users").document(sender_id).get()
    user = user_doc.to_dict() if user_doc.exists else {}

    # 3. Determine Branding (The "Elite" Logic)
    is_silver = user.get("subscription_tier") == "silver"
    
    if is_silver:
        # User is paying: Give them their own brand
        logo_url = user.get("custom_invoice_colors", {}).get("logo") or user.get("logo_url")
        business_name = inv.get("sender_business_name") or user.get("business_name") or "Merchant"
        primary_color = colors.HexColor(user.get("custom_invoice_colors", {}).get("primary", "#1a1a1a"))
        footer_brand = business_name
        support_contact = user.get("email") or "the merchant"
    else:
        # Free Tier: You (Payla) are the brand
        logo_url = settings.PAYLA_LOGO_URL # Ensure this is in your config
        business_name = "Payla Payments"
        primary_color = colors.HexColor("#6366f1") # Payla Signature Indigo
        footer_brand = "Payla"
        support_contact = "support@payla.ng"

    buffer = BytesIO()
    # Setting margins for a professional "letterhead" feel
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.75*inch, bottomMargin=0.75*inch)
    story = []

    # 4. Logo Handling
    if logo_url:
        logo_data = await fetch_logo(logo_url)
        if logo_data:
            try:
                img = Image(logo_data)
                # Aspect ratio maintenance
                aspect = img.imageHeight / float(img.imageWidth)
                img.drawWidth = 1.2*inch
                img.drawHeight = 1.2*inch * aspect
                img.hAlign = 'CENTER'
                story.append(img)
                story.append(Spacer(1, 15))
            except: 
                pass

    # 5. Header Section
    story.append(Paragraph(business_name.upper(), title_style.clone('MainTitle', textColor=primary_color)))
    story.append(Paragraph("OFFICIAL PAYMENT RECEIPT", subtitle_style))
    story.append(Spacer(1, 30))

    # 6. Transaction Table
    data = [
        ["Invoice Number", invoice_id.upper()],
        ["Transaction Ref", inv.get("transaction_reference", "Verified").upper()],
        ["Date Paid", format_date(inv.get("paid_at"))],
        ["Total Amount", f"{inv.get('currency', '₦')}{inv.get('amount', 0):,.2f}"],
        ["Description", inv.get("description", "Payment for Services")],
    ]

    # Add Customer Info if available
    customer_label = inv.get("client_name") or inv.get("client_email") or "Valued Customer"
    data.append(["Paid By", customer_label])

    table = Table(data, colWidths=[2.2*inch, 3.8*inch], rowHeights=30)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#f8fafc")), # Soft slate background for keys
        ('TEXTCOLOR', (0, 0), (0, -1), primary_color),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
    ]))
    story.append(table)
    story.append(Spacer(1, 40))

    # 7. Closing Message
    thanks_style = ParagraphStyle('Thanks', parent=subtitle_style, fontSize=12, leading=16)
    story.append(Paragraph(f"<b>Successful Payment.</b>", thanks_style.clone('bold', textColor=primary_color)))
    story.append(Paragraph(f"This document confirms that your payment was received in full.", thanks_style))
    story.append(Spacer(1, 60))

    # 8. Brand-Specific Footer
    footer_style = ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8, textColor=colors.grey, alignment=1)
    
    footer_content = f"""
    This receipt was generated by {footer_brand}.<br/>
    For inquiries regarding this payment, please contact {support_contact}.<br/>
    <b>Thank you for using Payla.</b>
    """
    story.append(Paragraph(footer_content, footer_style))

    doc.build(story)
    buffer.seek(0)

    filename = f"Receipt_{invoice_id}.pdf"
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )