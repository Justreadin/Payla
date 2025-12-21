import logging
import sys
import asyncio

# ---------------------------
# LOGGER SETUP
# ---------------------------
logger = logging.getLogger("payla")
logger.setLevel(logging.INFO)

# Custom stream handler that flushes after every log
class FlushStreamHandler(logging.StreamHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()  # ensures every log is written immediately

# Formatter
formatter = logging.Formatter(
    "[%(asctime)s] %(levelname)s | %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S"
)

# Create and attach handler
handler = FlushStreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
handler.setFormatter(formatter)

# Remove old handlers and add our flush handler
logger.handlers = [handler]

# ---------------------------
# FLUSH FUNCTION
# ---------------------------
async def flush_logs():
    """
    Flush all handlers immediately.
    Useful if logs seem stuck in buffers.
    """
    for h in logger.handlers:
        h.flush()
    logger.info("✅ Flusher executed, logs flushed")

# ---------------------------
# OPTIONAL: synchronous version
# ---------------------------
def flush_logs_sync():
    """
    Synchronous flush for cases where async not needed.
    """
    for h in logger.handlers:
        h.flush()
    logger.info("✅ Flusher executed (sync)")
