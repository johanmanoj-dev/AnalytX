# main.py
# BehaviorMonitor - Entry Point
# This is the file the user runs to start the tool.
# It sets up the environment, verifies dependencies,
# and launches the PyQt6 UI.

import sys
import os

# ─────────────────────────────────────────────
#  Path Setup — must happen before any local imports
#  Ensures all files in app\ are importable regardless
#  of where the user runs main.py from.
# ─────────────────────────────────────────────

APP_DIR     = os.path.dirname(os.path.abspath(__file__))   # app\
BASE_DIR    = os.path.normpath(os.path.join(APP_DIR, "..")) # BehaviorMonitor\
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
            "Then restart BehaviorMonitor."
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
            "BehaviorMonitor only supports Windows.\n"
            "ETW (Event Tracing for Windows) is a Windows-only technology."
        )
    return True, ""


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
    message = "BehaviorMonitor failed to start:\n\n"
    message += "\n\n---\n\n".join(errors)

    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            message,
            "BehaviorMonitor — Startup Error",
            0x10  # MB_ICONERROR
        )
    except Exception:
        # Last resort — print to console
        print("[ERROR] BehaviorMonitor failed to start:")
        for err in errors:
            print(f"  - {err}")


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
    print(f"[MAIN] Logging to: {log_path}")


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
    app.setApplicationName("BehaviorMonitor")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("BehaviorMonitor")

    # Pass BASE_DIR to UI so it knows where everything lives
    window = ui.MainWindow(base_dir=BASE_DIR)
    window.show()

    return app.exec()


# ─────────────────────────────────────────────
#  Entry Point
# ─────────────────────────────────────────────

def main() -> None:
    # 1. Create required folders
    ensure_folders()

    # 2. Run dependency checks before importing anything heavy
    errors = run_all_checks()
    if errors:
        show_error_fallback(errors)
        sys.exit(1)

    # 3. Setup logging
    setup_logging()

    print("[MAIN] BehaviorMonitor starting...")
    print(f"[MAIN] Base dir   : {BASE_DIR}")
    print(f"[MAIN] Engine path: {ENGINE_PATH}")
    print(f"[MAIN] Session dir: {SESSION_DIR}")

    # 4. Launch UI — blocks until window is closed
    exit_code = launch_ui()

    print(f"[MAIN] BehaviorMonitor exited with code {exit_code}.")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()