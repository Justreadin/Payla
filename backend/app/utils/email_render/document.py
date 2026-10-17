"""
The email document wrapper.

This is the single most important file for cross-client rendering.
Do not modify without testing on:
  - Apple Mail (iOS 17+)
  - Gmail iOS
  - Gmail Android
  - Gmail web
  - Outlook web
  - Apple Mail (macOS)

Apple Mail strips background-color from <body> in most configurations,
especially in dark mode. To force the obsidian canvas to paint behind the
entire email, three independent declarations are required:

  1. <body> background-color (some clients respect it)
  2. A full-width <table bgcolor="..."> whose <td> also has
     bgcolor="..." AND style="background-color:..."  (legacy path)
  3. A <div> wrapping everything with width:100% and background-color
     (modern path)

If any one of these is missing, Apple Mail will paint white behind the
email. The triple-nesting is not decorative. It is the fix.

`min-height: 100vh` is deliberately absent everywhere. Email clients
handle vh unreliably, and it causes iOS to scroll past the content.
Document height equals content height. That is correct.
"""

from .tokens import MIDNIGHT, CANVAS_PADDING, CANVAS_PADDING_MOBILE


_DOC_HEAD = """<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="x-apple-disable-message-reformatting">
<meta name="color-scheme" content="dark only">
<meta name="supported-color-schemes" content="dark only">
<title>{title}</title>
<style>
  html, body {{ margin:0; padding:0; background-color:{midnight}; width:100%; }}
  body {{ -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%; }}
  table {{ border-collapse:collapse; mso-table-lspace:0pt; mso-table-rspace:0pt; }}
  img {{ -ms-interpolation-mode:bicubic; border:0; outline:none; text-decoration:none; display:block; }}
  a {{ text-decoration:none; }}

  /* Dark mode re-assertion. */
  @media (prefers-color-scheme: dark) {{
    html, body, table, td {{ background-color:{midnight} !important; }}
    .payla-canvas {{ background-color:{midnight} !important; }}
    .payla-card {{ background-color:{midnight} !important; }}
    .payla-body, .payla-body p, .payla-body li {{ color:#B8B8B8 !important; }}
    .payla-heading {{ color:#E8B4B8 !important; }}
  }}

  /* Mobile tightening. */
  @media only screen and (max-width:600px) {{
    .payla-canvas-td {{ padding:{canvas_padding_mobile} !important; }}
    .payla-card {{ padding:32px 24px !important; }}
    .payla-heading {{ font-size:26px !important; }}
  }}
</style>
</head>"""


def wrap_document(title: str, card_html: str) -> str:
    """
    Wrap a card fragment in a full, iPhone-safe HTML document.

    Args:
        title: The <title> tag content. Not visible in most clients;
               used for accessibility.
        card_html: The rendered <div class="payla-card">...</div> fragment.

    Returns:
        A complete HTML document string, ready to pass to Resend.
    """
    return f"""<!DOCTYPE html>
<html lang="en" style="background-color:{MIDNIGHT}; width:100%;">
{_DOC_HEAD.format(
    title=title,
    midnight=MIDNIGHT,
    canvas_padding_mobile=CANVAS_PADDING_MOBILE,
)}
<body style="margin:0; padding:0; background-color:{MIDNIGHT}; width:100%;">

  <!-- Layer 1: full-width canvas div. -->
  <div class="payla-canvas"
       style="background-color:{MIDNIGHT};
              width:100%;
              margin:0;
              padding:0;">

    <!-- Layer 2: full-width table with bgcolor. -->
    <table role="presentation"
           width="100%"
           cellpadding="0"
           cellspacing="0"
           border="0"
           bgcolor="{MIDNIGHT}"
           style="background-color:{MIDNIGHT}; width:100%;">
      <tr>
        <td class="payla-canvas-td"
            align="center"
            valign="top"
            bgcolor="{MIDNIGHT}"
            style="background-color:{MIDNIGHT};
                   padding:{CANVAS_PADDING};">

          <!-- Layer 3: centered inner container, card-width, so the
               card sits centered on wide clients. -->
          <table role="presentation"
                 width="100%"
                 cellpadding="0"
                 cellspacing="0"
                 border="0"
                 style="max-width:480px; width:100%;">
            <tr>
              <td align="center" valign="top">
                {card_html}
              </td>
            </tr>
          </table>

        </td>
      </tr>
    </table>

  </div>

</body>
</html>"""