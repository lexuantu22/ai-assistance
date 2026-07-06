"""
Background Task Runner - replaces Celery with simple threading
"""
import logging
import threading
from typing import Callable, Any

logger = logging.getLogger(__name__)

_executor_threads: list[threading.Thread] = []


def run_in_background(func: Callable, *args: Any, **kwargs: Any) -> None:
    """Run a function in a background thread."""
    def _wrapper():
        try:
            logger.info(f"[BG] Starting: {func.__name__}")
            func(*args, **kwargs)
            logger.info(f"[BG] Completed: {func.__name__}")
        except Exception as e:
            logger.error(f"[BG] Failed: {func.__name__} - {e}")

    thread = threading.Thread(target=_wrapper, daemon=True)
    thread.start()
    _executor_threads.append(thread)
