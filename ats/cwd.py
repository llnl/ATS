"""Thread-safe helpers for process current-working-directory changes."""
from contextlib import contextmanager
import os
import threading


_cwd_lock = threading.RLock()


@contextmanager
def chdir(path):
    """Temporarily change process cwd while holding the global cwd lock."""
    with _cwd_lock:
        here = os.getcwd()
        os.chdir(path)
        try:
            yield
        finally:
            os.chdir(here)
