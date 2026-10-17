"""
Payment alert email.

One template. Sent to the creator when a client pays. Four blocks:
a heading, one sentence of context, one button, a sign-off.

Paystack sends the payer their own receipt at checkout. Payla does not
email the payer, for paylink or invoice payments.
"""

from app.utils.email_render import render_email
from app.utils.email_render.components import (
    heading,
    paragraph,
    button,
    sign_off,
)


def render_user_payment_alert(
    user_name: str,
    amount: str,
    client_email: str,
    button_label: str,
    action_url: str,
) -> str:
    """
    Alert to the creator: a client just paid.

    For invoice payments, the button goes to the paid invoice page.
    For paylink payments, it goes to the payout page.
    """
    return render_email(
        title=f"You just got paid {amount}",
        blocks=[
            heading(f"You just got paid {amount}."),
            paragraph(
                f"<strong style=\"color:#FDFDFD;\">{client_email}</strong> "
                f"just paid you. The funds are on their way to your "
                f"connected bank account."
            ),
            button(button_label, action_url),
            sign_off("Talk soon."),
        ],
    )


def plaintext_user_payment_alert(
    user_name: str,
    amount: str,
    client_email: str,
    button_label: str,
    action_url: str,
) -> str:
    return f"""Hi {user_name},

{client_email} just paid you {amount}.

The funds are on their way to your connected bank account.

{button_label}:
{action_url}

—
Layla
Payla
"""


RECEIPT_TEMPLATES = {
    "user_payment_alert": {
        "html": render_user_payment_alert,
        "text": plaintext_user_payment_alert,
    },
}