# pipeline.py
# BehaviorMonitor - Event Pipeline
# Connects to the named pipe output of monitor_engine.exe,
# reads newline-delimited JSON events, and writes them to SQLite
# via database.py. Runs on its own thread so the UI stays responsive.

import json
import threading
import time
import os
import sys
from datetime import datetime
from typing import Callable, Optional

import database as db

# ─────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────

PIPE_NAME       = r"\\.\pipe\BehaviorMonitorPipe"
RECONNECT_DELAY = 1.0   # seconds to wait before retrying pipe connection
READ_BUFFER     = 65536  # bytes per read from pipe


# ─────────────────────────────────────────────
#  Pipeline Class
# ─────────────────────────────────────────────

class Pipeline:
    """
    Manages the connection to monitor_engine.exe via named pipe,
    parses incoming JSON events, and stores them in SQLite.

    Usage:
        pipeline = Pipeline(db_path="path/to/events.db")
        pipeline.set_event_callback(my_ui_update_function)
        pipeline.start()
        ...
        pipeline.stop()
    """

    def __init__(self, db_path: str):
        self.db_path        = db_path
        self.conn           = None          # SQLite connection
        self._thread        = None          # background reader thread
        self._running       = False
        self._pipe_handle   = None
        self._lock          = threading.Lock()
        self._leftover      = ""            # partial line buffer between reads

        # Optional callback — called on every parsed event so the UI can update
        # Signature: callback(category: str, event: dict)
        self._event_callback: Optional[Callable] = None

        # Stats counters
        self.stats = {
            "file_events":    0,
            "network_events": 0,
            "process_events": 0,
            "control_events": 0,
            "parse_errors":   0,
        }

    # ─────────────────────────────────────────
    #  Public API
    # ─────────────────────────────────────────

    def set_event_callback(self, callback: Callable) -> None:
        """
        Register a function to be called every time an event arrives.
        The UI uses this to refresh its tables in real time.
        callback(category: str, event: dict)
        """
        self._event_callback = callback

    def start(self) -> None:
        """Start the pipeline background thread."""
        if self._running:
            print("[PIPELINE] Already running.")
            return

        # Open DB connection
        self.conn = db.get_connection(self.db_path)

        self._running = True
        self._thread  = threading.Thread(
            target=self._run,
            name="PipelineThread",
            daemon=True         # dies automatically if main process exits
        )
        self._thread.start()
        print("[PIPELINE] Started.")

    def stop(self) -> None:
        """Signal the pipeline to stop and wait for the thread to finish."""
        print("[PIPELINE] Stopping...")
        self._running = False

        # Unblock the pipe read by closing the handle
        self._close_pipe()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

        # Mark session as stopped in DB
        if self.conn:
            try:
                db.update_session_stopped(self.conn)
            except Exception:
                pass
            self.conn.close()
            self.conn = None

        print("[PIPELINE] Stopped.")

    def is_running(self) -> bool:
        return self._running

    # ─────────────────────────────────────────
    #  Internal: Named Pipe Connection
    # ─────────────────────────────────────────

    def _connect_pipe(self) -> bool:
        """
        Try to open the named pipe created by monitor_engine.exe.
        Returns True on success, False on failure.
        The engine creates the pipe and waits — we connect to it.
        """
        try:
            import ctypes
            import ctypes.wintypes as wt

            kernel32 = ctypes.windll.kernel32

            handle = kernel32.CreateFileW(
                PIPE_NAME,
                0x80000000,  # GENERIC_READ
                0,           # no sharing
                None,        # default security
                3,           # OPEN_EXISTING
                0,           # default attributes
                None
            )

            INVALID_HANDLE = ctypes.c_void_p(-1).value
            if handle == INVALID_HANDLE or handle == 0:
                return False

            self._pipe_handle = handle
            print(f"[PIPELINE] Connected to pipe: {PIPE_NAME}")
            return True

        except Exception as e:
            print(f"[PIPELINE] Pipe connect error: {e}")
            return False

    def _close_pipe(self) -> None:
        """Close the pipe handle if open."""
        if self._pipe_handle:
            try:
                import ctypes
                ctypes.windll.kernel32.CloseHandle(self._pipe_handle)
            except Exception:
                pass
            self._pipe_handle = None

    def _read_pipe_chunk(self) -> Optional[bytes]:
        """
        Read a chunk of bytes from the pipe.
        Returns bytes on success, None if pipe closed or error.
        """
        try:
            import ctypes
            import ctypes.wintypes as wt

            kernel32  = ctypes.windll.kernel32
            buf       = ctypes.create_string_buffer(READ_BUFFER)
            bytes_read = wt.DWORD(0)

            ok = kernel32.ReadFile(
                self._pipe_handle,
                buf,
                READ_BUFFER,
                ctypes.byref(bytes_read),
                None
            )

            if not ok or bytes_read.value == 0:
                return None

            return buf.raw[:bytes_read.value]

        except Exception as e:
            print(f"[PIPELINE] Read error: {e}")
            return None

    # ─────────────────────────────────────────
    #  Internal: Main loop
    # ─────────────────────────────────────────

    def _run(self) -> None:
        """
        Main pipeline loop. Runs on the background thread.
        1. Wait for pipe connection
        2. Read chunks of bytes
        3. Split into lines (newline-delimited JSON)
        4. Parse each JSON line
        5. Route to correct DB insert function
        6. Call UI callback
        """

        # Wait for the engine to create the pipe
        print("[PIPELINE] Waiting for monitor_engine pipe...")
        while self._running:
            if self._connect_pipe():
                break
            time.sleep(RECONNECT_DELAY)

        if not self._running:
            return

        print("[PIPELINE] Reading events...")

        while self._running:
            chunk = self._read_pipe_chunk()

            if chunk is None:
                # Pipe closed — engine has shut down
                print("[PIPELINE] Pipe closed by engine.")
                self._running = False
                break

            # Decode and append to leftover buffer
            try:
                text = chunk.decode("utf-8", errors="replace")
            except Exception:
                continue

            self._leftover += text

            # Split on newlines — each complete line is one JSON event
            lines = self._leftover.split("\n")

            # Last element may be incomplete — save for next read
            self._leftover = lines[-1]

            for line in lines[:-1]:
                line = line.strip()
                if line:
                    self._process_line(line)

        print("[PIPELINE] Read loop exited.")

    # ─────────────────────────────────────────
    #  Internal: Parse and route one JSON line
    # ─────────────────────────────────────────

    def _process_line(self, line: str) -> None:
        """Parse a single JSON line and route it to the right DB table."""
        try:
            event = json.loads(line)
        except json.JSONDecodeError as e:
            print(f"[PIPELINE] JSON parse error: {e} | Line: {line[:80]}")
            self.stats["parse_errors"] += 1
            return

        category  = event.get("category", "")
        operation = event.get("operation", "")
        pid       = event.get("pid", 0)
        detail    = event.get("detail", "")
        timestamp = event.get("timestamp", datetime.now().isoformat())

        try:
            if category == "file":
                self._handle_file(event, timestamp, pid, operation, detail)

            elif category == "network":
                self._handle_network(event, timestamp, pid, operation, detail)

            elif category == "process":
                self._handle_process(event, timestamp, pid, operation, detail)

            elif category == "control":
                self._handle_control(event, timestamp, pid, operation, detail)

            else:
                print(f"[PIPELINE] Unknown category: {category}")
                return

            # Fire UI callback on the event (non-blocking)
            if self._event_callback:
                try:
                    self._event_callback(category, event)
                except Exception as cb_err:
                    print(f"[PIPELINE] Callback error: {cb_err}")

        except Exception as insert_err:
            print(f"[PIPELINE] DB insert error: {insert_err} | Event: {event}")

    # ─────────────────────────────────────────
    #  Internal: Category Handlers
    # ─────────────────────────────────────────

    def _handle_file(self, event: dict, timestamp: str,
                     pid: int, operation: str, detail: str) -> None:
        io_size = int(event.get("io_size", 0))
        db.insert_file_event(
            self.conn,
            timestamp=timestamp,
            pid=pid,
            operation=operation,
            file_path=detail,
            io_size=io_size
        )
        self.stats["file_events"] += 1

    def _handle_network(self, event: dict, timestamp: str,
                        pid: int, operation: str, detail: str) -> None:
        dst_ip   = event.get("dst_ip", "")
        dst_port = int(event.get("dst_port", 0))
        size     = int(event.get("size", 0))
        db.insert_network_event(
            self.conn,
            timestamp=timestamp,
            pid=pid,
            operation=operation,
            detail=detail,
            dst_ip=dst_ip,
            dst_port=dst_port,
            size=size
        )
        self.stats["network_events"] += 1

    def _handle_process(self, event: dict, timestamp: str,
                        pid: int, operation: str, detail: str) -> None:
        child_pid  = int(event.get("child_pid",  0))
        parent_pid = int(event.get("parent_pid", 0))
        exit_code  = event.get("exit_code", None)
        if exit_code is not None:
            exit_code = int(exit_code)

        db.insert_process_event(
            self.conn,
            timestamp=timestamp,
            pid=pid,
            operation=operation,
            detail=detail,
            child_pid=child_pid,
            parent_pid=parent_pid,
            exit_code=exit_code
        )
        self.stats["process_events"] += 1

    def _handle_control(self, event: dict, timestamp: str,
                        pid: int, operation: str, detail: str) -> None:
        db.insert_control_event(
            self.conn,
            timestamp=timestamp,
            operation=operation,
            pid=pid,
            detail=detail
        )
        self.stats["control_events"] += 1

        # Handle special control signals
        if operation == "TargetLaunched":
            print(f"[PIPELINE] Target launched. PID={pid} | Path={detail}")

        elif operation == "TargetExited":
            print(f"[PIPELINE] Target process exited. PID={pid}")

        elif operation == "EngineShutdown":
            print(f"[PIPELINE] Engine shutdown received. Stopping pipeline.")
            self._running = False

    # ─────────────────────────────────────────
    #  Stats
    # ─────────────────────────────────────────

    def get_stats(self) -> dict:
        """Returns current event counters. UI can call this for status bar."""
        return dict(self.stats)

    def print_stats(self) -> None:
        print(f"[PIPELINE] Stats: {self.stats}")


# ─────────────────────────────────────────────
#  Quick self-test — run pipeline.py directly
#  (requires monitor_engine.exe to be running
#   and sending events through the pipe)
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    print("[TEST] Pipeline self-test — will try to connect to pipe.")
    print("[TEST] Make sure monitor_engine.exe is running first.")
    print("[TEST] Press Ctrl+C to stop.\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = db.get_db_path(tmpdir)
        conn    = db.get_connection(db_path)
        db.create_tables(conn)
        conn.close()

        def on_event(category: str, event: dict):
            print(f"  [{category.upper()}] {event.get('operation')} | {event.get('detail', '')[:60]}")

        pipeline = Pipeline(db_path=db_path)
        pipeline.set_event_callback(on_event)
        pipeline.start()

        try:
            while pipeline.is_running():
                time.sleep(1)
                pipeline.print_stats()
        except KeyboardInterrupt:
            print("\n[TEST] Interrupted by user.")

        pipeline.stop()
        pipeline.print_stats()
        print("[TEST] Done.")