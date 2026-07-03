# launcher.py
# AnalytX - Engine Launcher
# Responsible for starting and stopping monitor_engine.exe as a subprocess,
# passing the correct target exe path and working directory as arguments.
# Also manages the lifecycle of the Pipeline once the engine is running.

import logging
import os
import sys
import subprocess
import threading
import time
from typing import Optional, Callable

import database as db
from pipeline import Pipeline


# ─────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────

# Path to monitor_engine.exe relative to this file's location
# launcher.py is in app\  and engine is in core\
ENGINE_RELATIVE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),  # app\
    "..",                                         # BehaviorMonitor\
    "core",                                       # core\
    "monitor_engine.exe"
)
ENGINE_PATH = os.path.normpath(ENGINE_RELATIVE_PATH)

# Base dir for session data (BehaviorMonitor\data\sessions\)
DATA_BASE_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    ".."
))


# ─────────────────────────────────────────────
#  Launcher Class
# ─────────────────────────────────────────────

class Launcher:
    """
    Manages the full lifecycle of a monitoring session:
      1. Validates the target exe/bat path
      2. Creates a session folder and SQLite DB
      3. Starts monitor_engine.exe with correct arguments
      4. Starts the Pipeline to read events from the pipe
      5. Provides stop() to cleanly shut everything down

    Usage:
        launcher = Launcher()
        launcher.set_event_callback(my_ui_function)
        launcher.set_status_callback(my_status_function)
        ok, error = launcher.start(target_path="C:\\SomeApp\\app.exe")
        ...
        launcher.stop()
    """

    def __init__(self):
        self._engine_process: Optional[subprocess.Popen] = None
        self._pipeline:       Optional[Pipeline]          = None
        self._engine_log_thread: Optional[threading.Thread] = None

        self._session_folder: Optional[str] = None
        self._db_path:        Optional[str] = None
        self._target_path:    Optional[str] = None
        self._working_dir:    Optional[str] = None
        self._is_bat:         bool          = False
        self._running:        bool          = False

        # Callbacks
        # event_callback(category: str, event: dict) — fires on every event
        self._event_callback:  Optional[Callable] = None
        # status_callback(message: str) — fires on status changes (for UI status bar)
        self._status_callback: Optional[Callable] = None

    # ─────────────────────────────────────────
    #  Public API
    # ─────────────────────────────────────────

    def set_event_callback(self, callback: Callable) -> None:
        """Register callback fired on every incoming event. Used by UI."""
        self._event_callback = callback

    def set_status_callback(self, callback: Callable) -> None:
        """Register callback fired on status messages. Used by UI status bar."""
        self._status_callback = callback

    def start(self, target_path: str, working_dir: str = None) -> tuple[bool, str]:
        """
        Start a monitoring session.

        Args:
            target_path: Full path to the target .exe or .bat file.
            working_dir: Optional override for working directory.
                         If None, auto-derived from target_path's folder.

        Returns:
            (True, "") on success
            (False, error_message) on failure
        """
        if self._running:
            return False, "A monitoring session is already running."

        # ── Check admin privileges ────────────
        if not is_admin():
            return False, (
                "Administrator privileges required.\n\n"
                "AnalytX uses ETW (Event Tracing for Windows) which requires "
                "elevated privileges.\n\n"
                "Please restart AnalytX as Administrator:\n"
                "  Right-click → Run as Administrator"
            )

        # ── Validate inputs ───────────────────
        ok, err = self._validate_target(target_path)
        if not ok:
            return False, err

        ok, err = self._validate_engine()
        if not ok:
            return False, err

        # ── Resolve paths ─────────────────────
        self._target_path = os.path.normpath(target_path)
        self._working_dir = os.path.normpath(
            working_dir if working_dir else os.path.dirname(self._target_path)
        )
        ext = os.path.splitext(self._target_path)[1].lower()
        self._is_bat = ext in (".bat", ".cmd")

        # ── Create session DB ─────────────────
        self._session_folder = db.get_session_folder(DATA_BASE_DIR)
        self._db_path        = db.get_db_path(self._session_folder)
        conn = db.get_connection(self._db_path)
        db.create_tables(conn)
        conn.close()

        self._status("Session folder: " + self._session_folder)

        # ── Start engine subprocess ───────────
        ok, err = self._start_engine()
        if not ok:
            return False, err

        # ── Start pipeline ────────────────────
        self._pipeline = Pipeline(db_path=self._db_path)
        if self._event_callback:
            self._pipeline.set_event_callback(self._event_callback)
        self._pipeline.start()

        self._running = True
        self._status(f"Monitoring started — PID tracking for: {self._target_path}")
        return True, ""

    def stop(self) -> None:
        """Stop monitoring — shuts down pipeline then terminates the engine."""
        if not self._running:
            return

        self._status("Stopping monitoring session...")

        # Stop pipeline first (flushes remaining events)
        if self._pipeline:
            self._pipeline.stop()
            self._pipeline = None

        # Terminate engine process
        self._stop_engine()

        self._running = False
        self._status("Monitoring stopped.")

    def is_running(self) -> bool:
        return self._running

    def get_db_path(self) -> Optional[str]:
        """Returns the path to the current session's SQLite DB."""
        return self._db_path

    def get_session_folder(self) -> Optional[str]:
        return self._session_folder

    def get_pipeline_stats(self) -> dict:
        """Returns event counters from the pipeline. UI uses this for status bar."""
        if self._pipeline:
            return self._pipeline.get_stats()
        return {}

    def get_target_path(self) -> Optional[str]:
        return self._target_path

    def get_working_dir(self) -> Optional[str]:
        return self._working_dir

    # ─────────────────────────────────────────
    #  Internal: Validation
    # ─────────────────────────────────────────

    def _validate_target(self, target_path: str) -> tuple[bool, str]:
        """Check the target exe/bat exists and is a supported type."""
        if not target_path:
            return False, "No target file selected."

        if not os.path.isfile(target_path):
            return False, f"Target file not found:\n{target_path}"

        ext = os.path.splitext(target_path)[1].lower()
        if ext not in (".exe", ".bat", ".cmd"):
            return False, f"Unsupported file type '{ext}'.\nOnly .exe, .bat, and .cmd files are supported."

        return True, ""

    def _validate_engine(self) -> tuple[bool, str]:
        """Check monitor_engine.exe exists in the core folder."""
        if not os.path.isfile(ENGINE_PATH):
            return False, (
                f"monitor_engine.exe not found at:\n{ENGINE_PATH}\n\n"
                f"Please compile it first using build.bat in the core\\ folder."
            )
        return True, ""

    # ─────────────────────────────────────────
    #  Internal: Engine Subprocess
    # ─────────────────────────────────────────

    def _kill_stale_engines(self) -> None:
        """Kill any leftover monitor_engine.exe processes from previous sessions.
        A stale engine holds the named pipe open, causing CreateNamedPipeW
        to fail with ERROR_PIPE_BUSY when starting a new session."""
        try:
            result = subprocess.run(
                ["taskkill", "/F", "/IM", "monitor_engine.exe"],
                capture_output=True, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode == 0:
                logging.info("[LAUNCHER] Killed stale monitor_engine.exe process(es).")
                time.sleep(0.3)  # Allow OS to release pipe handles
        except Exception:
            pass  # taskkill fails if no matching process exists — that's fine

    def _start_engine(self) -> tuple[bool, str]:
        """
        Launch monitor_engine.exe as a hidden subprocess.
        Arguments passed: <target_path> <working_dir>
        """
        try:
            # Clean up any orphaned engine processes from crashed sessions
            self._kill_stale_engines()

            cmd = [
                os.path.normpath(ENGINE_PATH),
                os.path.normpath(self._target_path),
                os.path.normpath(self._working_dir),
                r"\\.\pipe\BehaviorMonitorPipe"
            ]

            self._status(f"Launching engine: {' '.join(cmd)}")

            logging.info(f"[DEBUG] CMD: {cmd}")

            # CREATE_NO_WINDOW hides the engine's console from the user
            self._engine_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            # Start a thread to read engine's stdout/stderr for internal logging
            self._engine_log_thread = threading.Thread(
                target=self._read_engine_logs,
                daemon=True,
                name="EngineLogThread"
            )
            self._engine_log_thread.start()

            # Give the engine a moment to initialize and create the pipe
            time.sleep(0.5)

            # Check it didn't immediately crash
            if self._engine_process.poll() is not None:
                stderr = self._engine_process.stderr.read().decode("utf-8", errors="replace")
                return False, f"monitor_engine.exe exited immediately.\nError:\n{stderr}"

            self._status(f"Engine started. PID={self._engine_process.pid}")
            return True, ""

        except Exception as e:
            return False, f"Failed to start monitor_engine.exe:\n{str(e)}"

    def _stop_engine(self) -> None:
        """Terminate the engine subprocess cleanly."""
        if not self._engine_process:
            return

        try:
            # Check if already exited on its own
            if self._engine_process.poll() is None:
                self._engine_process.terminate()

                # Give it 3 seconds to exit gracefully
                try:
                    self._engine_process.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    # Force kill if it didn't respond
                    self._engine_process.kill()
                    self._engine_process.wait()

            self._status(f"Engine process stopped. Exit code: {self._engine_process.returncode}")

        except Exception as e:
            logging.error(f"[LAUNCHER] Error stopping engine: {e}")
        finally:
            self._engine_process = None

    def _read_engine_logs(self) -> None:
        """
        Reads stdout from monitor_engine.exe on a background thread.
        Prints to console during development — can be written to log file later.
        """
        try:
            for line in iter(self._engine_process.stdout.readline, b""):
                decoded = line.decode("utf-8", errors="replace").strip()
                if decoded:
                    logging.info(f"[ENGINE] {decoded}")
        except Exception:
            pass

    # ─────────────────────────────────────────
    #  Internal: Status helper
    # ─────────────────────────────────────────

    def _status(self, message: str) -> None:
        """Send a status message to the registered callback and also print it."""
        logging.info(f"[LAUNCHER] {message}")
        if self._status_callback:
            try:
                self._status_callback(message)
            except Exception as e:
                logging.error(f"[LAUNCHER] Status callback error: {e}")


# ─────────────────────────────────────────────
#  Utility: Admin Check
# ─────────────────────────────────────────────

def is_admin() -> bool:
    """
    Check if the current process has Administrator privileges.
    Required because ETW kernel providers only work when elevated.
    """
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


# ─────────────────────────────────────────────
#  Utility: Get list of running processes
#  Used by UI if we later add "attach to PID" feature
# ─────────────────────────────────────────────

def get_running_processes() -> list[dict]:
    """
    Returns a list of currently running processes as dicts:
    {"pid": int, "name": str, "path": str}
    Uses tasklist via subprocess — no extra libraries needed.
    """
    processes = []
    try:
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        for line in result.stdout.strip().splitlines():
            parts = line.strip('"').split('","')
            if len(parts) >= 2:
                name = parts[0]
                try:
                    pid = int(parts[1])
                except ValueError:
                    continue
                processes.append({"pid": pid, "name": name, "path": ""})
    except Exception as e:
        logging.error(f"[LAUNCHER] get_running_processes error: {e}")
    return processes


# ─────────────────────────────────────────────
#  Quick self-test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    logging.info("[TEST] Launcher self-test")
    logging.info(f"[TEST] Engine path resolved to: {ENGINE_PATH}")
    logging.info(f"[TEST] Engine exists: {os.path.isfile(ENGINE_PATH)}")
    logging.info(f"[TEST] Data base dir: {DATA_BASE_DIR}")

    logging.info("\n[TEST] Running processes (first 5):")
    procs = get_running_processes()
    for p in procs[:5]:
        logging.info(f"  PID={p['pid']}  NAME={p['name']}")

    logging.info("\n[TEST] To test full launch, call:")
    logging.info("  launcher = Launcher()")
    logging.info("  ok, err = launcher.start('C:\\\\path\\\\to\\\\app.exe')")