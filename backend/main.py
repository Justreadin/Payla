import os
import logging
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
import uvicorn
from firebase_admin import credentials, firestore
from app.scripts.migrate_waitlist import migrate
from app.tasks.launch_emails import auto_start_launch_emails
from app.tasks.reminder_cleanup import cleanup_loop
from app.scripts.flusher import flush_logs
from fastapi_utils.tasks import repeat_every
from app.tasks.reminder_service_loop import reminder_loop
from app.tasks.billing_service_loop import billing_service_loop
from app.tasks.marketing_service_loop import marketing_loop
from fastapi.responses import StreamingResponse
from reminder_cleanup import purge_locked_and_old_reminders, repeat_purge_forever
import time
import threading
import subprocess
import multiprocessing
from celery.bin import beat

# ------------------------------------------------------------
# 1. CONFIG & LOGGING
# ------------------------------------------------------------
from app.core.config import settings
import asyncio
from app.core.auth import get_current_user
from app.core.firebase import db
import logging.config

# ------------------------------------------------------------
# IMPROVED LOGGING CONFIGURATION
# ------------------------------------------------------------
LOG_LEVEL = "INFO" if settings.ENVIRONMENT == "production" else "DEBUG"

logging_config = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "default": {
            "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
        },
    },
    "loggers": {
        "uvicorn": {"handlers": ["console"], "level": LOG_LEVEL},
        "uvicorn.error": {"handlers": ["console"], "level": LOG_LEVEL},
        "uvicorn.access": {"handlers": ["console"], "level": LOG_LEVEL},
        "payla": {"handlers": ["console"], "level": "DEBUG", "propagate": False},
    },
}

logging.config.dictConfig(logging_config)
logger = logging.getLogger("payla")


class CustomProxyHeadersMiddleware(BaseHTTPMiddleware):
    """
    Custom middleware to handle X-Forwarded-For and X-Forwarded-Proto headers,
    replacing ProxyHeadersMiddleware from newer Starlette versions.
    """
    async def dispatch(self, request, call_next):
        # Override client IP if header exists
        x_forwarded_for = request.headers.get("x-forwarded-for")
        if x_forwarded_for:
            # Take the first IP in the list
            request.scope["client"] = (x_forwarded_for.split(",")[0].strip(), 0)
        
        # Override scheme if header exists
        x_forwarded_proto = request.headers.get("x-forwarded-proto")
        if x_forwarded_proto:
            request.scope["scheme"] = x_forwarded_proto
        
        return await call_next(request)


# ------------------------------------------------------------
# 2. FASTAPI APP
# ------------------------------------------------------------
app = FastAPI(
    title="Payla API",
    description="Payla — Paystack for consumers. Invoices, @username links, auto-payouts.",
    version="1.0.0",
    contact={
        "name": "Payla Team",
        "url": "https://payla.ng",
        "email": "hello@payla.ng",
    },
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# ------------------------------------------------------------
# 3. CORS
# ------------------------------------------------------------
origins = [
    "http://127.0.0.1:5500",
    "http://127.0.0.1:8000",
    "https://payla.vercel.app",
    "https://app.payla.ng",
    "https://payla.ng",
]

# Add custom proxy middleware
app.add_middleware(CustomProxyHeadersMiddleware)

if settings.ENVIRONMENT == "production":
    app.add_middleware(
        HTTPSRedirectMiddleware
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------
# 4. ROUTERS (API ROUTES)
# ------------------------------------------------------------
from app.routers import (
    user_router,
    invoice_router,
    payment_router,
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
    presell_router,
    token_gate,
    webhooks,
    marketing_router
)

app.include_router(auth_router.router, prefix="/api", tags=["Auth"])
app.include_router(user_router.router, prefix="/api", tags=["Users"])
app.include_router(invoice_router.router, prefix="/api", tags=["Invoices"])
app.include_router(onboarding_router.router, prefix="/api", tags=["Onboarding"])
app.include_router(payment_router.router, prefix="/api", tags=["Webhook"])
app.include_router(reminder_router.router, prefix="/api", tags=["Reminders"])
app.include_router(subscription_router.router, prefix="/api", tags=["Subscription"])
app.include_router(profile_router.router, prefix="/api", tags=["Profile"])
app.include_router(paylink_router.router, prefix="/api", tags=["Paylink"])
app.include_router(payout_router.router, prefix="/api", tags=["Payout"])
app.include_router(dashboard_router.router, prefix="/api", tags=["Dashboard"])
app.include_router(notifications_router.router, prefix="/api", tags=["Notifications"])
app.include_router(analytics_router.router, prefix="/api", tags=["Analytics"])
app.include_router(receipt_router.router, prefix="/api", tags=["Receipt"])
app.include_router(presell_router.router, prefix="/api", tags=["Presell"])
app.include_router(token_gate.router, prefix="/api", tags=["Token_Gate"])
app.include_router(webhooks.router, prefix="/api", tags=["Webhooks"])
app.include_router(marketing_router.router, tags=["Marketing"])

# ------------------------------------------------------------
# 5. SETUP PATHS
# ------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

if not os.path.exists(FRONTEND_DIR):
    logger.error(f"❌ FRONTEND_DIR not found: {FRONTEND_DIR}")
else:
    logger.info(f"✅ FRONTEND_DIR found: {FRONTEND_DIR}")

# ------------------------------------------------------------
# 6. EXPLICIT STATIC FILE HANDLERS (HIGHEST PRIORITY)
# ------------------------------------------------------------

# Helper function to get MIME type
def get_mime_type(filename: str) -> str:
    """Get correct MIME type for a file"""
    import mimetypes
    mimetypes.init()
    
    # Explicit mappings to ensure correct types
    mime_map = {
        '.js': 'application/javascript',
        '.mjs': 'application/javascript',
        '.css': 'text/css',
        '.json': 'application/json',
        '.svg': 'image/svg+xml',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.ico': 'image/x-icon',
        '.webmanifest': 'application/manifest+json',
        '.woff': 'font/woff',
        '.woff2': 'font/woff2',
        '.ttf': 'font/ttf',
        '.eot': 'application/vnd.ms-fontobject',
    }
    
    ext = os.path.splitext(filename)[1].lower()
    return mime_map.get(ext, mimetypes.guess_type(filename)[0] or 'application/octet-stream')

# JavaScript files - MUST BE FIRST
@app.get("/js/{file_path:path}", include_in_schema=False)
async def serve_js(file_path: str):
    """Serve JavaScript files with correct MIME type"""
    full_path = os.path.join(FRONTEND_DIR, "js", file_path)
    
    # Security check
    if not os.path.abspath(full_path).startswith(os.path.abspath(os.path.join(FRONTEND_DIR, "js"))):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail=f"JS file not found: {file_path}")
    
    logger.info(f"🟢 Serving JS: {file_path} from {full_path}")
    
    return FileResponse(
        full_path,
        media_type="application/javascript",
        headers={
            "Content-Type": "application/javascript; charset=utf-8",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "public, max-age=31536000" if not settings.DEBUG else "no-cache"
        }
    )

# CSS files
@app.get("/css/{file_path:path}", include_in_schema=False)
async def serve_css(file_path: str):
    """Serve CSS files with correct MIME type"""
    full_path = os.path.join(FRONTEND_DIR, "css", file_path)
    
    if not os.path.abspath(full_path).startswith(os.path.abspath(os.path.join(FRONTEND_DIR, "css"))):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail=f"CSS file not found: {file_path}")
    
    logger.info(f"🟢 Serving CSS: {file_path}")
    
    return FileResponse(
        full_path,
        media_type="text/css",
        headers={
            "Content-Type": "text/css; charset=utf-8",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "public, max-age=31536000" if not settings.DEBUG else "no-cache"
        }
    )

# Assets (images, fonts, etc.)
@app.get("/assets/{file_path:path}", include_in_schema=False)
async def serve_assets(file_path: str):
    """Serve asset files with correct MIME type"""
    full_path = os.path.join(FRONTEND_DIR, "assets", file_path)
    
    if not os.path.abspath(full_path).startswith(os.path.abspath(os.path.join(FRONTEND_DIR, "assets"))):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail=f"Asset not found: {file_path}")
    
    mime_type = get_mime_type(file_path)
    logger.info(f"🟢 Serving asset: {file_path} as {mime_type}")
    
    return FileResponse(
        full_path,
        media_type=mime_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "public, max-age=31536000" if not settings.DEBUG else "no-cache"
        }
    )

# Uploads
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ------------------------------------------------------------
# 7. SPECIFIC ROUTES
# ------------------------------------------------------------

@app.get("/health", tags=["System"])
async def health_check():
    try:
        test_doc = db.collection("system").document("healthcheck")
        test_doc.set({"ping": datetime.utcnow()}, merge=True)
        return {"status": "healthy", "db": "connected"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(status_code=503, content={"status": "unhealthy", "error": str(e)})

@app.get("/debug/check-js", tags=["System"])
async def debug_check():
    """Debug endpoint to check JS file serving"""
    js_path = os.path.join(FRONTEND_DIR, "js", "payla.js")
    web_analytics_path = os.path.join(FRONTEND_DIR, "js", "web_analytics.js")
    
    def check_file(path):
        exists = os.path.exists(path)
        content_preview = ""
        file_size = 0
        if exists:
            file_size = os.path.getsize(path)
            with open(path, 'r', encoding='utf-8') as f:
                content_preview = f.read(200)
        return {
            "path": path,
            "exists": exists,
            "size": file_size,
            "preview": content_preview
        }
    
    return {
        "frontend_dir": FRONTEND_DIR,
        "frontend_dir_exists": os.path.exists(FRONTEND_DIR),
        "js_dir": os.path.join(FRONTEND_DIR, "js"),
        "js_dir_exists": os.path.exists(os.path.join(FRONTEND_DIR, "js")),
        "js_dir_contents": os.listdir(os.path.join(FRONTEND_DIR, "js")) if os.path.exists(os.path.join(FRONTEND_DIR, "js")) else [],
        "payla_js": check_file(js_path),
        "web_analytics_js": check_file(web_analytics_path)
    }


@app.get("/me")
async def me(user = Depends(get_current_user)):
    return user

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    favicon_path = os.path.join(FRONTEND_DIR, "assets", "favicon.ico")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/x-icon")
    raise HTTPException(status_code=404, detail="Favicon not found")

@app.get("/site.webmanifest", include_in_schema=False)
async def site_manifest():
    manifest_path = os.path.join(FRONTEND_DIR, "assets", "site.webmanifest")
    if os.path.exists(manifest_path):
        return FileResponse(manifest_path, media_type="application/manifest+json")
    raise HTTPException(status_code=404, detail="Manifest not found")

@app.get("/og-image.jpg", include_in_schema=False)
async def serve_og_image():
    path = os.path.join(FRONTEND_DIR, "assets", "og-image.jpg")
    if os.path.exists(path):
        return FileResponse(path, media_type="image/jpeg")
    raise HTTPException(status_code=404, detail="OG image not found")

@app.get("/reload", include_in_schema=False)
async def reload():
    async def event_stream():
        last = frontend_last_change
        while True:
            if frontend_last_change > last:
                last = frontend_last_change
                yield "data: reload\n\n"
            await asyncio.sleep(0.5)
    return StreamingResponse(event_stream(), media_type="text/event-stream")

# ------------------------------------------------------------
# 8. HTML ROUTES
# ------------------------------------------------------------

@app.get("/i/{invoice_id}", include_in_schema=False)
async def serve_invoice_page(invoice_id: str):
    html_path = os.path.join(FRONTEND_DIR, "i", "public_invoice.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="Invoice page not found")
    return FileResponse(
        html_path, 
        media_type="text/html; charset=utf-8", 
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Content-Type-Options": "nosniff"
        }
    )

@app.get("/@{username}", include_in_schema=False)
@app.get("/@{username}/", include_in_schema=False)
async def serve_paylink_page(username: str):
    """Serve paylink.html for any /@username"""
    username = username.strip().lower()
    paylink_path = os.path.join(FRONTEND_DIR, "paylink.html")

    if not os.path.exists(paylink_path):
        raise HTTPException(status_code=404, detail="Paylink page not found")

    with open(paylink_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    assert settings.BACKEND_URL, "BACKEND_URL must be set in production"

    inject_script = f"""
    <script>
        window.PAYLINK_USERNAME = "{username}";
        window.PAYLINK_API_BASE = "{settings.BACKEND_URL.rstrip('/')}/api/paylinks";
    </script>
    """

    html_content = html_content.replace("</head>", inject_script + "\n</head>")

    return HTMLResponse(
        html_content,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Content-Type-Options": "nosniff"
        }
    )

@app.get("/", include_in_schema=False)
async def serve_index():
    index_path = os.path.join(FRONTEND_DIR, "payla.html")
    if not os.path.exists(index_path):
        raise HTTPException(status_code=404, detail="Index page not found")
    return FileResponse(
        index_path, 
        media_type="text/html; charset=utf-8",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "X-Content-Type-Options": "nosniff"
        }
    )

# ------------------------------------------------------------
# 9. CATCH-ALL FOR OTHER HTML PAGES (MUST BE LAST!)
# ------------------------------------------------------------
@app.get("/{page_name}", include_in_schema=False)
async def serve_html_page(page_name: str):
    # Remove .html extension if present
    if page_name.endswith(".html"):
        page_name = page_name[:-5]

    # Security: block directory traversal
    if ".." in page_name or "/" in page_name or page_name.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid page name")

    # Try {page_name}.html
    html_path = os.path.join(FRONTEND_DIR, f"{page_name}.html")
    if os.path.exists(html_path):
        return FileResponse(
            html_path,
            media_type="text/html; charset=utf-8",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "X-Content-Type-Options": "nosniff"
            }
        )

    # Try {page_name}/index.html
    index_path = os.path.join(FRONTEND_DIR, page_name, "index.html")
    if os.path.exists(index_path):
        return FileResponse(
            index_path,
            media_type="text/html; charset=utf-8",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "X-Content-Type-Options": "nosniff"
            }
        )

    raise HTTPException(status_code=404, detail=f"Page not found: {page_name}")

# ------------------------------------------------------------
# 10. GLOBAL EXCEPTION HANDLER
# ------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": "Something went wrong. We're on it.",
            "request_id": request.headers.get("X-Request-ID"),
        },
    )

# ------------------------------------------------------------
# 11. STARTUP EVENTS
# ------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    logger.info(f"🚀 Payla API started | Env: {settings.ENVIRONMENT} | Debug: {settings.DEBUG}")
    logger.info(f"📁 Frontend: {settings.FRONTEND_URL}")
    if hasattr(settings, "PAYSTACK_WEBHOOK_URL"):
        logger.info(f"🔗 Paystack webhook: {settings.PAYSTACK_WEBHOOK_URL}")

    if not os.getenv("MIGRATION_DONE"):
        logger.info("Running waitlist migration...")
        try:
            migrate()
            os.environ["MIGRATION_DONE"] = "true"
            logger.info("✅ Waitlist migration complete")
        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")
    else:
        logger.info("✅ Waitlist already migrated")
    
    auto_start_launch_emails()

@app.on_event("startup")
async def start_background_tasks():
    """Start all background async tasks"""
    asyncio.create_task(repeat_purge_forever())
    asyncio.create_task(reminder_loop())
    logger.info("✅ Reminder loop started")
    
    asyncio.create_task(billing_service_loop())
    logger.info("✅ Billing loop started")
    
    asyncio.create_task(marketing_loop())
    logger.info("✅ Marketing loop started")

# ------------------------------------------------------------
# 12. REQUEST LOGGING MIDDLEWARE
# ------------------------------------------------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"➡️ {request.client.host} {request.method} {request.url.path}")
    try:
        response = await call_next(request)
    except Exception as e:
        logger.exception(f"💥 Exception during {request.method} {request.url.path}: {e}")
        raise
    logger.info(f"⬅️ {request.method} {request.url.path} → {response.status_code}")
    return response

# ------------------------------------------------------------
# 13. FRONTEND RELOAD WATCHER (DEV ONLY)
# ------------------------------------------------------------
frontend_last_change = time.time()

def watch_frontend():
    global frontend_last_change
    last_mtime = 0
    
    while True:
        try:
            for root, dirs, files in os.walk(FRONTEND_DIR):
                for f in files:
                    path = os.path.join(root, f)
                    mtime = os.path.getmtime(path)
                    if mtime > last_mtime:
                        last_mtime = mtime
                        frontend_last_change = time.time()
        except Exception as e:
            logger.error(f"Watch error: {e}")
        time.sleep(1)

if settings.DEBUG:
    thread = threading.Thread(target=watch_frontend, daemon=True)
    thread.start()
    logger.info("👀 Frontend file watcher started")

# ------------------------------------------------------------
# 14. RUN LOCALLY
# ------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="debug",
        access_log=True
    )