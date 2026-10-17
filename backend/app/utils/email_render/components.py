"""
Reusable email components.

Each function returns an HTML fragment. Compose them into a list and pass
the list to render_email(). Every block already respects the design tokens;
do not inline styles in templates, compose from these instead.
"""

from typing import Optional, Sequence
from .tokens import (
    MIDNIGHT,
    ROSE,
    ROSE_DEEP,
    ROSE_HAIRLINE_RGBA,
    ROSE_HAIRLINE_SOFT_RGBA,
    ROSE_WASH_RGBA,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_TERTIARY,
    VERIFIED_GREEN,
    ERROR_RED,
    FONT_DISPLAY,
    FONT_BODY,
    FONT_LORA,
    FONT_MONO,
    FS_DISPLAY_XL,
    FS_DISPLAY_LG,
    FS_DISPLAY_MD,
    FS_BODY_LG,
    FS_BODY,
    FS_BODY_SM,
    FS_CAPTION,
    FS_MICRO,
    LH_TIGHT,
    LH_NORMAL,
    LH_RELAXED,
    LS_TIGHT,
    LS_EYEBROW,
    LS_WORDMARK,
    CARD_RADIUS,
    CARD_BORDER,
    CARD_PADDING,
    CARD_MAX_WIDTH,
    CARD_SHADOW,
    BUTTON_RADIUS,
    BUTTON_PADDING,
    BUTTON_FONT_WEIGHT,
    WORDMARK,
    SIGNATURE_NAME,
)


# ==========================
# CARD
# ==========================

def card(inner_html: str) -> str:
    """
    The single container every email is built inside.
    Everything else composes into this.
    """
    return (
        f'<div class="payla-card" '
        f'style="background-color:{MIDNIGHT}; '
        f'border:{CARD_BORDER}; '
        f'border-radius:{CARD_RADIUS}; '
        f'padding:{CARD_PADDING}; '
        f'max-width:{CARD_MAX_WIDTH}; '
        f'margin:0 auto; '
        f'box-shadow:{CARD_SHADOW}; '
        f'text-align:left;">'
        f'{inner_html}'
        f'</div>'
    )


# ==========================
# HEADINGS
# ==========================

def heading(text: str, size: str = FS_DISPLAY_XL, color: str = ROSE) -> str:
    """
    Display heading. Playfair, rose, tight.
    Use sparingly: one per email is the correct amount.
    """
    return (
        f'<h1 class="payla-heading" '
        f'style="font-family:{FONT_DISPLAY}; '
        f'font-size:{size}; '
        f'font-weight:400; '
        f'color:{color}; '
        f'letter-spacing:{LS_TIGHT}; '
        f'line-height:{LH_TIGHT}; '
        f'margin:0 0 32px 0;">'
        f'{text}'
        f'</h1>'
    )


def subheading(text: str) -> str:
    """Smaller display heading for sections inside an email."""
    return heading(text, size=FS_DISPLAY_LG)


def eyebrow(text: str, color: str = ROSE) -> str:
    """
    Small uppercase label above a heading.
    Letter-spaced, rose. Used for tier names, section labels.
    """
    return (
        f'<p style="font-family:{FONT_BODY}; '
        f'font-size:{FS_CAPTION}; '
        f'font-weight:600; '
        f'letter-spacing:{LS_EYEBROW}; '
        f'text-transform:uppercase; '
        f'color:{color}; '
        f'margin:0 0 16px 0;">'
        f'{text}'
        f'</p>'
    )


# ==========================
# BODY
# ==========================

def paragraph(
    text: str,
    size: str = FS_BODY,
    color: str = TEXT_SECONDARY,
    italic: bool = False,
    strong: bool = False,
) -> str:
    """Standard body paragraph. Inter, secondary color."""
    style = (
        f'font-family:{FONT_BODY}; '
        f'font-size:{size}; '
        f'line-height:{LH_RELAXED}; '
        f'color:{color}; '
        f'margin:0 0 20px 0; '
    )
    if italic:
        style += f'font-style:italic; font-family:{FONT_LORA}; '
    if strong:
        style += 'font-weight:600; '
    return f'<p style="{style}">{text}</p>'


def lead(text: str) -> str:
    """Larger intro paragraph. Slightly brighter than body."""
    return paragraph(text, size=FS_BODY_LG, color=TEXT_PRIMARY)


def body_lines(lines: Sequence[str]) -> str:
    """
    A stack of single-line body statements, close together.
    Useful for the staccato style in the onboarding sequence.
    """
    inner = "".join(
        f'<p style="font-family:{FONT_BODY}; font-size:{FS_BODY}; '
        f'line-height:{LH_NORMAL}; color:{TEXT_SECONDARY}; margin:0 0 4px 0;">{line}</p>'
        for line in lines
    )
    return f'<div style="margin:0 0 20px 0;">{inner}</div>'


def bullet_list(items: Sequence[str], color: str = TEXT_SECONDARY) -> str:
    """
    Rose-bulleted list. Matches the landing page feature-list.
    Uses a literal bullet character, no separate span.
    """
    rows = "".join(
        f'<li style="font-family:{FONT_BODY}; font-size:{FS_BODY}; '
        f'line-height:{LH_NORMAL}; color:{color}; '
        f'padding-left:20px; margin:0 0 8px 0; position:relative;">'
        f'<span style="color:{ROSE}; position:absolute; left:0; top:0;">'
        f'&middot;</span>{item}</li>'
        for item in items
    )
    return (
        f'<ul style="list-style:none; padding:0; margin:0 0 24px 0;">{rows}</ul>'
    )

# ==========================
# EMPHASIS
# ==========================

def pullquote(text: str) -> str:
    """
    Italic Lora with a rose left rule.
    The landing page equivalent is the bordered italic note.
    """
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'style="margin:32px 0;">'
        f'<tr>'
        f'<td style="border-left:2px solid {ROSE}; padding-left:20px;">'
        f'<p style="font-family:{FONT_LORA}; font-style:italic; '
        f'font-size:{FS_BODY}; line-height:{LH_NORMAL}; color:{TEXT_SECONDARY}; '
        f'margin:0;">{text}</p>'
        f'</td>'
        f'</tr>'
        f'</table>'
    )


def callout(inner_html: str) -> str:
    """
    Rose-washed inset block. Rounded, subtle border.
    Use for grouped information the reader should scan as a set.
    """
    return (
        f'<div style="background:{ROSE_WASH_RGBA}; '
        f'border:1px solid {ROSE_HAIRLINE_SOFT_RGBA}; '
        f'border-radius:16px; '
        f'padding:24px; '
        f'margin:32px 0;">'
        f'{inner_html}'
        f'</div>'
    )


def mono(text: str, color: str = ROSE, size: str = FS_BODY) -> str:
    """Monospace string. For usernames, tokens, invoice IDs."""
    return (
        f'<span style="font-family:{FONT_MONO}; font-size:{size}; '
        f'color:{color}; letter-spacing:0.01em;">{text}</span>'
    )


def inline_highlight(text: str) -> str:
    """Rose-colored emphasis inside a paragraph. Use once, not twice."""
    return f'<span style="color:{ROSE};">{text}</span>'


# ==========================
# DIVIDER
# ==========================

def divider() -> str:
    """Rose hairline, centered, short. The landing page's recurring mark."""
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="margin:40px 0;">'
        f'<tr><td align="center" '
        f'style="background:linear-gradient(90deg,transparent,{ROSE},transparent); '
        f'height:1px; line-height:1px; font-size:1px;">&nbsp;</td></tr>'
        f'</table>'
    )


# ==========================
# BUTTON
# ==========================

def button(label: str, href: str, variant: str = "primary") -> str:
    """
    Rose pill button. The only button style.
    variant: "primary" (rose fill) or "outline" (rose border, no fill).
    """
    if variant == "primary":
        style = (
            f'background-color:{ROSE}; '
            f'color:{MIDNIGHT}; '
            f'border:1px solid {ROSE}; '
        )
    else:
        style = (
            f'background-color:transparent; '
            f'color:{ROSE}; '
            f'border:1px solid {ROSE}; '
        )
    return (
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
        f'style="margin:32px 0;">'
        f'<tr>'
        f'<td align="center" bgcolor="{ROSE if variant == "primary" else MIDNIGHT}" '
        f'style="border-radius:{BUTTON_RADIUS}; '
        f'{style}'
        f'padding:{BUTTON_PADDING}; '
        f'font-family:{FONT_BODY}; font-size:{FS_BODY}; '
        f'font-weight:{BUTTON_FONT_WEIGHT}; '
        f'letter-spacing:0.01em; line-height:1;">'
        f'<a href="{href}" '
        f'style="color:{MIDNIGHT if variant == "primary" else ROSE}; '
        f'text-decoration:none; display:inline-block;">'
        f'{label}'
        f'</a>'
        f'</td>'
        f'</tr>'
        f'</table>'
    )


# ==========================
# STATE ACCENT (used as text color only, never a badge)
# ==========================

def state_line(text: str, state: str = "success") -> str:
    """
    A single colored line indicating state.
    state: "success" (green), "warning" (amber), "error" (red).
    No pills, no badges. The landing page never uses badges in copy.
    """
    color = {
        "success": VERIFIED_GREEN,
        "warning": "#F0B768",
        "error": ERROR_RED,
    }.get(state, TEXT_PRIMARY)
    return (
        f'<p style="font-family:{FONT_BODY}; font-size:{FS_BODY_SM}; '
        f'font-weight:600; color:{color}; '
        f'letter-spacing:0.01em; margin:0 0 16px 0;">'
        f'{text}'
        f'</p>'
    )


# ==========================
# SIGN-OFF (every email ends with this, unchanged)
# ==========================

def sign_off(closing: Optional[str] = None) -> str:
    """
    The Layla signature block. Fixed across all emails.
    Only the `closing` line varies, and only between a small set of approved
    variants ("I'll be in touch.", "Talk soon.", "Always here.").
    """
    closing_line = closing or "I'll be in touch."
    return (
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="margin-top:60px; border-top:1px solid {ROSE_HAIRLINE_SOFT_RGBA};">'
        f'<tr><td style="padding-top:32px;">'
        f'<p style="font-family:{FONT_BODY}; font-size:{FS_BODY_SM}; '
        f'color:{TEXT_TERTIARY}; margin:0 0 8px 0;">{closing_line}</p>'
        f'<p style="font-family:{FONT_DISPLAY}; font-size:{FS_DISPLAY_MD}; '
        f'color:{ROSE}; margin:0 0 4px 0;">&mdash; {SIGNATURE_NAME}</p>'
        f'<p style="font-family:{FONT_BODY}; font-size:{FS_MICRO}; '
        f'font-weight:900; letter-spacing:{LS_WORDMARK}; '
        f'color:rgba(232,180,184,0.5); margin:0;">{WORDMARK}</p>'
        f'</td></tr>'
        f'</table>'
    )