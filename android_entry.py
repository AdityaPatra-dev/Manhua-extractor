"""
Android Chaquopy Entrypoint Adapter.
Configures dynamic Android storage paths, initializes the SQLite database,
and launches the Uvicorn/FastAPI server in a background daemon thread.
"""
import os
import sys
import threading
from typing import Optional

_server_thread: Optional[threading.Thread] = None
_server_started = False
_server_port = 8000
_last_error: Optional[str] = None


def get_last_error() -> Optional[str]:
    """Return the last traceback string if server crashed, or None."""
    global _last_error
    return _last_error


def configure_android_paths(internal_dir: str, downloads_dir: str) -> None:
    """Configure Android sandbox and external storage paths."""
    os.environ["MANHUA_IS_ANDROID"] = "1"

    # Internal private app sandbox for SQLite DB & configs
    os.makedirs(internal_dir, exist_ok=True)
    db_path = os.path.join(internal_dir, "manhua_extractor.db")
    os.environ["MANHUA_DB_PATH"] = db_path

    # Public or external downloads folder for CBZ/PDF files
    os.makedirs(downloads_dir, exist_ok=True)
    os.environ["MANHUA_DOWNLOADS_DIR"] = downloads_dir

    # Re-initialize database with Android path
    try:
        from database.db import init_db
        init_db(db_path)
    except Exception as e:
        import traceback
        print(f"[AndroidEntry] Database init error: {traceback.format_exc()}", file=sys.stderr)


def run_uvicorn_server(port: int = 8000) -> None:
    """Run uvicorn server loop on 127.0.0.1 loopback safely in thread."""
    global _server_started, _last_error
    try:
        import asyncio
        import uvicorn
        from app import app
        _server_started = True

        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="info",
            access_log=False,
            loop="asyncio"
        )
        server = uvicorn.Server(config)
        server.install_signal_handlers = lambda: None
        server.run()
    except Exception as e:
        import traceback
        _last_error = traceback.format_exc()
        print(f"[AndroidEntry] Server crash: {_last_error}", file=sys.stderr)


def start_server_thread(internal_dir: str, downloads_dir: str, port: int = 8000) -> bool:
    """
    Called from Kotlin (MainActivity or ForegroundService) via Chaquopy:
    Python.getInstance().getModule("android_entry").callAttr("start_server_thread", internalPath, downloadsPath, 8000)
    """
    global _server_thread, _server_port
    if _server_thread and _server_thread.is_alive():
        return True

    configure_android_paths(internal_dir, downloads_dir)
    _server_port = port

    _server_thread = threading.Thread(
        target=run_uvicorn_server,
        args=(port,),
        name="AndroidFastAPIDaemon",
        daemon=True
    )
    _server_thread.start()
    return True


def is_server_running() -> bool:
    """Check if the internal FastAPI daemon is active."""
    return _server_thread is not None and _server_thread.is_alive()


def get_server_port() -> int:
    """Return active loopback port."""
    return _server_port

