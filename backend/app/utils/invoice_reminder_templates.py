"""
Client-facing invoice reminder templates.

These go to the creator's client, sent by Layla on the creator's behalf.
The brand at the top is the creator's business, not Payla.
The voice is Layla's throughout.

Seven stages. The register escalates as the invoice ages:
  1. first_contact    -- warm introduction
  2. reminder         -- neutral, informational
  3. reminder_2       -- direct, less cushioning
  4. due_today        -- practical, present-tense
  5. overdue_gentle   -- kind, no pressure
  6. overdue_firm     -- direct, professional
  7. payment_received -- grateful, closing

Escalation lives mostly in the subject line and the button label.
The body stays restrained so the emails never feel like collections.
"""

from app.utils.email_render import render_email
from app.utils.email_render.components import (
    heading,
    eyebrow,
    paragraph,
    callout,
    mono,
    divider,
    button,
    state_line,
    sign_off,
)


def _business_header(business_name: str) -> str:
    """Every client-facing email opens with the creator's brand, not Payla."""
    return eyebrow(business_name)


# ==========================
# 1. FIRST CONTACT
# ==========================

def render_first_contact(
    business_name: str, amount: str, link: str,
) -> str:
    return render_email(
        title=f"Invoice from {business_name}",
        blocks=[
            _business_header(business_name),
            heading("A new invoice."),
            paragraph(
                f"I&rsquo;m <strong style=\"color:#FDFDFD;\">Layla</strong>, "
                f"{business_name}&rsquo;s payment concierge. "
                f"I&rsquo;ll be handling your transactions from here on."
            ),
            paragraph(
                f"{business_name} has issued an invoice for "
                f"<strong style=\"color:#FDFDFD;\">{amount}</strong>. "
                f"You can view the details and settle it with one tap below."
            ),
            button("View invoice", link),
            paragraph(
                "Looking forward to working with you.",
                color="#B8B8B8",
                size="15px",
            ),
            sign_off("Talk soon."),
        ],
    )


# ==========================
# 2. REMINDER
# ==========================

def render_reminder(
    business_name: str, amount: str, due_date: str, link: str,
) -> str:
    return render_email(
        title=f"Reminder: invoice from {business_name}",
        blocks=[
            _business_header(business_name),
            heading("A gentle reminder."),
            paragraph(
                f"<strong style=\"color:#FDFDFD;\">Layla</strong> here. "
                f"Your payment of <strong style=\"color:#FDFDFD;\">{amount}</strong> "
                f"to {business_name} is coming up on {due_date}."
            ),
            paragraph(
                "I&rsquo;ve prepared everything for you. "
                "Tap below to handle it early and keep your day moving."
            ),
            button("Settle early", link),
            sign_off("Talk soon."),
        ],
    )


# ==========================
# 3. REMINDER 2
# ==========================

def render_reminder_2(
    business_name: str, amount: str, link: str,
) -> str:
    return render_email(
        title=f"Due tomorrow: {business_name}",
        blocks=[
            _business_header(business_name),
            heading("Due tomorrow."),
            paragraph(
                f"<strong style=\"color:#FDFDFD;\">Layla</strong> here. "
                f"Your <strong style=\"color:#FDFDFD;\">{amount}</strong> payment "
                f"to {business_name} is due tomorrow."
            ),
            paragraph(
                "Your quick-access link is ready. "
                "Settle it in one tap below."
            ),
            button("One-tap payment", link),
            sign_off("Talk soon."),
        ],
    )


# ==========================
# 4. DUE TODAY
# ==========================

def render_due_today(
    business_name: str, amount: str, day_of_week: str, link: str,
) -> str:
    return render_email(
        title=f"Due today: {business_name}",
        blocks=[
            _business_header(business_name),
            heading("Today is the day."),
            paragraph(
                f"Happy {day_of_week}. "
                f"<strong style=\"color:#FDFDFD;\">Layla</strong> here. "
                f"Today is the day for your "
                f"<strong style=\"color:#FDFDFD;\">{amount}</strong> payment "
                f"to {business_name}."
            ),
            paragraph(
                "One tap and I&rsquo;ll make sure they get it instantly, "
                "so you can focus on what you do best."
            ),
            button("Pay now", link),
            paragraph(
                "I&rsquo;ve got you.",
                color="#E8B4B8",
                size="15px",
            ),
            sign_off("Talk soon."),
        ],
    )


# ==========================
# 5. OVERDUE, GENTLE
# ==========================

def render_overdue_gentle(
    business_name: str, amount: str, link: str,
) -> str:
    return render_email(
        title=f"Past due: invoice from {business_name}",
        blocks=[
            _business_header(business_name),
            heading("A quiet note."),
            paragraph(
                f"It&rsquo;s <strong style=\"color:#FDFDFD;\">Layla</strong>. "
                f"I noticed your payment of "
                f"<strong style=\"color:#FDFDFD;\">{amount}</strong> to "
                f"{business_name} is just past due."
            ),
            paragraph(
                "I&rsquo;m keeping your link active and secure so we can "
                "get this cleared without any stress."
            ),
            button("Clear payment", link),
            paragraph(
                "Always here to help.",
                color="#B8B8B8",
                size="15px",
            ),
            sign_off("Talk soon."),
        ],
    )


# ==========================
# 6. OVERDUE, FIRM
# ==========================

def render_overdue_firm(
    business_name: str, amount: str, link: str,
) -> str:
    return render_email(
        title=f"Account review: {business_name}",
        blocks=[
            _business_header(business_name),
            heading("A note from Layla."),
            paragraph(
                f"<strong style=\"color:#FDFDFD;\">Layla</strong> here. "
                f"I&rsquo;m doing my review and noticed your "
                f"<strong style=\"color:#FDFDFD;\">{amount}</strong> payment "
                f"to {business_name} is still open."
            ),
            paragraph(
                "I&rsquo;d like to get this settled for you today so your "
                "account stays in perfect standing. Ready when you are."
            ),
            button("Settle now", link),
            sign_off("Talk soon."),
        ],
    )


# ==========================
# 7. PAYMENT RECEIVED (client-side)
# ==========================

def render_payment_received(
    business_name: str, amount: str,
) -> str:
    """
    Sent to the client confirming their payment went through.
    Distinct from the client receipt, which is a formal document.
    This one is a conversational confirmation.
    """
    return render_email(
        title=f"Payment confirmed: {business_name}",
        blocks=[
            _business_header(business_name),
            state_line("Payment confirmed", state="success"),
            heading("Thank you.", size="28px"),
            paragraph(
                f"Your payment of "
                f"<strong style=\"color:#FDFDFD;\">{amount}</strong> to "
                f"{business_name} has been processed."
            ),
            paragraph(
                "I&rsquo;ve updated your records. A formal receipt "
                "is on its way."
            ),
            paragraph(
                "Thank you for being so prompt.",
                color="#B8B8B8",
                size="15px",
            ),
            sign_off("Talk soon."),
        ],
    )


# ==========================
# REGISTRY
# ==========================

INVOICE_REMINDER_TEMPLATES = {
    "first_contact": {
        "subject": "A new invoice from {business_name}",
        "render": render_first_contact,
    },
    "reminder": {
        "subject": "Reminder: invoice from {business_name}",
        "render": render_reminder,
    },
    "reminder_2": {
        "subject": "Due tomorrow: {business_name}",
        "render": render_reminder_2,
    },
    "due_today": {
        "subject": "Due today: {business_name}",
        "render": render_due_today,
    },
    "overdue_gentle": {
        "subject": "Past due: invoice from {business_name}",
        "render": render_overdue_gentle,
    },
    "overdue_firm": {
        "subject": "Account review: {business_name}",
        "render": render_overdue_firm,
    },
    "payment_received": {
        "subject": "Payment confirmed: {business_name}",
        "render": render_payment_received,
    },
}


def render_invoice_reminder(email_type: str, context: dict) -> str:
    """
    Look up and render a reminder template.

    Only the context keys each template actually needs are passed
    through. This prevents `TypeError: unexpected keyword argument`
    when the caller supplies a superset of keys (e.g. `day_of_week`
    for templates that don't use it).
    """
    entry = INVOICE_REMINDER_TEMPLATES.get(email_type)
    if not entry:
        return ""

    render_fn = entry["render"]

    # Accept only the keyword args the template declares.
    import inspect
    sig = inspect.signature(render_fn)
    accepted = {
        name
        for name, param in sig.parameters.items()
        if param.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
    }

    filtered = {k: v for k, v in context.items() if k in accepted}

    return render_fn(**filtered)
    
def get_invoice_subject(email_type: str, business_name: str) -> str:
    """Return the subject line for a given reminder type."""
    entry = INVOICE_REMINDER_TEMPLATES.get(email_type)
    if not entry:
        return "Invoice notification"
    return entry["subject"].format(business_name=business_name)