"""
Payla email rendering system.

Public API:
    render_email(title, blocks) -> str

For components:
    from app.utils.email_render import components
    from app.utils.email_render.components import heading, paragraph, button

For tokens (rarely needed directly):
    from app.utils.email_render import tokens
"""

from .render import render_email
from . import components
from . import tokens

__all__ = ["render_email", "components", "tokens"]