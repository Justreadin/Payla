"""
The public renderer. This is what templates call.

Usage:

    from app.utils.email_render import render_email
    from app.utils.email_render.components import (
        card, heading, paragraph, button, sign_off, divider,
    )

    html = render_email(
        title="Welcome to Payla",
        blocks=[
            heading("Welcome, Favour."),
            paragraph("I'm Layla. I'll be guiding you through Payla."),
            divider(),
            paragraph("Your identity is ready."),
            button("View your Payla page", "https://payla.ng/@favour"),
            sign_off(),
        ],
    )

The return value is a complete HTML document, ready to pass to any sender.
"""

from typing import Iterable, Sequence
from .document import wrap_document
from .components import card


def render_email(title: str, blocks: Sequence[str]) -> str:
    """
    Compose a list of HTML blocks into a full email document.

    Args:
        title: The <title> tag content. Should match the email subject line
               for accessibility clients.
        blocks: A list of HTML fragments, each returned by a function in
                components.py. They are joined in order inside the card.

    Returns:
        A complete HTML document string.
    """
    inner = "".join(blocks)
    card_html = card(inner)
    return wrap_document(title=title, card_html=card_html)