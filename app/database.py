# database.py
# BehaviorMonitor - Database Handler
# Creates and manages the SQLite database for storing monitored events.
# Used by pipeline.py (writing) and ui.py / reporter.py (reading)

import sqlite3
import os
from datetime import datetime


# ─────────────────────────────────────────────
#  Session folder & DB path management
# ─────────────────────────────────────────────

def get_session_folder(base_dir: str) -> str:
    """
    Creates a timestamped session folder inside base_dir/data/sessions/
    and returns its path. Called once when monitoring starts.
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    session_folder = os.path.join(base_dir, "data", "sessions", f"session_{timestamp}")
    os.makedirs(session_folder, exist_ok=True)
    return session_folder


def get_db_path(session_folder: str) -> str:
    """Returns the full path to the SQLite DB file inside the session folder."""
    return os.path.join(session_folder, "events.db")


# ─────────────────────────────────────────────
#  Database Connection
# ─────────────────────────────────────────────

def get_connection(db_path: str) -> sqlite3.Connection:
    """
    Opens and returns a SQLite connection with sensible defaults.
    Uses WAL mode so the UI can read while pipeline writes simultaneously.
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row          # rows behave like dicts
    conn.execute("PRAGMA journal_mode=WAL") # allows concurrent read + write
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# ─────────────────────────────────────────────
#  Schema Creation
# ─────────────────────────────────────────────

def create_tables(conn: sqlite3.Connection) -> None:
    """
    Creates all tables if they don't exist yet.
    Called once at the start of a monitoring session.
    """
    cursor = conn.cursor()

    # ── Session metadata ──────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS session_info (
            id              INTEGER PRIMARY KEY,
            target_path     TEXT    NOT NULL,
            working_dir     TEXT    NOT NULL,
            root_pid        INTEGER NOT NULL,
            started_at      TEXT    NOT NULL,
            stopped_at      TEXT,
            status          TEXT    DEFAULT 'running'
        )
    """)

    # ── File system events ────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS file_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL,
            pid         INTEGER NOT NULL,
            operation   TEXT    NOT NULL,  -- e.g. Create, Read, Write, Delete
            file_path   TEXT    NOT NULL,
            io_size     INTEGER DEFAULT 0
        )
    """)

    # ── Network events ────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS network_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL,
            pid         INTEGER NOT NULL,
            operation   TEXT    NOT NULL,  -- e.g. Connect, Send, Receive
            detail      TEXT    NOT NULL,  -- "src_ip:port -> dst_ip:port"
            dst_ip      TEXT,
            dst_port    INTEGER DEFAULT 0,
            size        INTEGER DEFAULT 0
        )
    """)

    # ── Process events ────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS process_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL,
            pid         INTEGER NOT NULL,
            operation   TEXT    NOT NULL,  -- ChildProcessStart, ProcessExit
            detail      TEXT,              -- image name or exit info
            child_pid   INTEGER DEFAULT 0,
            parent_pid  INTEGER DEFAULT 0,
            exit_code   INTEGER
        )
    """)

    # ── Control events (engine lifecycle messages) ────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS control_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL,
            operation   TEXT    NOT NULL,  -- TargetLaunched, TargetExited, EngineShutdown
            pid         INTEGER DEFAULT 0,
            detail      TEXT
        )
    """)

    # ── Indexes for fast UI queries ───────────────────────────
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_file_pid       ON file_events(pid)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_file_op        ON file_events(operation)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_file_path      ON file_events(file_path)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_network_pid    ON network_events(pid)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_network_dst    ON network_events(dst_ip)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_process_pid    ON process_events(pid)")

    conn.commit()
    print("[DB] Tables created successfully.")


# ─────────────────────────────────────────────
#  Insert Functions — called by pipeline.py
# ─────────────────────────────────────────────

def insert_session(conn: sqlite3.Connection, target_path: str,
                   working_dir: str, root_pid: int) -> int:
    """Inserts session metadata and returns the session row id."""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO session_info (target_path, working_dir, root_pid, started_at, status)
        VALUES (?, ?, ?, ?, 'running')
    """, (target_path, working_dir, root_pid, datetime.now().isoformat()))
    conn.commit()
    return cursor.lastrowid


def update_session_stopped(conn: sqlite3.Connection) -> None:
    """Marks the session as stopped with a timestamp."""
    conn.execute("""
        UPDATE session_info
        SET stopped_at = ?, status = 'stopped'
        WHERE id = (SELECT MAX(id) FROM session_info)
    """, (datetime.now().isoformat(),))
    conn.commit()


def insert_file_event(conn: sqlite3.Connection, timestamp: str, pid: int,
                      operation: str, file_path: str, io_size: int = 0) -> None:
    conn.execute("""
        INSERT INTO file_events (timestamp, pid, operation, file_path, io_size)
        VALUES (?, ?, ?, ?, ?)
    """, (timestamp, pid, operation, file_path, io_size))
    conn.commit()


def insert_network_event(conn: sqlite3.Connection, timestamp: str, pid: int,
                         operation: str, detail: str,
                         dst_ip: str = "", dst_port: int = 0, size: int = 0) -> None:
    conn.execute("""
        INSERT INTO network_events (timestamp, pid, operation, detail, dst_ip, dst_port, size)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (timestamp, pid, operation, detail, dst_ip, dst_port, size))
    conn.commit()


def insert_process_event(conn: sqlite3.Connection, timestamp: str, pid: int,
                         operation: str, detail: str = "",
                         child_pid: int = 0, parent_pid: int = 0,
                         exit_code: int = None) -> None:
    conn.execute("""
        INSERT INTO process_events (timestamp, pid, operation, detail, child_pid, parent_pid, exit_code)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (timestamp, pid, operation, detail, child_pid, parent_pid, exit_code))
    conn.commit()


def insert_control_event(conn: sqlite3.Connection, timestamp: str,
                         operation: str, pid: int = 0, detail: str = "") -> None:
    conn.execute("""
        INSERT INTO control_events (timestamp, operation, pid, detail)
        VALUES (?, ?, ?, ?)
    """, (timestamp, operation, pid, detail))
    conn.commit()


# ─────────────────────────────────────────────
#  Query Functions — called by ui.py and reporter.py
# ─────────────────────────────────────────────

def get_session_info(conn: sqlite3.Connection) -> sqlite3.Row:
    """Returns the most recent session's metadata row."""
    return conn.execute("""
        SELECT * FROM session_info ORDER BY id DESC LIMIT 1
    """).fetchone()


def get_file_events(conn: sqlite3.Connection, limit: int = 500,
                    pid_filter: int = None, op_filter: str = None) -> list:
    """
    Returns file events, newest first.
    Optionally filter by PID or operation type.
    """
    query  = "SELECT * FROM file_events WHERE 1=1"
    params = []
    if pid_filter:
        query += " AND pid = ?"
        params.append(pid_filter)
    if op_filter:
        query += " AND operation LIKE ?"
        params.append(f"%{op_filter}%")
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return conn.execute(query, params).fetchall()


def get_network_events(conn: sqlite3.Connection, limit: int = 500,
                       pid_filter: int = None, ip_filter: str = None) -> list:
    """Returns network events, newest first. Optionally filter by PID or destination IP."""
    query  = "SELECT * FROM network_events WHERE 1=1"
    params = []
    if pid_filter:
        query += " AND pid = ?"
        params.append(pid_filter)
    if ip_filter:
        query += " AND dst_ip LIKE ?"
        params.append(f"%{ip_filter}%")
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return conn.execute(query, params).fetchall()


def get_process_events(conn: sqlite3.Connection, limit: int = 500,
                       pid_filter: int = None) -> list:
    """Returns process events, newest first."""
    query  = "SELECT * FROM process_events WHERE 1=1"
    params = []
    if pid_filter:
        query += " AND pid = ?"
        params.append(pid_filter)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    return conn.execute(query, params).fetchall()


def get_all_events_combined(conn: sqlite3.Connection, limit: int = 200) -> list:
    """
    Returns a unified list of recent events across all categories,
    sorted by timestamp descending. Useful for the 'All Events' tab in the UI.
    """
    query = """
        SELECT timestamp, 'file'    AS category, operation, file_path  AS detail, pid FROM file_events
        UNION ALL
        SELECT timestamp, 'network' AS category, operation, detail,               pid FROM network_events
        UNION ALL
        SELECT timestamp, 'process' AS category, operation, detail,               pid FROM process_events
        ORDER BY timestamp DESC
        LIMIT ?
    """
    return conn.execute(query, (limit,)).fetchall()


def get_summary_stats(conn: sqlite3.Connection) -> dict:
    """
    Returns a summary dict with event counts per category.
    Used by the reporter and the UI status bar.
    """
    file_count    = conn.execute("SELECT COUNT(*) FROM file_events").fetchone()[0]
    network_count = conn.execute("SELECT COUNT(*) FROM network_events").fetchone()[0]
    process_count = conn.execute("SELECT COUNT(*) FROM process_events").fetchone()[0]

    unique_files  = conn.execute("SELECT COUNT(DISTINCT file_path) FROM file_events").fetchone()[0]
    unique_ips    = conn.execute("SELECT COUNT(DISTINCT dst_ip) FROM network_events WHERE dst_ip != ''").fetchone()[0]

    return {
        "file_events":    file_count,
        "network_events": network_count,
        "process_events": process_count,
        "unique_files":   unique_files,
        "unique_ips":     unique_ips,
        "total_events":   file_count + network_count + process_count,
    }


def get_unique_ips(conn: sqlite3.Connection) -> list:
    """Returns list of all unique destination IPs contacted."""
    rows = conn.execute("""
        SELECT DISTINCT dst_ip, COUNT(*) as hits
        FROM network_events
        WHERE dst_ip != ''
        GROUP BY dst_ip
        ORDER BY hits DESC
    """).fetchall()
    return rows


def get_unique_files(conn: sqlite3.Connection) -> list:
    """Returns list of all unique files touched with operation counts."""
    rows = conn.execute("""
        SELECT file_path, COUNT(*) as hits, GROUP_CONCAT(DISTINCT operation) as operations
        FROM file_events
        GROUP BY file_path
        ORDER BY hits DESC
    """).fetchall()
    return rows


# ─────────────────────────────────────────────
#  Quick self-test — run this file directly to verify DB works
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    print("[TEST] Running database self-test...")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = get_db_path(tmpdir)
        conn    = get_connection(db_path)
        create_tables(conn)

        # Insert dummy session
        insert_session(conn, "C:\\test\\app.exe", "C:\\test\\", 1234)

        # Insert dummy events
        insert_file_event(conn, "2025-01-01 10:00:00.000", 1234, "Create", "C:\\test\\config.ini", 512)
        insert_file_event(conn, "2025-01-01 10:00:01.000", 1234, "Read",   "C:\\test\\data.db",    1024)
        insert_network_event(conn, "2025-01-01 10:00:02.000", 1234, "Connect",
                             "192.168.1.5:54321 -> 93.184.216.34:443",
                             "93.184.216.34", 443, 0)
        insert_process_event(conn, "2025-01-01 10:00:03.000", 1234, "ChildProcessStart",
                             "cmd.exe", child_pid=5678, parent_pid=1234)
        insert_control_event(conn, "2025-01-01 10:00:00.000", "TargetLaunched", 1234, "C:\\test\\app.exe")

        # Query and print
        stats = get_summary_stats(conn)
        print(f"[TEST] Stats: {stats}")

        file_events = get_file_events(conn)
        print(f"[TEST] File events: {[dict(r) for r in file_events]}")

        net_events = get_network_events(conn)
        print(f"[TEST] Network events: {[dict(r) for r in net_events]}")

        combined = get_all_events_combined(conn)
        print(f"[TEST] Combined events: {len(combined)} rows")

        update_session_stopped(conn)
        session = get_session_info(conn)
        print(f"[TEST] Session status: {session['status']}")

        conn.close()

    print("[TEST] All tests passed!")