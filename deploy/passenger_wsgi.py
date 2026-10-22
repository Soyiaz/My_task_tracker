"""Fallback launcher for cPanel "Setup Python App" (Passenger).

Use this ONLY when pm2 is not available on the server, or when background
processes started over SSH are killed when the session ends. The normal path
is deploy/ecosystem.streamlit.config.js with pm2; see deploy/DEPLOY.md.

Streamlit cannot be served through WSGI: it is a Tornado server with a
WebSocket, and Passenger's WSGI bridge has neither. So this file does not try.
Instead, the first request Passenger sends here starts Streamlit as a
detached subprocess on 127.0.0.1:8601 (once, guarded by a lock file and a
port check), and every request is answered with a redirect to the proxied
/tracker path, which Apache must forward to that port (deploy/tracker.htaccess).

cPanel setup, in short:
  Setup Python App -> Create application
    Python version:           3.11 or newer
    Application root:         tracker            (the git clone, ~/tracker)
    Application URL:          tracker-launcher   (any path; only the redirect lives here)
    Application startup file: passenger_wsgi.py
    Application entry point:  application
  then  cp ~/tracker/deploy/passenger_wsgi.py ~/tracker/passenger_wsgi.py
  and install requirements.txt into the app's virtualenv from the same screen.

Opening https://aauaiandrobotics.com/tracker-launcher/ once after a reboot
(or pinging it from a cron job / uptime monitor) is what keeps Streamlit up.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
# The file is meant to be copied to the project root; if it is run from
# deploy/ itself, the project is one level up.
ROOT = HERE if (HERE / "streamlit_app.py").exists() else HERE.parent

PORT = int(os.environ.get("PORT", "8601"))
BASE_URL_PATH = os.environ.get("BASE_URL_PATH", "/tracker").rstrip("/") or "/tracker"
LOCK = ROOT / "logs" / "streamlit.lock"
LOG = ROOT / "logs" / "tracker-passenger.log"
STALE_LOCK_SECONDS = 120


def _port_open() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=0.5):
            return True
    except OSError:
        return False


def _acquire_lock() -> bool:
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    try:
        if LOCK.exists() and time.time() - LOCK.stat().st_mtime > STALE_LOCK_SECONDS:
            LOCK.unlink()
    except OSError:
        pass
    try:
        fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w") as fh:
        fh.write(str(os.getpid()))
    return True


def _start_streamlit() -> None:
    """Start Streamlit detached, once. Harmless to call when it is up."""
    if _port_open() or not _acquire_lock():
        return
    try:
        cmd = [
            sys.executable, "-m", "streamlit", "run", "streamlit_app.py",
            "--server.port", str(PORT),
            "--server.address", "127.0.0.1",
            "--server.headless", "true",
            "--server.baseUrlPath", BASE_URL_PATH,
            "--browser.gatherUsageStats", "false",
            "--server.enableCORS", "false",
            "--server.enableXsrfProtection", "true",
        ]
        env = dict(os.environ, PYTHONUNBUFFERED="1")
        with open(LOG, "ab") as log:
            subprocess.Popen(
                cmd,
                cwd=str(ROOT),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=env,
                start_new_session=True,  # survives Passenger recycling this process
                close_fds=True,
            )
        # Give it a moment so the redirect below does not land on a dead port.
        for _ in range(40):
            if _port_open():
                break
            time.sleep(0.25)
    finally:
        try:
            LOCK.unlink()
        except OSError:
            pass


def application(environ, start_response):
    _start_streamlit()
    target = BASE_URL_PATH + "/"
    body = (
        f'<!doctype html><meta http-equiv="refresh" content="0;url={target}">'
        f'<p>Tracker is starting. <a href="{target}">Open it</a>.</p>'
    ).encode()
    status = "302 Found" if _port_open() else "503 Service Unavailable"
    start_response(
        status,
        [
            ("Location", target),
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
        ],
    )
    return [body]
