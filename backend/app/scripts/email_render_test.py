"""
Manual test for the email rendering system.

Run:
    python -m app.scripts.email_render_test

Copy the output and either:
  - Paste into Resend's dashboard as an HTML email to yourself
  - Pipe to a file and open in a browser to preview layout (not iPhone-accurate
    but useful for eyeballing)

The real test is: send it to a Gmail account on iPhone and confirm:
  1. The background is obsidian (#0A0A0A), not white.
  2. Scrolling stops where the content ends, with no white gap below.
  3. The card has a subtle rose hairline and rounded corners.
  4. Type is legible at iPhone width without pinch-zooming.
"""
import sys
from pathlib import Path
from datetime import datetime, timezone
from app.utils.email_render import render_email
from app.utils.email_render.components import (
    card,
    heading,
    eyebrow,
    lead,
    paragraph,
    body_lines,
    bullet_list,
    pullquote,
    callout,
    mono,
    inline_highlight,
    divider,
    button,
    state_line,
    sign_off,
)


BACKEND_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_DIR))


def build_test_email() -> str:
    """Compose an email that exercises every component."""
    blocks = [
        eyebrow("Payla &middot; Test"),
        heading("Welcome, Favour."),
        lead("I&rsquo;m <strong style=\"color:#FDFDFD;\">Layla</strong>."),
        paragraph(
            "I&rsquo;ll be guiding you through Payla, from your "
            f"{inline_highlight('payment identity')}, "
            "to client payments, reminders, invoices, and receipts."
        ),
        body_lines([
            "You do the work.",
            "You deliver on time.",
            "Then you wait.",
        ]),
        pullquote(
            "My emails are short. Intentional. Worth your time. "
            "One minute is all I need."
        ),
        divider(),
        eyebrow("Your rewards"),
        bullet_list([
            "One year of Payla Silver, complimentary",
            "Founding Creator badge",
            "Lifetime price protection",
            "Direct line to support",
        ]),
        callout(
            f'<p style="font-family:\'Inter\',sans-serif; font-size:15px; '
            f'color:#B8B8B8; margin:0 0 8px 0;">Your payment identity</p>'
            f'<p style="margin:0;">{mono("payla.ng/@favour", size="22px")}</p>'
        ),
        state_line("Payment confirmed", state="success"),
        button("View your Payla page", "https://payla.ng/@favour"),
        paragraph(
            "This isn&rsquo;t a payment link. It&rsquo;s your payment identity.",
            color="#FDFDFD",
        ),
        sign_off("I&rsquo;ll be in touch."),
    ]
    return render_email(title="Welcome to Payla", blocks=blocks)


if __name__ == "__main__":
    print(build_test_email())