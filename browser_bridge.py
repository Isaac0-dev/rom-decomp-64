import sys
import os

# Check if we are running in a browser environment (Pyodide)
try:
    import pyodide
    IS_BROWSER = True
except ImportError:
    IS_BROWSER = False

def get_io_root():
    """Return the root directory for IO operations."""
    if IS_BROWSER:
        return "/"
    return os.getcwd()

def run_in_browser():
    return IS_BROWSER

def patch_system():
    """Apply any necessary monkey patches for browser compatibility."""
    if IS_BROWSER:
        # Mock sys.exit to prevent exit signal
        sys.exit = lambda code=None: None
        
        # Prevent any UI modules from being imported if they exist
        sys.modules['tkinter'] = type('Mock', (), {})()
        sys.modules['tkinter.filedialog'] = type('Mock', (), {})()
        
        # We can also add a shim for requests if needed, 
        # but since extraction doesn't rely on it, we just warn/ignore.
        sys.modules['requests'] = type('Mock', (), {'get': lambda *a, **kw: None})()

        # Mock ThreadPoolExecutor for single-threaded environments (Pyodide)
        import concurrent.futures
        import threading

        class SyncThread:
            def __init__(self, target=None, args=(), kwargs={}, daemon=None):
                self.target = target
                self.args = args
                self.kwargs = kwargs
                self.daemon = daemon
            def start(self):
                if self.target:
                    self.target(*self.args, **self.kwargs)
            def join(self, timeout=None):
                pass

        threading.Thread = SyncThread
        
        class SyncFuture:
            def __init__(self, result):
                self._result = result
            def result(self, timeout=None):
                return self._result
            def add_done_callback(self, fn):
                fn(self)
            def done(self):
                return True

        class SyncExecutor:
            def __init__(self, *args, **kwargs):
                pass
            def submit(self, fn, *args, **kwargs):
                return SyncFuture(fn(*args, **kwargs))
            def map(self, fn, *iterables, timeout=None, chunksize=1):
                return map(fn, *iterables)
            def shutdown(self, wait=True, *, cancel_futures=False):
                pass
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass

        concurrent.futures.ThreadPoolExecutor = SyncExecutor
