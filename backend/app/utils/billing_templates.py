"""
Subscription billing emails.

Three states, matching core/subscription.py exactly:

  1. silver_renewing_soon -- active, not cancelling, ending within N days.
                             A courtesy notice. Paystack will auto-charge.
  2. silver_ending        -- voluntary cancellation or non-renewing.
                             Access ends at subscription_end. No grace.
  3. silver_grace_period  -- renewal failed, in the 7-day grace window.
                             Access continues until grace ends.

The caller supplies `days_remaining` and `days_left`; these are never
hardcoded. Source of truth is core/subscription.py::get_subscription_status.
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


def render_silver_renewing_soon(
    user_name: str,
    name: str,
    days_remaining: int,
    billing_url: str,
    amount_ngn: int,
    interval: str,
) -> str:
    """
    Sent when Silver is active, not cancelling, and the current period
    ends within the notice window. Paystack will auto-renew. This is a
    courtesy notice, not a warning.
    """
    day_word = "day" if days_remaining == 1 else "days"
    cycle_word = "month" if interval == "monthly" else "year"

    return render_email(
        title=f"Your Silver renews in {days_remaining} {day_word}",
        blocks=[
            state_line("Renewal scheduled", state="success"),
            heading("Your Silver renews soon."),
            paragraph(f"Hi {user_name},"),
            paragraph(
                f"Your Silver subscription for "
                f"{mono(f'payla.ng/@{name}')} renews in "
                f"<strong style=\"color:#FDFDFD;\">{days_remaining} "
                f"{day_word}</strong>."
            ),
            callout(
                f'<p style="font-family:\'Inter\',sans-serif; font-size:15px; '
                f'line-height:1.7; color:#B8B8B8; margin:0 0 6px 0;">'
                f'<strong style="color:#FDFDFD;">Renewal amount:</strong></p>'
                f'<p style="font-family:\'Inter\',sans-serif; font-size:15px; '
                f'line-height:1.7; color:#B8B8B8; margin:0;">'
                f'&#8358;{amount_ngn:,} per {cycle_word}</p>'
            ),
            paragraph(
                "Nothing to do. Your saved payment method will be charged "
                "on the renewal date, and Silver will continue without "
                "interruption."
            ),
            paragraph(
                "If you&rsquo;d like to change your payment method, update "
                "your subscription, or pause renewal, you can do that below."
            ),
            button("Manage subscription", billing_url, variant="outline"),
            divider(),
            paragraph(
                "You&rsquo;re receiving this because Payla Silver renews "
                "automatically. You can turn off auto-renew at any time and "
                "keep Silver through the period you&rsquo;ve already paid for.",
                color="#7A7A7A",
                size="13px",
            ),
            sign_off("I&rsquo;ll be in touch."),
        ],
    )


def render_silver_ending(
    user_name: str,
    name: str,
    days_remaining: int,
    billing_url: str,
) -> str:
    """
    Sent when the user has cancelled or turned off auto-renew, and the
    paid period ends within the notice window. No grace period applies
    after this date.
    """
    day_word = "day" if days_remaining == 1 else "days"

    return render_email(
        title=f"Your Silver ends in {days_remaining} {day_word}",
        blocks=[
            state_line("Subscription ending", state="warning"),
            heading("Your Silver ends soon."),
            paragraph(f"Hi {user_name},"),
            paragraph(
                f"Your Silver subscription for "
                f"{mono(f'payla.ng/@{name}')} ends in "
                f"<strong style=\"color:#FDFDFD;\">{days_remaining} "
                f"{day_word}</strong>."
            ),
            paragraph(
                "You&rsquo;ve already chosen not to renew, so no further "
                "charge will be made."
            ),
            callout(
                '<p style="font-family:\'Inter\',sans-serif; font-size:15px; '
                'line-height:1.7; color:#B8B8B8; margin:0 0 12px 0;">'
                '<strong style="color:#FDFDFD;">What pauses when Silver ends</strong></p>'
                '<p style="font-family:\'Inter\',sans-serif; font-size:15px; '
                'line-height:1.7; color:#B8B8B8; margin:0 0 6px 0;">'
                '&middot; Branded invoices</p>'
                '<p style="font-family:\'Inter\',sans-serif; font-size:15px; '
                'line-height:1.7; color:#B8B8B8; margin:0 0 6px 0;">'
                '&middot; Layla&rsquo;s automated reminders</p>'
                '<p style="font-family:\'Inter\',sans-serif; font-size:15px; '
                'line-height:1.7; color:#B8B8B8; margin:0 0 6px 0;">'
                '&middot; Payment tracking and analytics</p>'
                '<p style="font-family:\'Inter\',sans-serif; font-size:15px; '
                'line-height:1.7; color:#B8B8B8; margin:0;">'
                '&middot; PDF receipts</p>'
            ),
            paragraph(
                "What stays: your Payla name, your page, your Free features, "
                "and your payment history.",
                color="#FDFDFD",
            ),
            paragraph(
                "If you change your mind before the end date, you can resume "
                "Silver at any time. Your founding price stays with your "
                "account if you have one."
            ),
            button("Resume Silver", billing_url),
            paragraph(
                "You can ignore this email if you meant to cancel. Your "
                "access continues until the end of the period "
                "you&rsquo;ve already paid for.",
                color="#7A7A7A",
                size="13px",
            ),
            sign_off("I&rsquo;ll be in touch."),
        ],
    )


def render_silver_grace_period(
    user_name: str,
    name: str,
    days_left: int,
    billing_url: str,
) -> str:
    """
    Sent when a Silver renewal failed and the account is inside the
    7-day grace window. `days_left` comes from
    core/subscription.py::get_subscription_status()["days_left_in_grace"].
    """
    day_word = "day" if days_left == 1 else "days"

    return render_email(
        title="Your Silver subscription needs attention",
        blocks=[
            state_line("Renewal failed", state="error"),
            heading("Your Silver access is in grace."),
            paragraph(f"Hi {user_name},"),
            paragraph(
                f"Your last Silver renewal for "
                f"{mono(f'payla.ng/@{name}')} did not go through. "
                f"You have <strong style=\"color:#FDFDFD;\">{days_left} "
                f"{day_word}</strong> of grace left before Silver features "
                f"are paused."
            ),
            paragraph(
                "Silver features still work during the grace period. "
                "Update your payment method to keep them active."
            ),
            button("Update payment method", billing_url),
            divider(),
            paragraph(
                "What pauses when grace ends:",
                color="#FDFDFD",
                strong=True,
            ),
            paragraph(
                "Branded invoices.<br>"
                "Layla&rsquo;s automated reminders.<br>"
                "Payment tracking and analytics.<br>"
                "PDF receipts.",
                color="#B8B8B8",
            ),
            paragraph(
                "What stays: your Payla name, your page, your Free features, "
                "and your payment history.",
                color="#FDFDFD",
            ),
            sign_off("I&rsquo;ll be in touch."),
        ],
    )