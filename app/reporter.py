# reporter.py
# BehaviorMonitor - Report Generator
# Reads the completed session SQLite database and generates
# a clean, self-contained HTML report summarizing all monitored activity.

import os
import sqlite3
from datetime import datetime
from typing import Optional

import database as db


# ─────────────────────────────────────────────
#  Main Report Generator
# ─────────────────────────────────────────────

class Reporter:
    """
    Generates an HTML report from a completed monitoring session.

    Usage:
        reporter = Reporter(db_path="path/to/events.db")
        output_path = reporter.generate()
        print(f"Report saved to: {output_path}")
    """

    def __init__(self, db_path: str, output_path: str = None):
        """
        Args:
            db_path:     Path to the session's events.db file.
            output_path: Where to save the HTML report.
                         Defaults to report.html in the same folder as events.db.
        """
        self.db_path = db_path
        self.output_path = output_path or os.path.join(
            os.path.dirname(db_path), "report.html"
        )

    def generate(self) -> str:
        """
        Generate the HTML report.
        Returns the path to the saved report file.
        """
        conn = db.get_connection(self.db_path)

        try:
            session     = db.get_session_info(conn)
            stats       = db.get_summary_stats(conn)
            file_events = db.get_file_events(conn, limit=2000)
            net_events  = db.get_network_events(conn, limit=2000)
            proc_events = db.get_process_events(conn, limit=2000)
            unique_ips  = db.get_unique_ips(conn)
            unique_files = db.get_unique_files(conn)
        finally:
            conn.close()

        html = self._build_html(
            session, stats,
            file_events, net_events, proc_events,
            unique_ips, unique_files
        )

        with open(self.output_path, "w", encoding="utf-8") as f:
            f.write(html)

        print(f"[REPORTER] Report saved to: {self.output_path}")
        return self.output_path

    # ─────────────────────────────────────────
    #  HTML Builder
    # ─────────────────────────────────────────

    def _build_html(self, session, stats, file_events,
                    net_events, proc_events, unique_ips, unique_files) -> str:

        target_path  = session["target_path"]  if session else "Unknown"
        working_dir  = session["working_dir"]  if session else "Unknown"
        root_pid     = session["root_pid"]     if session else "Unknown"
        started_at   = session["started_at"]   if session else "Unknown"
        stopped_at   = session["stopped_at"]   if session else "Still running"
        status       = session["status"]       if session else "Unknown"

        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>BehaviorMonitor Report</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    font-family: 'Segoe UI', Arial, sans-serif;
    background: #0f1117;
    color: #e2e8f0;
    padding: 32px;
    font-size: 14px;
    line-height: 1.6;
  }}

  h1 {{
    font-size: 26px;
    font-weight: 700;
    color: #7dd3fc;
    margin-bottom: 4px;
  }}

  h2 {{
    font-size: 16px;
    font-weight: 600;
    color: #94a3b8;
    margin: 28px 0 12px 0;
    padding-bottom: 6px;
    border-bottom: 1px solid #1e293b;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }}

  .subtitle {{
    color: #64748b;
    font-size: 13px;
    margin-bottom: 28px;
  }}

  /* ── Summary Cards ── */
  .cards {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 16px;
    margin-bottom: 32px;
  }}

  .card {{
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 10px;
    padding: 18px 20px;
    text-align: center;
  }}

  .card .count {{
    font-size: 32px;
    font-weight: 700;
    color: #7dd3fc;
    display: block;
  }}

  .card .label {{
    font-size: 12px;
    color: #94a3b8;
    margin-top: 4px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }}

  /* ── Session Info Box ── */
  .info-box {{
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 10px;
    padding: 18px 24px;
    margin-bottom: 28px;
    display: grid;
    grid-template-columns: 140px 1fr;
    gap: 8px 0;
  }}

  .info-box .key {{
    color: #64748b;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    padding-top: 2px;
  }}

  .info-box .val {{
    color: #e2e8f0;
    word-break: break-all;
  }}

  /* ── Tables ── */
  .table-wrap {{
    overflow-x: auto;
    margin-bottom: 36px;
    border-radius: 10px;
    border: 1px solid #334155;
  }}

  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }}

  thead tr {{
    background: #1e293b;
  }}

  thead th {{
    padding: 10px 14px;
    text-align: left;
    color: #94a3b8;
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    white-space: nowrap;
  }}

  tbody tr {{
    border-top: 1px solid #1e293b;
    transition: background 0.1s;
  }}

  tbody tr:hover {{
    background: #1e293b;
  }}

  tbody td {{
    padding: 8px 14px;
    color: #cbd5e1;
    max-width: 480px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }}

  /* ── Badges ── */
  .badge {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }}

  .badge-file    {{ background: #1e3a5f; color: #7dd3fc; }}
  .badge-network {{ background: #1e3a2f; color: #6ee7b7; }}
  .badge-process {{ background: #3a1e3f; color: #d8b4fe; }}
  .badge-create  {{ background: #1e3a5f; color: #7dd3fc; }}
  .badge-write   {{ background: #3a2e1e; color: #fbbf24; }}
  .badge-read    {{ background: #1e2e3a; color: #94a3b8; }}
  .badge-delete  {{ background: #3a1e1e; color: #f87171; }}
  .badge-connect {{ background: #1e3a2f; color: #6ee7b7; }}
  .badge-send    {{ background: #1e3a2f; color: #34d399; }}
  .badge-receive {{ background: #1e2e3a; color: #60a5fa; }}

  .pid {{
    font-family: monospace;
    color: #94a3b8;
    font-size: 12px;
  }}

  .path {{
    font-family: monospace;
    font-size: 12px;
    color: #7dd3fc;
  }}

  .ip {{
    font-family: monospace;
    color: #6ee7b7;
  }}

  .ts {{
    color: #475569;
    font-size: 11px;
    font-family: monospace;
    white-space: nowrap;
  }}

  .no-events {{
    padding: 24px;
    text-align: center;
    color: #475569;
    font-style: italic;
  }}

  /* ── Footer ── */
  .footer {{
    margin-top: 48px;
    padding-top: 16px;
    border-top: 1px solid #1e293b;
    color: #475569;
    font-size: 12px;
    text-align: center;
  }}
</style>
</head>
<body>

<h1>BehaviorMonitor Report</h1>
<p class="subtitle">Generated {generated_at}</p>

<!-- Session Info -->
<h2>Session Information</h2>
<div class="info-box">
  <span class="key">Target</span>
  <span class="val path">{self._esc(target_path)}</span>

  <span class="key">Working Dir</span>
  <span class="val path">{self._esc(working_dir)}</span>

  <span class="key">Root PID</span>
  <span class="val pid">{root_pid}</span>

  <span class="key">Started</span>
  <span class="val">{self._esc(str(started_at))}</span>

  <span class="key">Stopped</span>
  <span class="val">{self._esc(str(stopped_at))}</span>

  <span class="key">Status</span>
  <span class="val">{self._esc(str(status))}</span>
</div>

<!-- Summary Cards -->
<h2>Summary</h2>
<div class="cards">
  <div class="card">
    <span class="count">{stats.get('total_events', 0)}</span>
    <span class="label">Total Events</span>
  </div>
  <div class="card">
    <span class="count">{stats.get('file_events', 0)}</span>
    <span class="label">File Events</span>
  </div>
  <div class="card">
    <span class="count">{stats.get('network_events', 0)}</span>
    <span class="label">Network Events</span>
  </div>
  <div class="card">
    <span class="count">{stats.get('process_events', 0)}</span>
    <span class="label">Process Events</span>
  </div>
  <div class="card">
    <span class="count">{stats.get('unique_files', 0)}</span>
    <span class="label">Unique Files</span>
  </div>
  <div class="card">
    <span class="count">{stats.get('unique_ips', 0)}</span>
    <span class="label">Unique IPs</span>
  </div>
</div>

<!-- Unique IPs -->
<h2>Network — Unique Destinations</h2>
{self._build_ip_table(unique_ips)}

<!-- Unique Files -->
<h2>File System — Unique Paths Accessed</h2>
{self._build_unique_files_table(unique_files)}

<!-- File Events -->
<h2>File Events ({len(file_events)} shown)</h2>
{self._build_file_table(file_events)}

<!-- Network Events -->
<h2>Network Events ({len(net_events)} shown)</h2>
{self._build_network_table(net_events)}

<!-- Process Events -->
<h2>Process Events ({len(proc_events)} shown)</h2>
{self._build_process_table(proc_events)}

<div class="footer">
  BehaviorMonitor &nbsp;|&nbsp; Report generated {generated_at}
</div>

</body>
</html>"""

    # ─────────────────────────────────────────
    #  Table Builders
    # ─────────────────────────────────────────

    def _build_ip_table(self, rows) -> str:
        if not rows:
            return '<p class="no-events">No network activity recorded.</p>'

        html = '<div class="table-wrap"><table>'
        html += "<thead><tr><th>Destination IP</th><th>Hit Count</th></tr></thead><tbody>"
        for row in rows:
            ip   = self._esc(str(row["dst_ip"]))
            hits = row["hits"]
            html += f'<tr><td class="ip">{ip}</td><td>{hits}</td></tr>'
        html += "</tbody></table></div>"
        return html

    def _build_unique_files_table(self, rows) -> str:
        if not rows:
            return '<p class="no-events">No file activity recorded.</p>'

        html = '<div class="table-wrap"><table>'
        html += "<thead><tr><th>File Path</th><th>Access Count</th><th>Operations</th></tr></thead><tbody>"
        for row in rows:
            path = self._esc(str(row["file_path"]))
            hits = row["hits"]
            ops  = self._esc(str(row["operations"] or ""))
            html += f'<tr><td class="path" title="{path}">{path}</td><td>{hits}</td><td>{ops}</td></tr>'
        html += "</tbody></table></div>"
        return html

    def _build_file_table(self, rows) -> str:
        if not rows:
            return '<p class="no-events">No file events recorded.</p>'

        html = '<div class="table-wrap"><table>'
        html += "<thead><tr><th>Timestamp</th><th>PID</th><th>Operation</th><th>File Path</th><th>IO Size</th></tr></thead><tbody>"
        for row in rows:
            ts      = self._esc(str(row["timestamp"]))
            pid     = row["pid"]
            op      = self._esc(str(row["operation"]))
            path    = self._esc(str(row["file_path"]))
            io_size = row["io_size"]
            badge   = self._op_badge(op)
            html += (
                f'<tr>'
                f'<td class="ts">{ts}</td>'
                f'<td class="pid">{pid}</td>'
                f'<td>{badge}</td>'
                f'<td class="path" title="{path}">{path}</td>'
                f'<td>{io_size}</td>'
                f'</tr>'
            )
        html += "</tbody></table></div>"
        return html

    def _build_network_table(self, rows) -> str:
        if not rows:
            return '<p class="no-events">No network events recorded.</p>'

        html = '<div class="table-wrap"><table>'
        html += "<thead><tr><th>Timestamp</th><th>PID</th><th>Operation</th><th>Detail</th><th>Dest IP</th><th>Port</th><th>Size</th></tr></thead><tbody>"
        for row in rows:
            ts       = self._esc(str(row["timestamp"]))
            pid      = row["pid"]
            op       = self._esc(str(row["operation"]))
            detail   = self._esc(str(row["detail"]))
            dst_ip   = self._esc(str(row["dst_ip"] or ""))
            dst_port = row["dst_port"]
            size     = row["size"]
            badge    = self._op_badge(op, "network")
            html += (
                f'<tr>'
                f'<td class="ts">{ts}</td>'
                f'<td class="pid">{pid}</td>'
                f'<td>{badge}</td>'
                f'<td title="{detail}">{detail}</td>'
                f'<td class="ip">{dst_ip}</td>'
                f'<td>{dst_port}</td>'
                f'<td>{size}</td>'
                f'</tr>'
            )
        html += "</tbody></table></div>"
        return html

    def _build_process_table(self, rows) -> str:
        if not rows:
            return '<p class="no-events">No process events recorded.</p>'

        html = '<div class="table-wrap"><table>'
        html += "<thead><tr><th>Timestamp</th><th>PID</th><th>Operation</th><th>Detail</th><th>Child PID</th><th>Exit Code</th></tr></thead><tbody>"
        for row in rows:
            ts        = self._esc(str(row["timestamp"]))
            pid       = row["pid"]
            op        = self._esc(str(row["operation"]))
            detail    = self._esc(str(row["detail"] or ""))
            child_pid = row["child_pid"] if row["child_pid"] else ""
            exit_code = row["exit_code"] if row["exit_code"] is not None else ""
            badge     = self._op_badge(op, "process")
            html += (
                f'<tr>'
                f'<td class="ts">{ts}</td>'
                f'<td class="pid">{pid}</td>'
                f'<td>{badge}</td>'
                f'<td>{detail}</td>'
                f'<td class="pid">{child_pid}</td>'
                f'<td>{exit_code}</td>'
                f'</tr>'
            )
        html += "</tbody></table></div>"
        return html

    # ─────────────────────────────────────────
    #  Helpers
    # ─────────────────────────────────────────

    def _op_badge(self, operation: str, category: str = "file") -> str:
        """Returns a colored HTML badge for an operation type."""
        op_lower = operation.lower()
        if "create" in op_lower:
            cls = "badge-create"
        elif "write" in op_lower:
            cls = "badge-write"
        elif "read" in op_lower or "query" in op_lower:
            cls = "badge-read"
        elif "delete" in op_lower or "close" in op_lower:
            cls = "badge-delete"
        elif "connect" in op_lower:
            cls = "badge-connect"
        elif "send" in op_lower:
            cls = "badge-send"
        elif "receive" in op_lower or "recv" in op_lower:
            cls = "badge-receive"
        elif category == "network":
            cls = "badge-network"
        elif category == "process":
            cls = "badge-process"
        else:
            cls = "badge-file"
        return f'<span class="badge {cls}">{operation}</span>'

    def _esc(self, text: str) -> str:
        """Escape HTML special characters to prevent broken output."""
        return (text
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;"))


# ─────────────────────────────────────────────
#  Convenience function — called by main.py / UI
# ─────────────────────────────────────────────

def generate_report(db_path: str, output_path: str = None) -> str:
    """
    Shortcut to generate a report without instantiating Reporter directly.
    Returns the path to the saved HTML file.
    """
    reporter = Reporter(db_path=db_path, output_path=output_path)
    return reporter.generate()


# ─────────────────────────────────────────────
#  Self-test — run reporter.py directly
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import tempfile

    print("[TEST] Reporter self-test...")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = db.get_db_path(tmpdir)
        conn    = db.get_connection(db_path)
        db.create_tables(conn)

        # Insert dummy session and events
        db.insert_session(conn, "C:\\TestApp\\app.exe", "C:\\TestApp\\", 1234)
        db.insert_file_event(conn, "2025-02-22 10:00:00.000", 1234, "Create", "C:\\TestApp\\config.ini", 512)
        db.insert_file_event(conn, "2025-02-22 10:00:01.000", 1234, "Write",  "C:\\TestApp\\log.txt",    256)
        db.insert_file_event(conn, "2025-02-22 10:00:02.000", 1234, "Read",   "C:\\TestApp\\data.db",   1024)
        db.insert_file_event(conn, "2025-02-22 10:00:03.000", 1234, "Delete", "C:\\TestApp\\temp.tmp",     0)
        db.insert_network_event(conn, "2025-02-22 10:00:04.000", 1234, "Connect",
                                "192.168.1.5:54321 -> 93.184.216.34:443",
                                "93.184.216.34", 443, 0)
        db.insert_network_event(conn, "2025-02-22 10:00:05.000", 1234, "Send",
                                "192.168.1.5:54321 -> 93.184.216.34:443",
                                "93.184.216.34", 443, 1024)
        db.insert_process_event(conn, "2025-02-22 10:00:06.000", 1234,
                                "ChildProcessStart", "cmd.exe",
                                child_pid=5678, parent_pid=1234)
        db.insert_control_event(conn, "2025-02-22 10:00:00.000",
                                "TargetLaunched", 1234, "C:\\TestApp\\app.exe")
        db.update_session_stopped(conn)
        conn.close()

        # Generate report
        report_path = os.path.join(tmpdir, "report.html")
        saved_path  = generate_report(db_path, report_path)

        print(f"[TEST] Report generated: {saved_path}")
        print(f"[TEST] File size: {os.path.getsize(saved_path)} bytes")
        print("[TEST] Open the file in a browser to preview it.")

        # Copy to cwd for easy viewing
        import shutil
        local_copy = os.path.join(os.getcwd(), "test_report.html")
        shutil.copy(saved_path, local_copy)
        print(f"[TEST] Copied to: {local_copy}")