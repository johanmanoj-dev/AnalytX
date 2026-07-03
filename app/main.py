# main.py
# AnalytX - Entry Point
# This is the file the user runs to start the tool.
# It sets up the environment, verifies dependencies,
# and launches the PyQt6 UI.

import sys
import os
import logging

# ─────────────────────────────────────────────
#  Path Setup — must happen before any local imports
#  Ensures all files in app\ are importable regardless
#  of where the user runs main.py from.
# ─────────────────────────────────────────────

APP_DIR     = os.path.dirname(os.path.abspath(__file__))   # app\
BASE_DIR    = os.path.normpath(os.path.join(APP_DIR, "..")) # AnalytX\
CORE_DIR    = os.path.join(BASE_DIR, "core")
DATA_DIR    = os.path.join(BASE_DIR, "data")
SESSION_DIR = os.path.join(DATA_DIR, "sessions")
LOGS_DIR    = os.path.join(BASE_DIR, "logs")
ENGINE_PATH = os.path.join(CORE_DIR, "monitor_engine.exe")

# Add app\ to path so all local modules are importable
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


# ─────────────────────────────────────────────
#  Ensure Required Folders Exist
# ─────────────────────────────────────────────

def ensure_folders() -> None:
    """Create required folders if they don't exist yet."""
    for folder in [DATA_DIR, SESSION_DIR, LOGS_DIR]:
        os.makedirs(folder, exist_ok=True)

def cleanup_old_sessions(max_sessions: int = 10) -> None:
    """Keep only the most recent sessions and delete the rest."""
    import shutil
    try:
        sessions = [
            os.path.join(SESSION_DIR, d) for d in os.listdir(SESSION_DIR)
            if os.path.isdir(os.path.join(SESSION_DIR, d))
        ]
        # Sort chronologically (oldest first) based on folder name (timestamp)
        sessions.sort()
        
        if len(sessions) > max_sessions:
            to_delete = sessions[:-max_sessions]
            for folder in to_delete:
                try:
                    shutil.rmtree(folder)
                    import logging
                    logging.info(f"[MAIN] Purged old session: {folder}")
                except Exception as e:
                    pass
    except Exception:
        pass


# ─────────────────────────────────────────────
#  Dependency Checks
# ─────────────────────────────────────────────

def check_python_version() -> tuple[bool, str]:
    """Require Python 3.10+ for match statements and modern type hints."""
    if sys.version_info < (3, 10):
        return False, (
            f"Python 3.10 or higher is required.\n"
            f"You are running Python {sys.version_info.major}.{sys.version_info.minor}.\n"
            f"Please upgrade Python and try again."
        )
    return True, ""


def check_pyqt6() -> tuple[bool, str]:
    """Check PyQt6 is installed."""
    try:
        import PyQt6
        return True, ""
    except ImportError:
        return False, (
            "PyQt6 is not installed.\n\n"
            "Install it by running:\n"
            "    pip install PyQt6\n\n"
            "Then restart AnalytX."
        )


def check_engine() -> tuple[bool, str]:
    """Check monitor_engine.exe is compiled and present."""
    if not os.path.isfile(ENGINE_PATH):
        return False, (
            f"monitor_engine.exe not found at:\n{ENGINE_PATH}\n\n"
            f"Please compile it first:\n"
            f"1. Open a Visual Studio Developer Command Prompt\n"
            f"2. Navigate to the core\\ folder\n"
            f"3. Run build.bat"
        )
    return True, ""


def check_windows() -> tuple[bool, str]:
    """This tool is Windows only."""
    if sys.platform != "win32":
        return False, (
            "AnalytX only supports Windows.\n"
            "ETW (Event Tracing for Windows) is a Windows-only technology."
        )
    return True, ""


def check_admin() -> tuple[bool, str]:
    """Check if running with Administrator privileges (required for ETW)."""
    try:
        import ctypes
        if ctypes.windll.shell32.IsUserAnAdmin():
            return True, ""
        else:
            return False, (
                "Administrator privileges required.\n\n"
                "AnalytX uses ETW (Event Tracing for Windows) which requires "
                "elevated privileges.\n\n"
                "Please restart as Administrator:\n"
                "  Right-click → Run as Administrator"
            )
    except Exception:
        return False, "Could not verify admin privileges."


def run_all_checks() -> list[str]:
    """
    Run all dependency checks.
    Returns a list of error messages — empty list means all passed.
    """
    errors = []
    checks = [
        check_windows,
        check_python_version,
        check_pyqt6,
        check_engine,
        check_admin,
    ]
    for check in checks:
        ok, err = check()
        if not ok:
            errors.append(err)
    return errors


# ─────────────────────────────────────────────
#  Fallback error display without PyQt6
#  (in case PyQt6 isn't installed yet)
# ─────────────────────────────────────────────

def show_error_fallback(errors: list[str]) -> None:
    """
    Show errors using Windows MessageBox via ctypes
    if PyQt6 is not available yet.
    """
    message = "AnalytX failed to start:\n\n"
    message += "\n\n---\n\n".join(errors)

    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            message,
            "AnalytX — Startup Error",
            0x10  # MB_ICONERROR
        )
    except Exception:
        # Last resort — print to console
        logging.error("[ERROR] AnalytX failed to start:")
        for err in errors:
            logging.info(f"  - {err}")


# ─────────────────────────────────────────────
#  Logging Setup
# ─────────────────────────────────────────────

def setup_logging() -> None:
    """
    Redirect stdout and stderr to a log file in logs\
    while also keeping them visible in the console.
    """
    import logging

    log_path = os.path.join(
        LOGS_DIR,
        f"monitor_{__import__('datetime').datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
    )

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )
    logging.info(f"[MAIN] Logging to: {log_path}")


# ─────────────────────────────────────────────
#  Launch UI
# ─────────────────────────────────────────────

def launch_ui() -> int:
    """
    Import and launch the PyQt6 UI.
    Returns the exit code from the Qt application.
    """
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QIcon
    import ui  # ui.py in the same app\ folder

    app = QApplication(sys.argv)
    app.setApplicationName("AnalytX")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("AnalytX")

    # Pass BASE_DIR to UI so it knows where everything lives
    window = ui.MainWindow(base_dir=BASE_DIR)
    window.show()

    return app.exec()


# ─────────────────────────────────────────────
#  Entry Point
# ─────────────────────────────────────────────

def main() -> None:
    # 1. Create required folders and cleanup
    ensure_folders()
    cleanup_old_sessions()

    # 2. Run dependency checks before importing anything heavy
    errors = run_all_checks()
    if errors:
        show_error_fallback(errors)
        sys.exit(1)

    # 3. Setup logging
    setup_logging()

    logging.info("[MAIN] AnalytX starting...")
    logging.info(f"[MAIN] Base dir   : {BASE_DIR}")
    logging.info(f"[MAIN] Engine path: {ENGINE_PATH}")
    logging.info(f"[MAIN] Session dir: {SESSION_DIR}")

    # 4. Launch UI — blocks until window is closed
    exit_code = launch_ui()

    logging.info(f"[MAIN] AnalytX exited with code {exit_code}.")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()