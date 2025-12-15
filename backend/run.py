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
        access_log=True
    )
