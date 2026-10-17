import os
import re
import json
import time
import asyncio
import logging
import logging.config
import threading
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import (
    HTMLResponse,
    FileResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from google.cloud.firestore_v1.base_query import FieldFilter

from app.core.config import settings
from app.core.auth import get_current_user
from app.core.constants import USERNAME_PATTERN
from app.core.firebase import db
from app.core.security import SecurityHeadersMiddleware

from app.scripts.migrate_waitlist import migrate
from app.tasks.reminder_service_loop import reminder_loop
from app.tasks.billing_reminder import billing_service_loop
# from app.tasks.marketing_service_loop import marketing_loop
from app.tasks.bank_confirmation_retry import (
    start_scheduler as start_bank_confirmation_scheduler,
    stop_scheduler as stop_bank_confirmation_scheduler,
)
from app.tasks.reminder_cleanup import cleanup_loop

# ------------------------------------------------------------
# 1. PATHS & CONFIGURATION
# ------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
UPLOADS_DIR = BASE_DIR / "uploads"
LOGOS_DIR = UPLOADS_DIR / "logos"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

IS_PRODUCTION = str(settings.ENVIRONMENT).lower() == "production"

if IS_PRODUCTION and settings.DEBUG:
    raise RuntimeError(
        "Unsafe configuration: DEBUG must be False in production."
    )

LOG_LEVEL = "INFO" if IS_PRODUCTION else "DEBUG"

logging_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": (
                "%(asctime)s | %(levelname)s | "
                "%(name)s | %(message)s"
            ),
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "uvicorn": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "uvicorn.error": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "uvicorn.access": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "payla": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "payla.security": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
    },
}

logging.config.dictConfig(logging_config)
logger = logging.getLogger("payla")

if FRONTEND_DIR.is_dir():
    logger.info("Frontend directory found")
else:
    logger.warning("Frontend directory not found")

# ------------------------------------------------------------
# 2. FASTAPI APPLICATION
# ------------------------------------------------------------

app = FastAPI(
    title="Payla API",
    description=(
        "Payla — invoices, username payment links, "
        "and payment services."
    ),
    version="1.0.0",
    contact={
        "name": "Payla Team",
        "url": "https://payla.ng",
        "email": "hello@payla.ng",
    },
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

# ------------------------------------------------------------
# 3. MIDDLEWARE
# ------------------------------------------------------------

app.add_middleware(SecurityHeadersMiddleware)

origins = [
    "http://127.0.0.1:5500",
    "http://127.0.0.1:8000",
    "https://payla.vercel.app",
    "https://app.payla.ng",
    "https://payla.ng",
    "https://payla.vip",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=[
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "X-Request-ID",
    ],
)

# ------------------------------------------------------------
# 4. API ROUTERS
# ------------------------------------------------------------

from app.routers import (
    user_router,
    invoice_router,
    ##payment_router,
    onboarding_router,
    reminder_router,
    auth_router,
    subscription_router,
    profile_router,
    payout_router,
    paylink_router,
    dashboard_router,
    notifications_router,
    analytics_router,
    receipt_router,
    token_gate,
    webhooks,
    marketing_router,
    founding_router,
)

app.include_router(auth_router.router, prefix="/api", tags=["Auth"])
app.include_router(user_router.router, prefix="/api", tags=["Users"])
app.include_router(invoice_router.router, prefix="/api", tags=["Invoices"])
app.include_router(onboarding_router.router, prefix="/api", tags=["Onboarding"])
##app.include_router(payment_router.router, prefix="/api", tags=["Payment"])
app.include_router(reminder_router.router, prefix="/api", tags=["Reminders"])
app.include_router(
    subscription_router.router,
    prefix="/api",
    tags=["Subscription"],
)
app.include_router(profile_router.router, prefix="/api", tags=["Profile"])
app.include_router(paylink_router.router, prefix="/api", tags=["Paylinks"])
app.include_router(payout_router.router, prefix="/api", tags=["Payout"])
app.include_router(dashboard_router.router, prefix="/api", tags=["Dashboard"])
app.include_router(
    notifications_router.router,
    prefix="/api",
    tags=["Notifications"],
)
app.include_router(analytics_router.router, prefix="/api", tags=["Analytics"])
app.include_router(receipt_router.router, prefix="/api", tags=["Receipt"])
#app.include_router(presell_router.router, prefix="/api", tags=["Presell"])
app.include_router(token_gate.router, prefix="/api", tags=["Token Gate"])
app.include_router(webhooks.router, prefix="/api", tags=["Webhooks"])
app.include_router(marketing_router.router, tags=["Marketing"])
app.include_router(
    founding_router.router,
    prefix="/api",
    tags=["Founding"],
)

# ------------------------------------------------------------
# 5. SAFE STATIC-FILE HELPERS
# ------------------------------------------------------------

def resolve_static_file(
    root: str | Path,
    relative_path: str,
) -> Path:
    root_path = Path(root).resolve()
    target_path = (root_path / relative_path).resolve()

    try:
        target_path.relative_to(root_path)
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail="Access denied",
        )

    if not target_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="File not found",
        )

    return target_path


def get_mime_type(filename: str) -> str:
    import mimetypes

    mime_map = {
        ".js": "application/javascript",
        ".mjs": "application/javascript",
        ".css": "text/css",
        ".json": "application/json",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".ico": "image/x-icon",
        ".webmanifest": "application/manifest+json",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
        ".ttf": "font/ttf",
        ".eot": "application/vnd.ms-fontobject",
    }

    extension = Path(filename).suffix.lower()

    return mime_map.get(
        extension,
        mimetypes.guess_type(filename)[0]
        or "application/octet-stream",
    )


def static_cache_control() -> str:
    if settings.DEBUG:
        return "no-cache"
    return "public, max-age=31536000, immutable"


# ------------------------------------------------------------
# 6. FRONTEND STATIC FILES
# ------------------------------------------------------------

@app.get("/js/{file_path:path}", include_in_schema=False)
async def serve_js(file_path: str):
    full_path = resolve_static_file(
        FRONTEND_DIR / "js",
        file_path,
    )

    return FileResponse(
        full_path,
        media_type="application/javascript",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": static_cache_control(),
        },
    )


@app.get("/css/{file_path:path}", include_in_schema=False)
async def serve_css(file_path: str):
    full_path = resolve_static_file(
        FRONTEND_DIR / "css",
        file_path,
    )

    return FileResponse(
        full_path,
        media_type="text/css",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": static_cache_control(),
        },
    )


@app.get("/assets/{file_path:path}", include_in_schema=False)
async def serve_assets(file_path: str):
    full_path = resolve_static_file(
        FRONTEND_DIR / "assets",
        file_path,
    )

    return FileResponse(
        full_path,
        media_type=get_mime_type(str(full_path)),
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": static_cache_control(),
        },
    )


# ------------------------------------------------------------
# 7. UPLOADS & LOGOS
# ------------------------------------------------------------

app.mount(
    "/uploads",
    StaticFiles(directory=str(UPLOADS_DIR)),
    name="uploads",
)

if LOGOS_DIR.is_dir():
    app.mount(
        "/logos",
        StaticFiles(directory=str(LOGOS_DIR)),
        name="logos",
    )

# ------------------------------------------------------------
# 8. HEALTH CHECK
# ------------------------------------------------------------

@app.get("/health", tags=["System"])
async def health_check():
    try:
        db.collection("system").document("healthcheck").get()
        return {"status": "healthy"}
    except Exception:
        logger.exception("Health check failed")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy"},
        )


# ------------------------------------------------------------
# 9. DEVELOPMENT-ONLY DEBUG ROUTES
# ------------------------------------------------------------

if settings.DEBUG:

    @app.get("/debug/check-js", include_in_schema=False)
    async def debug_check():
        js_dir = FRONTEND_DIR / "js"
        return {
            "frontend_dir_exists": FRONTEND_DIR.is_dir(),
            "js_dir_exists": js_dir.is_dir(),
            "payla_js_exists": (js_dir / "payla.js").is_file(),
            "web_analytics_exists": (
                js_dir / "web_analytics.js"
            ).is_file(),
        }

    @app.get("/debug/uploads", include_in_schema=False)
    async def debug_uploads():
        return {
            "uploads_exists": UPLOADS_DIR.is_dir(),
            "logos_exists": LOGOS_DIR.is_dir(),
        }


# ------------------------------------------------------------
# 10. AUTHENTICATED CURRENT-USER ENDPOINT
# ------------------------------------------------------------

@app.get("/me", include_in_schema=False)
async def me(user=Depends(get_current_user)):
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )
    return user


# ------------------------------------------------------------
# 11. STANDARD PUBLIC ASSETS
# ------------------------------------------------------------

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    path = FRONTEND_DIR / "assets" / "favicon.ico"
    if path.is_file():
        return FileResponse(
            path,
            media_type="image/x-icon",
            headers={"X-Content-Type-Options": "nosniff"},
        )
    raise HTTPException(status_code=404, detail="Favicon not found")


@app.get("/site.webmanifest", include_in_schema=False)
async def site_manifest():
    path = FRONTEND_DIR / "assets" / "site.webmanifest"
    if path.is_file():
        return FileResponse(
            path,
            media_type="application/manifest+json",
            headers={"X-Content-Type-Options": "nosniff"},
        )
    raise HTTPException(status_code=404, detail="Manifest not found")


@app.get("/og-image.jpg", include_in_schema=False)
async def serve_og_image():
    path = FRONTEND_DIR / "assets" / "og-image.jpg"
    if path.is_file():
        return FileResponse(
            path,
            media_type="image/jpeg",
            headers={"X-Content-Type-Options": "nosniff"},
        )
    raise HTTPException(status_code=404, detail="Image not found")


# ------------------------------------------------------------
# 12. DEVELOPMENT-ONLY FRONTEND RELOAD
# ------------------------------------------------------------

frontend_last_change = time.time()


if settings.DEBUG:

    @app.get("/reload", include_in_schema=False)
    async def reload():
        async def event_stream():
            last = frontend_last_change

            while True:
                if frontend_last_change > last:
                    last = frontend_last_change
                    yield "data: reload\n\n"

                await asyncio.sleep(0.5)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "X-Content-Type-Options": "nosniff",
            },
        )


# ------------------------------------------------------------
# 13. PUBLIC INVOICE PAGE
# ------------------------------------------------------------

@app.get("/i/{invoice_id}", include_in_schema=False)
async def serve_invoice_page(invoice_id: str):
    html_path = FRONTEND_DIR / "i" / "public_invoice.html"

    if not html_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Invoice page not found",
        )

    return FileResponse(
        html_path,
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Content-Type-Options": "nosniff",
        },
    )


# ------------------------------------------------------------
# 14. PUBLIC PAYLINK PAGE
# ------------------------------------------------------------

def _is_vip_host(request: Request) -> bool:
    """Return True when the request arrived on the .vip domain."""
    host = (request.headers.get("host") or "").split(":")[0].lower()
    return host == "payla.vip" or host.endswith(".payla.vip")


def _is_ng_host(request: Request) -> bool:
    """Return True when the request arrived on the .ng domain."""
    host = (request.headers.get("host") or "").split(":")[0].lower()
    return (
        host == "payla.ng"
        or host == "localhost"
        or host == "127.0.0.1"
        or host.endswith(".payla.ng")
    )


def _canonical_paylink_url(username: str, domain: str) -> str:
    base = (
        settings.VIP_BASE_URL if domain == "vip"
        else settings.BACKEND_URL
    )
    return f"{base.rstrip('/')}/@{username}"


@app.get("/@{username}", include_in_schema=False)
@app.get("/@{username}/", include_in_schema=False)
async def serve_paylink_page(username: str, request: Request):
    username = username.strip().lower()

    if not USERNAME_PATTERN.fullmatch(username):
        raise HTTPException(
            status_code=400,
            detail="Invalid username",
        )

    paylink_path = FRONTEND_DIR / "paylink.html"

    if not paylink_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Paylink page not found",
        )

    backend_url = settings.BACKEND_URL

    if not backend_url:
        logger.error("BACKEND_URL is not configured")
        raise HTTPException(
            status_code=500,
            detail="Service configuration error",
        )

    # ── Domain canonicalization ──
    # Read the merchant's preferred_domain and redirect if the
    # incoming host doesn't match. Free users always have "ng".
    # Silver users can have "vip". A redirect fires only when the
    # host and the preference disagree.
    try:
        paylink_docs = list(
            db.collection("paylinks")
            .where(filter=FieldFilter("username", "==", username))
            .limit(1)
            .stream()
        )
    except Exception:
        logger.exception(
            "Could not read paylink domain for @%s", username
        )
        paylink_docs = []

    if paylink_docs:
        paylink_data = paylink_docs[0].to_dict() or {}
        preferred = str(
            paylink_data.get("preferred_domain", "ng")
        ).lower()

        incoming_vip = _is_vip_host(request)
        incoming_ng = _is_ng_host(request)

        # Only .vip → .ng and .ng → .vip are meaningful redirects.
        # Requests from unknown hosts (e.g. Railway internal
        # hostnames) are served as-is.
        redirect_to = None

        if preferred == "vip" and incoming_ng:
            redirect_to = _canonical_paylink_url(username, "vip")
        elif preferred == "ng" and incoming_vip:
            redirect_to = _canonical_paylink_url(username, "ng")

        if redirect_to:
            return RedirectResponse(
                url=redirect_to,
                status_code=301,
            )

    # ── Serve the HTML shell ──
    safe_username = json.dumps(username).replace("<", "\\u003c")

    api_base = f"{backend_url.rstrip('/')}/api/paylinks"
    safe_api_base = json.dumps(api_base).replace("<", "\\u003c")

    safe_host = json.dumps(
        request.headers.get("host", "")
    ).replace("<", "\\u003c")

    try:
        html_content = paylink_path.read_text(encoding="utf-8")
    except OSError:
        logger.exception("Failed to read paylink HTML")
        raise HTTPException(
            status_code=500,
            detail="Unable to load paylink page",
        )

    inject_script = (
        "<script>"
        f"window.PAYLINK_USERNAME = {safe_username};"
        f"window.PAYLINK_API_BASE = {safe_api_base};"
        f"window.PAYLINK_HOST = {safe_host};"
        "</script>"
    )

    if "</head>" not in html_content.lower():
        logger.error("Paylink HTML is missing its head closing tag")
        raise HTTPException(
            status_code=500,
            detail="Unable to load paylink page",
        )

    html_content = re.sub(
        r"</head\s*>",
        lambda _: inject_script + "\n</head>",
        html_content,
        count=1,
        flags=re.IGNORECASE,
    )

    return HTMLResponse(
        content=html_content,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Content-Type-Options": "nosniff",
        },
    )


# ------------------------------------------------------------
# 15. HOMEPAGE
# ------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def serve_index():
    index_path = FRONTEND_DIR / "payla.html"

    if not index_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Index page not found",
        )

    return FileResponse(
        index_path,
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.head("/", include_in_schema=False)
async def head_index():
    return Response(status_code=200)


# ------------------------------------------------------------
# 16. CATCH-ALL HTML ROUTE — KEEP LAST
# ------------------------------------------------------------

@app.get("/{page_name}", include_in_schema=False)
async def serve_html_page(page_name: str):
    if (
        not page_name
        or page_name.startswith(".")
        or ".." in page_name
        or "/" in page_name
        or "\\" in page_name
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid page name",
        )

    if page_name.endswith(".html"):
        page_name = page_name[:-5]

    if (
        not page_name
        or page_name.startswith(".")
        or ".." in page_name
        or "/" in page_name
        or "\\" in page_name
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid page name",
        )

    candidate = FRONTEND_DIR / f"{page_name}.html"

    if candidate.is_file():
        resolved = resolve_static_file(FRONTEND_DIR, f"{page_name}.html")
        return FileResponse(
            resolved,
            media_type="text/html; charset=utf-8",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "X-Content-Type-Options": "nosniff",
            },
        )

    index_candidate = FRONTEND_DIR / page_name / "index.html"

    if index_candidate.is_file():
        relative_path = f"{page_name}/index.html"
        resolved = resolve_static_file(FRONTEND_DIR, relative_path)
        return FileResponse(
            resolved,
            media_type="text/html; charset=utf-8",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "X-Content-Type-Options": "nosniff",
            },
        )

    raise HTTPException(
        status_code=404,
        detail="Page not found",
    )


# ------------------------------------------------------------
# 17. GLOBAL EXCEPTION HANDLER
# ------------------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(
    request: Request,
    exc: Exception,
):
    request_id = getattr(request.state, "request_id", None)

    logger.error(
        "Unhandled application exception request_id=%s method=%s path=%s",
        request_id or "unknown",
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "Something went wrong. We're on it.",
            "request_id": request_id,
        },
    )


# ------------------------------------------------------------
# 18. STARTUP
# ------------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    logger.info(
        "Payla API starting environment=%s debug=%s",
        settings.ENVIRONMENT,
        settings.DEBUG,
    )

    if not FRONTEND_DIR.is_dir():
        logger.warning("Frontend directory is missing")

    if not os.getenv("MIGRATION_DONE"):
        logger.info("Running waitlist migration")

        try:
            migrate()
            os.environ["MIGRATION_DONE"] = "true"
            logger.info("Waitlist migration completed")
        except Exception:
            logger.exception("Waitlist migration failed")


@app.on_event("startup")
async def start_background_tasks():
    asyncio.create_task(cleanup_loop())
    asyncio.create_task(reminder_loop())
    asyncio.create_task(billing_service_loop())
    # asyncio.create_task(marketing_loop())
    start_bank_confirmation_scheduler()

    logger.info("Background task startup requested")


# ------------------------------------------------------------
# 19. DEVELOPMENT-ONLY FRONTEND WATCHER
# ------------------------------------------------------------

def watch_frontend():
    global frontend_last_change

    last_mtime = 0.0

    while True:
        try:
            if FRONTEND_DIR.is_dir():
                for root, dirs, files in os.walk(FRONTEND_DIR):
                    dirs[:] = [
                        directory
                        for directory in dirs
                        if not (Path(root) / directory).is_symlink()
                    ]

                    for filename in files:
                        path = Path(root) / filename

                        try:
                            mtime = path.stat().st_mtime
                        except OSError:
                            continue

                        if mtime > last_mtime:
                            last_mtime = mtime
                            frontend_last_change = time.time()

        except Exception:
            logger.exception("Frontend watcher error")

        time.sleep(1)


if settings.DEBUG:
    watcher_thread = threading.Thread(
        target=watch_frontend,
        name="payla-frontend-watcher",
        daemon=True,
    )
    watcher_thread.start()
    logger.info("Development frontend watcher started")