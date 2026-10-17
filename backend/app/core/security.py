
# app/core/security.py

import logging
import re
import time
import uuid

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from firebase_admin import auth

logger = logging.getLogger("payla.security")

bearer_scheme = HTTPBearer(auto_error=False)

# Only accept request IDs generated in a safe, predictable format.
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add defensive HTTP headers and log basic request metadata."""

    async def dispatch(self, request: Request, call_next):
        started = time.monotonic()

        incoming_id = request.headers.get("X-Request-ID", "")
        request_id = (
            incoming_id
            if _REQUEST_ID_PATTERN.fullmatch(incoming_id)
            else uuid.uuid4().hex
        )
        request.state.request_id = request_id

        try:
            response = await call_next(request)
        except Exception:
            # Do not log request bodies, authorization headers, or secrets.
            logger.exception(
                "Unhandled request error request_id=%s method=%s path=%s",
                request_id,
                request.method,
                request.url.path,
            )
            raise

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )

        # Do not overwrite a policy deliberately set by a route.
        if "Cross-Origin-Resource-Policy" not in response.headers:
            response.headers["Cross-Origin-Resource-Policy"] = "same-site"

        elapsed_ms = round((time.monotonic() - started) * 1000, 2)

        logger.info(
            "request_complete request_id=%s method=%s path=%s status=%s duration_ms=%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )

        return response


def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    """Require a valid Firebase ID token with the admin custom claim."""

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        claims = auth.verify_id_token(
            credentials.credentials,
            check_revoked=True,
        )
    except Exception:
        logger.warning("Rejected invalid or revoked token on admin endpoint")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if claims.get("admin") is not True:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access required",
        )

    return claims
