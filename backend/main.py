import os
import logging
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
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
import time
import threading
import subprocess
# main.py
import multiprocessing
#from app.core.celery_app import celery_app
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------
# 4. ROUTERS
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
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# ------------------------------------------------------------
# 5. FRONTEND STATIC FILES (Serve HTML/CSS/JS)
# ------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")

if os.path.exists(FRONTEND_DIR):
    app.mount("/css", StaticFiles(directory=os.path.join(FRONTEND_DIR, "css")), name="css")
    app.mount("/js", StaticFiles(directory=os.path.join(FRONTEND_DIR, "js")), name="js")
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")), name="assets")
    app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
    logger.info(f"Frontend static directories mounted from {FRONTEND_DIR}")
else:
    logger.warning(f"Frontend directory not found at {FRONTEND_DIR}")

@app.get("/reload")
async def reload():
    async def event_stream():
        last = frontend_last_change
        while True:
            if frontend_last_change > last:
                last = frontend_last_change
                yield "data: reload\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ────────────────────────────────
#  PRIORITY 1: STATIC ALIASES
# ────────────────────────────────
@app.get("/og-image.jpg", include_in_schema=False)
async def serve_og_image():
    # Points directly to the file inside assets
    path = os.path.join(FRONTEND_DIR, "assets", "og-image.jpg")
    if os.path.exists(path):
        return FileResponse(path)
    raise HTTPException(status_code=404, detail="Image file missing in assets folder")

# ────────────────────────────────
#  PAYLINK ROUTE — MUST BE SECOND!
# ────────────────────────────────
@app.get("/@{username}")
@app.get("/@{username}/")
async def serve_paylink_page(username: str):
    """Serve paylink.html for any /@username"""
    username = username.strip().lower()
    paylink_path = os.path.join(FRONTEND_DIR, "paylink.html")

    if not os.path.exists(paylink_path):
        raise HTTPException(status_code=404, detail="paylink.html not found in frontend/")

    with open(paylink_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # Inject username and API base directly into JS
    inject_script = f"""
    <script>
        window.PAYLINK_USERNAME = "{username}";
        window.PAYLINK_API_BASE = "{settings.BACKEND_URL or 'http://127.0.0.1:8000'}/api/paylinks";
    </script>
    """
    html_content = html_content.replace("</head>", inject_script + "\n</head>")

    return HTMLResponse(html_content)


# ─── CRITICAL: ROUTE ORDER MATTERS IN FASTAPI ───
# 1. Invoice public page
@app.get("/i/{invoice_id}", include_in_schema=False)
async def serve_invoice_page(invoice_id: str):
    html_path = os.path.join(FRONTEND_DIR, "i", "public_invoice.html")
    if not os.path.exists(html_path):
        raise HTTPException(status_code=404, detail="public_invoice.html not found")
    return FileResponse(
        html_path, 
        media_type="text/html", 
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
    )


# 2. Named pages: /dashboard, /payout, etc.
@app.get("/{page_name}", include_in_schema=False)
async def serve_html_page(page_name: str, request: Request):
    # Remove .html extension
    if page_name.endswith(".html"):
        page_name = page_name[:-5]

    # Security: block bad paths
    if ".." in page_name or page_name.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid page")

    # ───────────────────────────────────────────
    # Serve file if /frontend/{page_name}.html exists
    # ───────────────────────────────────────────
    html_path = os.path.join(FRONTEND_DIR, f"{page_name}.html")
    if os.path.exists(html_path):
        return FileResponse(
            html_path,
            media_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
        )

    # ───────────────────────────────────────────
    # Serve /frontend/{page_name}/index.html
    # ───────────────────────────────────────────
    dir_path = os.path.join(FRONTEND_DIR, page_name)
    index_path = os.path.join(dir_path, "index.html")
    if os.path.exists(index_path):
        return FileResponse(
            index_path,
            media_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
        )

    # ───────────────────────────────────────────
    # Not found
    # ───────────────────────────────────────────
    raise HTTPException(status_code=404, detail=f"Page '{page_name}' not found")

# 3. Root → payla.html
@app.get("/", include_in_schema=False)
async def serve_index():
    index_path = os.path.join(FRONTEND_DIR, "payla.html")
    if os.path.exists(index_path):
        return FileResponse(
            index_path, 
            media_type="text/html",
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
        )
    raise HTTPException(status_code=404, detail="payla.html not found")

# ------------------------------------------------------------
# 6. HEALTH & USER
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

@app.get("/me")
async def me(user = Depends(get_current_user)):
    return user

# ------------------------------------------------------------
# 7. GLOBAL EXCEPTION HANDLER
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
# 8. STARTUP EVENT
# ------------------------------------------------------------
@app.on_event("startup")
async def startup_event():
    logger.info(f"Payla API started | Env: {settings.ENVIRONMENT} | Debug: {settings.DEBUG}")
    logger.info(f"Frontend: {settings.FRONTEND_URL}")
    if hasattr(settings, "PAYSTACK_WEBHOOK_URL"):
        logger.info(f"Paystack webhook: {settings.PAYSTACK_WEBHOOK_URL}")

    if not os.getenv("MIGRATION_DONE"):
        logger.info("Running waitlist migration...")
        try:
            migrate()
            os.environ["MIGRATION_DONE"] = "true"
            logger.info("Waitlist migration complete.")
        except Exception as e:
            logger.error(f"Migration failed: {e}")
    else:
        logger.info("Waitlist already migrated.")
    auto_start_launch_emails()



@app.on_event("startup")
async def start_background_tasks():
    """
    Start all background async tasks
    """
    # Start reminder processing loop
    asyncio.create_task(reminder_loop())
    logger.info("✅ Async reminder loop started")
    
    # Start reminder cleanup loop
    asyncio.create_task(billing_service_loop())
    logger.info("✅ Async billing loop started")
    asyncio.create_task(marketing_loop())
    logger.info("✅ Async marketing/conversion loop started")


"""
def start_celery_worker():
    subprocess.Popen([
        "celery",
        "-A", "app.core.celery_app.celery_app",
        "worker",
        "--concurrency=30",
        "--loglevel=INFO",
    ])


def start_celery_beat():
    subprocess.Popen([
        "celery",
        "-A", "app.core.celery_app.celery_app",
        "beat",
        "--loglevel=INFO",
    ])


@app.on_event("startup")
def startup_celery():
    # Worker
    threading.Thread(target=start_celery_worker, daemon=True).start()
    # Beat
    threading.Thread(target=start_celery_beat, daemon=True).start()
    logger.info("Celery worker and beat started in background threads.")
"""



# ------------------------------------------------------------
# 9. REQUEST LOGGING MIDDLEWARE
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
    return response  # <--- RETURN THE RESPONSE



# ------------------------------------------------------------
# 10. Frontend Reload
# ------------------------------------------------------------

# Track the last modified timestamp
frontend_last_change = time.time()

FRONTEND_WATCH_DIR = os.path.join(FRONTEND_DIR)

def watch_frontend():
    global frontend_last_change
    last_mtime = 0

    while True:
        try:
            # Get newest modification time of ANY file inside /frontend
            for root, dirs, files in os.walk(FRONTEND_WATCH_DIR):
                for f in files:
                    path = os.path.join(root, f)
                    mtime = os.path.getmtime(path)
                    if mtime > last_mtime:
                        last_mtime = mtime
                        frontend_last_change = time.time()
        except Exception as e:
            print("Watch error:", e)

        time.sleep(1)

# Start watcher thread only in DEV
if settings.DEBUG:
    thread = threading.Thread(target=watch_frontend, daemon=True)
    thread.start()

# ------------------------------------------------------------
# 11. RUN LOCALLY
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
