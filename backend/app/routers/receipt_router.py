from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html import escape
from io import BytesIO
from typing import Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
    KeepTogether,
)

try:
    from PIL import Image as PILImage, ImageDraw, ImageFont
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

from app.core.config import settings
from app.core.firebase import db
from app.core.subscription import require_silver
from app.models.user_model import User
from app.utils.firebase import firestore_run


import logging

logger = logging.getLogger("payla.receipt")


router = APIRouter(prefix="/receipt", tags=["Receipts"])


# ============================================================
# FONT REGISTRATION
# ============================================================
# ReportLab's built-in fonts (Times, Helvetica) don't include the
# naira glyph (U+20A6), so any ₦ renders as a lowercase "n".
#
# We try to register a few serif TTFs that ship on common Linux
# servers. If none are found, the helpers fall back to the built-in
# names and any ₦ in a receipt will degrade to "N" — the caller
# should keep that in mind if they deploy on a system with no
# TrueType serif available.
# ============================================================

_PAYLA_DISPLAY_FONT = "Times-Bold"
_PAYLA_DISPLAY_FONT_ITALIC = "Times-Italic"
_PAYLA_BODY_FONT = "Helvetica"


def _register_first_available(name: str, candidates) -> Optional[str]:
    """Register the first available TTF from the candidate list."""
    for path in candidates:
        try:
            pdfmetrics.registerFont(TTFont(name, path))
            return name
        except Exception:
            continue
    return None


_display = _register_first_available(
    "PaylaSerif-Bold",
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerifCondensed-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
    ),
)

if _display:
    _PAYLA_DISPLAY_FONT = _display


_display_italic = _register_first_available(
    "PaylaSerif-Italic",
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
        "/System/Library/Fonts/Supplemental/Georgia Italic.ttf",
    ),
)

if _display_italic:
    _PAYLA_DISPLAY_FONT_ITALIC = _display_italic


_body = _register_first_available(
    "PaylaSans",
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ),
)

if _body:
    _PAYLA_BODY_FONT = _body


# ============================================================
# PAYLA RECEIPT PALETTE
# ============================================================

OBSIDIAN           = colors.HexColor("#0A0A0A")
OBSIDIAN_SOFT      = colors.HexColor("#141414")
ROSE_GOLD          = colors.HexColor("#E8B4B8")
ROSE_GOLD_DEEP     = colors.HexColor("#D89FA4")
ROSE_HAIRLINE      = colors.HexColor("#E7C7CB")
ROSE_WASH          = colors.HexColor("#FBF3F4")
ROSE_TINT          = colors.HexColor("#FDF7F8")

TEXT_PRIMARY       = colors.HexColor("#1A1A1A")
TEXT_SECONDARY     = colors.HexColor("#5A5A5A")
TEXT_TERTIARY      = colors.HexColor("#8A8A8A")

VERIFIED_GREEN     = colors.HexColor("#2F8F5B")
VERIFIED_GREEN_BG  = colors.HexColor("#EBF6EF")
VERIFIED_GREEN_BD  = colors.HexColor("#C8E6D3")

TABLE_BORDER       = colors.HexColor("#ECE4E5")
TABLE_LABEL_BG     = colors.HexColor("#FAF6F7")


# ============================================================
# STYLES
# ============================================================

styles = getSampleStyleSheet()


brand_title_style = ParagraphStyle(
    "PaylaBrandTitle",
    parent=styles["Heading1"],
    fontName=_PAYLA_DISPLAY_FONT,
    fontSize=22,
    leading=26,
    spaceAfter=2,
    textColor=TEXT_PRIMARY,
    alignment=1,
)

receipt_label_style = ParagraphStyle(
    "PaylaReceiptLabel",
    parent=styles["Normal"],
    fontName=_PAYLA_BODY_FONT,
    fontSize=9,
    leading=12,
    textColor=TEXT_TERTIARY,
    alignment=1,
    spaceBefore=6,
    spaceAfter=14,
)

hero_amount_style = ParagraphStyle(
    "PaylaHeroAmount",
    parent=styles["Normal"],
    fontName=_PAYLA_DISPLAY_FONT,
    fontSize=28,
    leading=32,
    textColor=ROSE_GOLD_DEEP,
    alignment=1,
)

hero_amount_currency_style = ParagraphStyle(
    "PaylaHeroCurrency",
    parent=styles["Normal"],
    fontName=_PAYLA_BODY_FONT,
    fontSize=10,
    leading=14,
    textColor=TEXT_TERTIARY,
    alignment=1,
    spaceBefore=2,
)

hero_amount_label_style = ParagraphStyle(
    "PaylaHeroAmountLabel",
    parent=styles["Normal"],
    fontName=_PAYLA_BODY_FONT,
    fontSize=8,
    leading=12,
    textColor=TEXT_TERTIARY,
    alignment=1,
    spaceAfter=4,
)

footer_style = ParagraphStyle(
    "ReceiptFooter",
    parent=styles["Normal"],
    fontName=_PAYLA_BODY_FONT,
    fontSize=8,
    leading=12,
    textColor=TEXT_TERTIARY,
    alignment=1,
    wordWrap="CJK",
)

footer_secured_style = ParagraphStyle(
    "ReceiptFooterSecured",
    parent=styles["Normal"],
    fontName=_PAYLA_BODY_FONT,
    fontSize=7,
    leading=11,
    textColor=TEXT_TERTIARY,
    alignment=1,
    spaceBefore=6,
)

cell_style = ParagraphStyle(
    "ReceiptCell",
    parent=styles["Normal"],
    fontName=_PAYLA_BODY_FONT,
    fontSize=9.5,
    leading=13,
    textColor=TEXT_PRIMARY,
    wordWrap="CJK",
)

label_style = ParagraphStyle(
    "ReceiptLabel",
    parent=cell_style,
    fontName=_PAYLA_BODY_FONT,
    textColor=TEXT_SECONDARY,
)

status_chip_text_style = ParagraphStyle(
    "ReceiptStatusChipText",
    parent=styles["Normal"],
    fontName=_PAYLA_BODY_FONT,
    fontSize=8.5,
    leading=11,
    textColor=VERIFIED_GREEN,
    alignment=1,
)

status_style = ParagraphStyle(
    "ReceiptStatus",
    parent=cell_style,
    fontName=_PAYLA_BODY_FONT,
    textColor=VERIFIED_GREEN,
)


# ============================================================
# HELPERS
# ============================================================

def _invoice_document_id(invoice_id: str) -> str:
    """Accept both inv_... IDs and public short invoice IDs."""
    if invoice_id.startswith("inv_"):
        return invoice_id
    return f"inv_{invoice_id}"


def _payment_reference(invoice: dict) -> Optional[str]:
    return (
        invoice.get("transaction_reference")
        or invoice.get("paystack_reference")
    )


def _safe_text(value, default: str = "N/A") -> str:
    """Escape text before inserting it into a ReportLab Paragraph."""
    if value is None or value == "":
        value = default

    return escape(str(value))


def _initials_from(name: Optional[str]) -> str:
    """Return up to two uppercase initials for a name."""
    if not name:
        return "P"

    words = [word for word in str(name).split() if word]

    if not words:
        return "P"

    initials = "".join(word[0].upper() for word in words[:2])

    return initials or "P"


def _format_amount(value, currency: str = "NGN") -> str:
    try:
        amount = Decimal(str(value))

        if not amount.is_finite():
            raise ValueError("Invalid amount")

        formatted = f"{amount:,.2f}"

    except (InvalidOperation, TypeError, ValueError):
        formatted = "0.00"

    currency = str(currency or "NGN").upper()

    symbols = {
        "NGN": "₦",
        "USD": "$",
        "GBP": "£",
        "EUR": "€",
    }

    symbol = symbols.get(currency)

    if symbol:
        return f"{symbol}{formatted}"

    return f"{currency} {formatted}"


def _split_amount(value, currency: str = "NGN"):
    """Return (symbol, number-string) for the hero amount band."""
    try:
        amount = Decimal(str(value))

        if not amount.is_finite():
            raise ValueError("Invalid amount")

        number = f"{amount:,.2f}"

    except (InvalidOperation, TypeError, ValueError):
        number = "0.00"

    currency = str(currency or "NGN").upper()
    symbols = {"NGN": "₦", "USD": "$", "GBP": "£", "EUR": "€"}
    symbol = symbols.get(currency, currency + " ")
    return symbol, number


def format_date(dt_val) -> str:
    """Format Firestore timestamps, datetimes, and ISO strings."""
    if not dt_val:
        return "N/A"

    try:
        if isinstance(dt_val, datetime):
            dt = dt_val

        elif hasattr(dt_val, "to_datetime"):
            dt = dt.to_datetime()

        elif isinstance(dt_val, dict):
            seconds = dt_val.get("seconds")

            if seconds is None:
                return "N/A"

            dt = datetime.fromtimestamp(
                float(seconds),
                tz=timezone.utc,
            )

        elif isinstance(dt_val, (int, float)):
            dt = datetime.fromtimestamp(
                dt_val,
                tz=timezone.utc,
            )

        elif isinstance(dt_val, str):
            normalized = dt_val.strip()

            if normalized.endswith("Z"):
                normalized = normalized[:-1] + "+00:00"

            dt = datetime.fromisoformat(normalized)

        else:
            return "N/A"

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.strftime("%B %d, %Y at %I:%M %p UTC")

    except (ValueError, TypeError, OverflowError, OSError):
        return "N/A"


def _hex_color(value, default: str = "#1A1A1A"):
    """Use configured colors only when they are valid hex colors."""
    if not isinstance(value, str):
        value = default

    value = value.strip()

    if len(value) not in (4, 7) or not value.startswith("#"):
        value = default

    try:
        return colors.HexColor(value)
    except (ValueError, TypeError):
        return colors.HexColor(default)


async def fetch_logo(url: str) -> Optional[BytesIO]:
    """
    Fetch a remote logo with a short timeout.
    Only HTTP(S) URLs are accepted.
    """
    try:
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return None

        async with httpx.AsyncClient(
            timeout=5,
            follow_redirects=False,
        ) as client:
            response = await client.get(url)

        if response.status_code != 200:
            return None

        content_type = response.headers.get("content-type", "").lower()

        if not content_type.startswith("image/"):
            return None

        if len(response.content) > 3 * 1024 * 1024:
            return None

        return BytesIO(response.content)

    except Exception:
        logger.exception("Logo fetch failed")
        return None


def _build_medallion_png(
    initials: str,
    size: int = 200,
) -> Optional[BytesIO]:
    """
    Render the initials medallion as a PNG for use in ReportLab.

    Returns a BytesIO positioned at 0, or None if Pillow or a usable
    font are unavailable.
    """
    if not PILLOW_AVAILABLE:
        logger.warning("Pillow unavailable — cannot build medallion")
        return None

    try:
        img = PILImage.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        margin = 1
        draw.ellipse(
            [margin, margin, size - margin, size - margin],
            fill=(10, 10, 10, 255),
        )

        ring_width = 2
        draw.ellipse(
            [margin, margin, size - margin, size - margin],
            outline=(232, 180, 184, 90),
            width=ring_width,
        )

        font = None

        for font_path in (
            "app/assets/fonts/PlayfairDisplay-Bold.ttf",
            "app/assets/fonts/PlayfairDisplay-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
            "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
        ):
            try:
                font = ImageFont.truetype(font_path, int(size * 0.38))
                break
            except (OSError, IOError):
                continue

        if font is None:
            font = ImageFont.load_default()

        bbox = draw.textbbox((0, 0), initials, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        text_x = (size - text_width) / 2 - bbox[0]
        text_y = (size - text_height) / 2 - bbox[1]

        draw.text(
            (text_x, text_y),
            initials,
            fill=(232, 180, 184, 255),
            font=font,
        )

        buffer = BytesIO()
        img.save(buffer, format="PNG", optimize=True)
        buffer.seek(0)
        return buffer

    except Exception:
        logger.exception("Medallion generation failed")
        return None


async def _append_logo(
    story,
    logo_url,
    fallback_initials: Optional[str] = None,
    width=1.1 * inch,
):
    """
    Append the merchant's logo to the story. If no logo URL is
    available or the fetch fails, draw the initials medallion.
    """
    logo_data = None

    if isinstance(logo_url, str) and logo_url:
        logo_data = await fetch_logo(logo_url)

        if logo_data:
            logger.info("Logo rendered from URL: %s", logo_url[:60])
        else:
            logger.warning("Logo fetch returned no data for: %s", logo_url[:60])
    else:
        logger.info("No logo URL — using fallback initials.")

    if not logo_data and fallback_initials:
        logo_data = _build_medallion_png(fallback_initials)

        if logo_data:
            logger.info("Medallion rendered for initials: %s", fallback_initials)
        else:
            logger.warning("Medallion generation returned no data.")

    if not logo_data:
        logger.info("Nothing to render for the receipt header logo.")
        return

    try:
        image = Image(logo_data)

        if not image.imageWidth or not image.imageHeight:
            logger.warning("Logo image has zero dimensions.")
            return

        aspect = image.imageHeight / float(image.imageWidth)

        image.drawWidth = width
        image.drawHeight = width * aspect
        image.hAlign = "CENTER"

        story.append(image)
        story.append(Spacer(1, 16))

    except Exception:
        logger.exception("Could not append logo image to the story.")
        return


def _rose_rule(width="60%", thickness=0.75, space_after=18):
    return HRFlowable(
        width=width,
        thickness=thickness,
        color=ROSE_HAIRLINE,
        spaceBefore=0,
        spaceAfter=space_after,
        hAlign="CENTER",
    )


def _double_rose_rule(space_after=16):
    return [
        HRFlowable(
            width="34%",
            thickness=0.9,
            color=ROSE_GOLD,
            spaceBefore=0,
            spaceAfter=3,
            hAlign="CENTER",
        ),
        HRFlowable(
            width="22%",
            thickness=0.4,
            color=ROSE_HAIRLINE,
            spaceBefore=0,
            spaceAfter=space_after,
            hAlign="CENTER",
        ),
    ]


def _build_hero_amount_band(amount_value, currency="NGN"):
    symbol, number = _split_amount(amount_value, currency)

    amount_row = [
        Paragraph(
            f"{_safe_text(symbol)}{_safe_text(number)}",
            hero_amount_style,
        )
    ]

    currency_row = [
        Paragraph(
            _safe_text(currency.upper()),
            hero_amount_currency_style,
        )
    ]

    label_row = [
        Paragraph("AMOUNT PAID", hero_amount_label_style)
    ]

    table = Table(
        [label_row, amount_row, currency_row],
        colWidths=[6.0 * inch],
        hAlign="CENTER",
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ROSE_TINT),
        ("BOX", (0, 0), (-1, -1), 0.6, ROSE_HAIRLINE),
        ("LINEBELOW", (0, 0), (0, 0), 0.35, ROSE_HAIRLINE),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, 0), 12),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 14),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))

    return table


def _build_status_chip():
    chip = Table(
        [[Paragraph("SUCCESSFUL", status_chip_text_style)]],
        colWidths=[1.1 * inch],
        rowHeights=[0.26 * inch],
        hAlign="LEFT",
    )

    chip.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), VERIFIED_GREEN_BG),
        ("BOX", (0, 0), (-1, -1), 0.4, VERIFIED_GREEN_BD),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    return chip


def _build_receipt_table(data, primary_color, row_height=None):
    table_data = []

    for label, value in data:
        if isinstance(value, tuple) and len(value) == 2 and value[1] is status_style:
            table_data.append([
                Paragraph(_safe_text(label), label_style),
                _build_status_chip(),
            ])
            continue

        if isinstance(value, tuple) and len(value) == 2:
            value_text, value_style = value
        else:
            value_text, value_style = value, cell_style

        table_data.append([
            Paragraph(_safe_text(label), label_style),
            Paragraph(_safe_text(value_text), value_style),
        ])

    table = Table(
        table_data,
        colWidths=[2.0 * inch, 4.0 * inch],
        hAlign="CENTER",
    )

    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), TABLE_LABEL_BG),
        ("TEXTCOLOR", (0, 0), (0, -1), primary_color),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBEFORE", (0, 0), (0, -1), 1.4, ROSE_GOLD),
        ("LINEBELOW", (0, 0), (-1, -2), 0.35, TABLE_BORDER),
        ("BOX", (0, 0), (-1, -1), 0.5, TABLE_BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))

    return table


def _build_footer_block(receipt_footer_lines, secured_label: Optional[str] = None):
    parts = []

    parts.append(_rose_rule(width="40%", thickness=0.5, space_after=14))

    for line in receipt_footer_lines:
        parts.append(Paragraph(line, footer_style))

    if secured_label:
        parts.append(
            Paragraph(
                f'<font color="#E8B4B8">\u25CF</font>&nbsp;&nbsp;'
                f'{_safe_text(secured_label)}',
                footer_secured_style,
            )
        )

    return KeepTogether(parts)


def _pdf_response(buffer: BytesIO, filename: str):
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _get_authenticated_user_id(current_user) -> Optional[str]:
    if isinstance(current_user, dict):
        value = (
            current_user.get("uid")
            or current_user.get("id")
            or current_user.get("user_id")
        )
    else:
        value = (
            getattr(current_user, "uid", None)
            or getattr(current_user, "id", None)
            or getattr(current_user, "user_id", None)
        )

    return str(value) if value else None


def _merchant_branding(user: dict):
    custom_colors = user.get("custom_invoice_colors") or {}

    business_name = (
        user.get("business_name")
        or user.get("full_name")
        or "Merchant"
    )

    logo_url = (
        custom_colors.get("logo")
        or user.get("logo_url")
    )

    primary_color = _hex_color(
        custom_colors.get("primary"),
        "#1A1A1A",
    )

    return business_name, logo_url, primary_color


def _build_document(buffer: BytesIO):
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=0.85 * inch,
        bottomMargin=0.85 * inch,
        leftMargin=0.9 * inch,
        rightMargin=0.9 * inch,
        title="Payla Receipt",
        author="Payla",
        subject="Payment receipt",
        creator="Payla",
    )
    return doc


async def _merchant_has_silver(user_id: str) -> bool:
    if not user_id:
        return False

    try:
        snapshot = await firestore_run(
            db.collection("users").document(user_id).get
        )
    except Exception:
        return False

    if not snapshot.exists:
        return False

    try:
        merchant = User(**(snapshot.to_dict() or {}))
        return merchant.can_access_silver_features()
    except Exception:
        return False


# ============================================================
# 1. PAYLINK RECEIPT
# ============================================================

@router.get("/paylink/{reference}.pdf")
async def generate_paylink_receipt(
    reference: str,
    token: Optional[str] = None,
):
    txn_doc = await firestore_run(
        db.collection("paylink_transactions")
        .document(reference)
        .get
    )

    if not txn_doc.exists:
        raise HTTPException(
            status_code=404,
            detail="Transaction not found",
        )

    txn = txn_doc.to_dict() or {}

    if txn.get("status") not in ("success", "successful"):
        raise HTTPException(
            status_code=400,
            detail="Receipt only available for successful payments",
        )

    if token and token != reference:
        raise HTTPException(
            status_code=403,
            detail="Invalid access token",
        )

    user_id = txn.get("user_id")

    if not user_id:
        raise HTTPException(
            status_code=400,
            detail="Merchant information is missing",
        )

    if not await _merchant_has_silver(user_id):
        raise HTTPException(
            status_code=403,
            detail="Receipts are available on Payla Silver merchant accounts.",
        )

    user_doc = await firestore_run(
        db.collection("users").document(user_id).get
    )

    user = user_doc.to_dict() if user_doc.exists else {}

    logo_url = user.get("logo_url")

    business_name = (
        user.get("business_name")
        or user.get("full_name")
        or "Merchant"
    )

    custom_colors = user.get("custom_invoice_colors") or {}

    primary_color = _hex_color(
        custom_colors.get("primary"),
        "#1A1A1A",
    )

    footer_brand = business_name

    buffer = BytesIO()
    doc = _build_document(buffer)
    story = []

    await _append_logo(
        story,
        logo_url,
        fallback_initials=_initials_from(business_name),
        width=1.1 * inch,
    )

    story.append(
        Paragraph(
            _safe_text(business_name),
            brand_title_style,
        )
    )

    for rule in _double_rose_rule(space_after=14):
        story.append(rule)

    story.append(
        Paragraph("PAYMENT RECEIPT", receipt_label_style)
    )

    # The paylink transaction document stores the amount under
    # `amount_paid` (see paylink_router.create_paylink_transaction).
    # Older/legacy records may only have `amount` or
    # `requested_amount`, so we check all three in order.
    display_amount = (
        txn.get("amount_paid")
        or txn.get("amount")
        or txn.get("requested_amount")
        or 0
    )

    story.append(
        _build_hero_amount_band(display_amount, "NGN")
    )

    story.append(Spacer(1, 26))

    data = [
        ["Receipt ID", reference[:12].upper()],
        [
            "Date",
            format_date(txn.get("paid_at") or txn.get("created_at")),
        ],
        ["Status", ("SUCCESSFUL", status_style)],
    ]

    customer = txn.get("payer_name") or txn.get("customer_email")

    if customer:
        data.append(["Customer", str(customer)])

    story.append(_build_receipt_table(data, primary_color))

    story.append(Spacer(1, 32))

    thanks_style = ParagraphStyle(
        "PaylinkThanks",
        parent=styles["Normal"],
        fontName=_PAYLA_DISPLAY_FONT_ITALIC,
        fontSize=12,
        leading=16,
        textColor=ROSE_GOLD_DEEP,
        alignment=1,
    )

    story.append(
        Paragraph(
            f"Thank you for your payment to "
            f"{_safe_text(business_name)}.",
            thanks_style,
        )
    )

    story.append(Spacer(1, 36))

    story.append(
        _build_footer_block(
            [
                f"Receipt issued by {_safe_text(footer_brand)} via Payla.",
                f"Reference: {_safe_text(reference)}",
                _safe_text(settings.BACKEND_URL),
            ],
            secured_label="Secured by Payla",
        )
    )

    doc.build(story)

    return _pdf_response(
        buffer,
        f"Receipt_{reference[:8]}.pdf",
    )


# ============================================================
# 2. INVOICE RECEIPT
# ============================================================

@router.get("/invoice/{invoice_id}.pdf")
async def generate_invoice_receipt(
    invoice_id: str,
    token: Optional[str] = None,
):
    canonical_id = _invoice_document_id(invoice_id)

    invoice_ref = db.collection("invoices").document(canonical_id)
    inv_doc = await firestore_run(invoice_ref.get)

    if not inv_doc.exists:
        raise HTTPException(
            status_code=404,
            detail="Invoice not found",
        )

    inv = inv_doc.to_dict() or {}

    if inv.get("status") != "paid":
        raise HTTPException(
            status_code=400,
            detail="Receipt only available for paid invoices",
        )

    payment_reference = _payment_reference(inv)

    if (
        not token
        or not payment_reference
        or token != payment_reference
    ):
        raise HTTPException(
            status_code=403,
            detail="A valid payment reference is required",
        )

    sender_id = inv.get("sender_id")

    if not sender_id:
        raise HTTPException(
            status_code=400,
            detail="Invoice merchant information is missing",
        )

    if not await _merchant_has_silver(sender_id):
        raise HTTPException(
            status_code=403,
            detail="Receipts are available on Payla Silver merchant accounts.",
        )

    user_doc = await firestore_run(
        db.collection("users").document(sender_id).get
    )

    user = user_doc.to_dict() if user_doc.exists else {}

    custom_colors = user.get("custom_invoice_colors") or {}

    logo_url = (
        custom_colors.get("logo")
        or user.get("logo_url")
        or inv.get("sender_logo")
    )

    business_name = (
        inv.get("sender_business_name")
        or user.get("business_name")
        or user.get("full_name")
        or "Merchant"
    )

    primary_color = _hex_color(
        custom_colors.get("primary"),
        "#1A1A1A",
    )

    footer_brand = business_name

    support_contact = (
        user.get("email")
        or inv.get("sender_email")
        or "the merchant"
    )

    buffer = BytesIO()
    doc = _build_document(buffer)
    story = []

    await _append_logo(
        story,
        logo_url,
        fallback_initials=_initials_from(business_name),
        width=1.1 * inch,
    )

    story.append(
        Paragraph(
            _safe_text(business_name),
            brand_title_style,
        )
    )

    for rule in _double_rose_rule(space_after=14):
        story.append(rule)

    story.append(
        Paragraph("OFFICIAL PAYMENT RECEIPT", receipt_label_style)
    )

    amount = inv.get("amount", 0)
    currency = inv.get("currency") or "NGN"

    story.append(
        _build_hero_amount_band(amount, currency)
    )

    story.append(Spacer(1, 26))

    data = [
        ["Invoice Number", canonical_id.upper()],
        ["Transaction Ref", payment_reference],
        ["Date Paid", format_date(inv.get("paid_at"))],
        [
            "Description",
            inv.get("description") or "Payment for Services",
        ],
        [
            "Paid By",
            inv.get("client_name")
            or inv.get("client_email")
            or "Valued Customer",
        ],
        ["Status", ("SUCCESSFUL", status_style)],
    ]

    story.append(_build_receipt_table(data, primary_color))

    story.append(Spacer(1, 32))

    thanks_style = ParagraphStyle(
        "InvoiceReceiptThanks",
        parent=styles["Normal"],
        fontName=_PAYLA_DISPLAY_FONT_ITALIC,
        fontSize=12,
        leading=16,
        textColor=ROSE_GOLD_DEEP,
        alignment=1,
    )

    story.append(
        Paragraph(
            "This document confirms that the invoice payment "
            "was recorded as paid by Payla.",
            thanks_style,
        )
    )

    story.append(Spacer(1, 36))

    story.append(
        _build_footer_block(
            [
                f"Receipt generated by {_safe_text(footer_brand)}.",
                f"For payment enquiries, contact {_safe_text(support_contact)}.",
                "Thank you for using Payla.",
            ],
            secured_label="Secured by Payla",
        )
    )

    doc.build(story)

    safe_filename_id = "".join(
        char for char in canonical_id
        if char.isalnum() or char in ("-", "_")
    )

    return _pdf_response(
        buffer,
        f"Receipt_{safe_filename_id}.pdf",
    )


# ============================================================
# 3. MERCHANT TRANSACTION RECEIPT
# ============================================================

@router.get("/transaction/{reference}.pdf")
async def generate_transaction_receipt(
    reference: str,
    current_user=Depends(require_silver),
):
    user_id = _get_authenticated_user_id(current_user)

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Unable to identify the authenticated merchant",
        )

    payment_doc = await firestore_run(
        db.collection("payments").document(reference).get
    )

    if not payment_doc.exists:
        raise HTTPException(
            status_code=404,
            detail="Payment not found",
        )

    payment = payment_doc.to_dict() or {}

    if str(payment.get("user_id") or "") != user_id:
        raise HTTPException(
            status_code=404,
            detail="Payment not found",
        )

    if str(payment.get("status") or "").lower() not in (
        "success",
        "successful",
    ):
        raise HTTPException(
            status_code=400,
            detail="Receipt only available for successful payments",
        )

    user_doc = await firestore_run(
        db.collection("users").document(user_id).get
    )

    user = user_doc.to_dict() if user_doc.exists else {}

    business_name, logo_url, primary_color = _merchant_branding(user)

    buffer = BytesIO()
    doc = _build_document(buffer)
    story = []

    await _append_logo(
        story,
        logo_url,
        fallback_initials=_initials_from(business_name),
        width=1.1 * inch,
    )

    story.append(
        Paragraph(
            _safe_text(business_name),
            brand_title_style,
        )
    )

    for rule in _double_rose_rule(space_after=14):
        story.append(rule)

    story.append(
        Paragraph("PAYMENT RECEIPT", receipt_label_style)
    )

    amount = payment.get("amount", 0)
    currency = payment.get("currency") or "NGN"

    story.append(
        _build_hero_amount_band(amount, currency)
    )

    story.append(Spacer(1, 26))

    payment_reference = (
        payment.get("paystack_reference")
        or reference
    )

    paid_at = (
        payment.get("paid_at")
        or payment.get("created_at")
    )

    data = [
        ["Receipt ID", reference],
        ["Transaction Reference", payment_reference],
        ["Date Paid", format_date(paid_at)],
        ["Status", ("SUCCESSFUL", status_style)],
    ]

    invoice_id = payment.get("invoice_id")
    if invoice_id:
        data.append(["Invoice", str(invoice_id)])

    paylink_id = payment.get("paylink_id")
    if paylink_id:
        data.append(["Paylink", str(paylink_id)])

    story.append(_build_receipt_table(data, primary_color))

    story.append(Spacer(1, 32))

    thanks_style = ParagraphStyle(
        "TransactionReceiptThanks",
        parent=styles["Normal"],
        fontName=_PAYLA_DISPLAY_FONT_ITALIC,
        fontSize=12,
        leading=16,
        textColor=ROSE_GOLD_DEEP,
        alignment=1,
    )

    story.append(
        Paragraph(
            f"Payment received by {_safe_text(business_name)}.",
            thanks_style,
        )
    )

    story.append(Spacer(1, 36))

    story.append(
        _build_footer_block(
            [
                f"Receipt generated by {_safe_text(business_name)} via Payla.",
                f"Reference: {_safe_text(payment_reference)}",
                "This receipt confirms the payment record; "
                "it does not confirm payout settlement.",
            ],
            secured_label="Secured by Payla",
        )
    )

    doc.build(story)

    safe_reference = "".join(
        char for char in reference
        if char.isalnum() or char in ("-", "_")
    )

    return _pdf_response(
        buffer,
        f"Receipt_{safe_reference[:40]}.pdf",
    )