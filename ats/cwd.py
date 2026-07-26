"""Thread-safe helpers for process current-working-directory changes."""
from contextlib import contextmanager
import os
import threading


_cwd_lock = threading.RLock()


@contextmanager
def chdir(path):
    """Temporarily change process cwd while holding the global cwd lock.

    Args:
        path (str): Directory to make the process current-working-directory
            while the context is active.

    Yields:
        None.  The previous current-working-directory is restored when the
        context exits.
    """
    with _cwd_lock:
        here = os.getcwd()
        os.chdir(path)
        try:
            yield
        finally:
            os.chdir(here)
