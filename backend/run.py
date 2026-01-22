# run.py
import uvicorn
from app.core.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "main:app",                # points to main.py's app
        host="0.0.0.0",            # bind to all interfaces
        port=8000,                 # default port
        reload=settings.DEBUG,     # auto-reload in dev
        log_level="debug" if settings.DEBUG else "info",
        access_log=True,
        # ------------------------------------------------------------
        # CRITICAL FIX FOR MIXED CONTENT / HTTPS REDIRECTS
        # ------------------------------------------------------------
        proxy_headers=True,      # Tells Uvicorn to trust headers like X-Forwarded-Proto
        forwarded_allow_ips="*"  # Allows these headers from any proxy IP (safe for cloud deployments)
    )