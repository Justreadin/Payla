"""
Payla email design tokens.

Mirrors the landing page design system so emails and the site read as one
product. Every template should reference these, never hardcode a color or
size. If a value is missing here, add it here rather than inline.
"""

# ==========================
# PALETTE (from payla.css :root)
# ==========================

# Canvas
MIDNIGHT = "#0A0A0A"
MIDNIGHT_SOFT = "#0F0F0F"
MIDNIGHT_CARD_TOP = "#0F0F11"
MIDNIGHT_CARD_MID = "#09090B"
MIDNIGHT_CARD_BOTTOM = "#050506"

# Rose gold
ROSE = "#E8B4B8"
ROSE_DEEP = "#D89FA4"
ROSE_LIGHT = "#F0C5C9"

# Hairlines (used as rgba, but kept here for reference)
ROSE_HAIRLINE_RGBA = "rgba(232,180,184,0.22)"
ROSE_HAIRLINE_SOFT_RGBA = "rgba(232,180,184,0.10)"
ROSE_WASH_RGBA = "rgba(232,180,184,0.05)"

# Text
TEXT_PRIMARY = "#FDFDFD"
TEXT_SECONDARY = "#B8B8B8"
TEXT_TERTIARY = "#7A7A7A"

# State (used sparingly, as a text color only, never a badge)
VERIFIED_GREEN = "#4ADE80"
ERROR_RED = "#FF5C6C"
PENDING_AMBER = "#F0B768"

# ==========================
# TYPOGRAPHY
# ==========================

# Font stacks. Email clients require real fallbacks, no CSS custom properties.
FONT_DISPLAY = "'Playfair Display', Georgia, 'Times New Roman', serif"
FONT_BODY = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
FONT_LORA = "'Lora', Georgia, serif"
FONT_MONO = "'SF Mono', Menlo, Consolas, monospace"

# Type scale (px). Email rendering is more fragile than web, so fixed px only.
FS_DISPLAY_XL = "34px"   # hero headings in welcome emails
FS_DISPLAY_LG = "28px"   # section headings
FS_DISPLAY_MD = "22px"   # card headings, signature
FS_BODY_LG = "18px"      # lead paragraph
FS_BODY = "16px"         # standard body
FS_BODY_SM = "15px"      # secondary body
FS_CAPTION = "13px"      # meta, eyebrow
FS_MICRO = "11px"        # footer, legal

# Line heights (unitless, applied via line-height)
LH_TIGHT = "1.2"
LH_NORMAL = "1.6"
LH_RELAXED = "1.9"

# Letter spacing
LS_TIGHT = "-0.02em"
LS_NORMAL = "0"
LS_WIDE = "0.02em"
LS_EYEBROW = "0.14em"
LS_WORDMARK = "4px"

# ==========================
# STRUCTURE
# ==========================

# The card is the single container every email is built inside.
# 20px radius in email reads slightly softer than the landing page's 16px
# because at small render sizes, 16px looks tight.
CARD_RADIUS = "20px"
CARD_BORDER = f"1px solid {ROSE_HAIRLINE_RGBA}"
CARD_PADDING = "48px"
CARD_PADDING_MOBILE = "32px 24px"
CARD_MAX_WIDTH = "480px"

# Button
BUTTON_RADIUS = "14px"
BUTTON_PADDING = "16px 36px"
BUTTON_FONT_WEIGHT = "600"

# Outer canvas padding (the space around the card, on the obsidian canvas)
CANVAS_PADDING = "60px 20px"
CANVAS_PADDING_MOBILE = "40px 16px"

# ==========================
# SHADOWS (used as literal strings; some clients strip box-shadow)
# ==========================

# One shadow only. Email clients render these inconsistently, so keep it simple.
CARD_SHADOW = "0 24px 60px rgba(0,0,0,0.5)"

# ==========================
# BRAND
# ==========================

WORDMARK = "PAYLA"
SIGNATURE_NAME = "Layla"
SIGNATURE_CLOSING = "I'll be in touch."

# Legal / footer line
POWERED_BY = "Powered by <strong style=\"color:#B8B8B8;\">Payla</strong>."