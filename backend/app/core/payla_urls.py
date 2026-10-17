# app/core/payla_urls.py
"""Central URL builders for public Payla links.

The paylink URL depends on the merchant's preferred domain:

  - "ng":  https://payla.ng/@username   (default, Free and Silver)
  - "vip": https://payla.vip/@username  (Silver only)

Invoice URLs are not domain-scoped and always use BACKEND_URL.
"""

from app.core.config import settings


def paylink_url(username: str, domain: str = "ng") -> str:
    """Return the public paylink URL for a username on a given domain."""
    base = (
        settings.VIP_BASE_URL if domain == "vip"
        else settings.BACKEND_URL
    )
    return f"{base.rstrip('/')}/@{username}"


def invoice_url(short_id: str) -> str:
    """Return the public invoice URL. Never domain-scoped."""
    return f"{settings.BACKEND_URL.rstrip('/')}/i/{short_id}"