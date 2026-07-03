# AnalytX — Full Project Blueprint & Deep Analysis

> **Analysis Date:** July 3, 2026  
> **Analyzed By:** Automated Deep-Dive Engine  
> **Repository:** `AnalytX` (2 commits, authored Feb 22, 2026)  
> **README Note from Author:** *"have errors too lazy to fiz em!"*

---

## 1. What Is This Program?

**AnalytX** (internally still referenced as **"BehaviorMonitor"**) is a **Windows-only real-time process behavior monitoring tool**. It watches a target executable (.exe / .bat / .cmd) while it runs and records every file access, network connection, and child process spawn in real time.

### Core Concept
```
┌──────────────┐    Named Pipe     ┌──────────────┐    SQLite     ┌──────────────┐
│  C++ Engine  │ ───────────────── │   Python     │ ────────────  │  PyQt6 GUI   │
│ (ETW Tracing)│   JSON events     │  Pipeline    │   DB writes   │  Live Tables │
│  Admin-only  │                   │  (Thread)    │               │  + Reports   │
└──────────────┘                   └──────────────┘               └──────────────┘
```

| Layer | Technology | Role |
|-------|-----------|------|
| **Native Engine** | C++ / Win32 / ETW | Subscribes to Windows kernel telemetry providers (File, Network, Process), filters events by tracked PIDs, and streams JSON over a named pipe |
| **Pipeline** | Python 3.10+ / ctypes | Connects to the named pipe, parses newline-delimited JSON, routes events to SQLite via `database.py` |
| **Database** | SQLite (WAL mode) | Stores all events in category-specific tables with indexes |
| **UI** | PyQt6 | Dark-themed professional desktop GUI with live event tables, metric cards, search/filter, autoscroll, session management |
| **Reporter** | Python → HTML | Generates self-contained dark-themed HTML reports from session data |
| **Launcher** | Python / subprocess | Orchestrates engine startup, pipe connection, and session lifecycle |

### Supported Event Types

| Category | Source Provider | Events Captured |
|----------|----------------|-----------------|
| **File System** | `Microsoft-Windows-Kernel-File` | Create, Cleanup, Close, Read, Write, SetInfo, Delete, Rename |
| **Network** | `Microsoft-Windows-Kernel-Network` | TCP/UDP Send/Recv with src/dst IP:port and sizes |
| **Process** | `Microsoft-Windows-Kernel-Process` | Process Start (with cmdline), Process Stop, DLL/Image Load |

---

## 2. Project Structure

```
AnalytX/
├── README.md               # 1 line — "have errors too lazy to fiz em!"
├── blueprint.md            # ← This file
├── app/                    # Python application layer
│   ├── main.py             # Entry point — env setup, dependency checks, launch
│   ├── ui.py               # PyQt6 GUI (1,362 lines) — full dark-themed interface
│   ├── launcher.py         # Engine subprocess manager + pipeline orchestrator
│   ├── pipeline.py         # Named pipe reader → JSON parser → DB writer
│   ├── reporter.py         # HTML report generator from SQLite data
│   ├── database.py         # SQLite schema, inserts, queries
│   └── __pycache__/        # Compiled bytecodes (Python 3.10)
├── core/                   # Native engine layer
│   ├── monitor_engine.cpp  # C++ ETW monitor (662 lines)
│   ├── monitor_engine.exe  # Pre-compiled binary (138 KB)
│   ├── monitor_engine.obj  # Object file from last build
│   └── build.bat           # MSVC cl.exe build script
├── data/
│   └── sessions/           # 27 session folders from dev testing (all Feb 22)
└── logs/                   # 16 log files (all empty — 0 bytes each)
```

### Lines of Code Summary

| File | Lines | Bytes | Language |
|------|------:|------:|----------|
| `ui.py` | 1,362 | 48,689 | Python |
| `monitor_engine.cpp` | 662 | 26,326 | C++ |
| `reporter.py` | 587 | 19,785 | Python |
| `pipeline.py` | 424 | 15,591 | Python |
| `database.py` | 367 | 15,940 | Python |
| `launcher.py` | 368 | 14,970 | Python |
| `main.py` | 220 | 7,807 | Python |
| `build.bat` | 33 | 843 | Batch |
| **Total** | **4,023** | **~150 KB** | — |

---

## 3. Current Status Assessment

### Overall Verdict: 🟡 PARTIALLY BUILDABLE — NOT PRODUCTION-READY

The project has a solid architectural foundation with well-structured, well-commented code. However, it contains **critical data contract mismatches** between the C++ engine and Python pipeline that will cause **100% event loss at runtime**. The code compiles/runs but events will never flow end-to-end correctly.

| Aspect | Status | Details |
|--------|--------|---------|
| **C++ Engine Compilation** | ✅ Works | Pre-compiled .exe exists; build.bat works with VS Dev Prompt |
| **Python Dependencies** | ⚠️ Partial | PyQt6 required but no `requirements.txt` exists |
| **Application Launch** | ✅ Works | `main.py` starts, dependency checks pass, UI appears |
| **GUI Rendering** | ✅ Works | Professional dark UI renders correctly |
| **Engine → Pipe → Pipeline** | ❌ BROKEN | Critical JSON field mismatch (see Section 4) |
| **Pipeline → Database** | ❌ BROKEN | Data never arrives due to above mismatch |
| **Report Generation** | ✅ Works | HTML reporter works correctly with valid data |
| **End-to-End Monitoring** | ❌ BROKEN | No events will ever appear in the GUI |

---

## 4. Critical Issues (Show-Stoppers)

### 🔴 CRITICAL #1: JSON Field Name Mismatch — Engine vs Pipeline

This is the **fatal flaw** that makes the entire application non-functional end-to-end.

**The C++ engine emits events with these JSON fields:**
```json
{"type":"FILE",    "time":"...", "pid":1234, "operation":"Create", "path":"C:\\..."}
{"type":"NETWORK", "time":"...", "pid":1234, "protocol":"TCP", "direction":"Send", "src":"...", "dst":"...", "size":"..."}
{"type":"PROCESS", "time":"...", "pid":1234, "event":"Start", "new_pid":"5678", "image":"...", "cmdline":"..."}
{"type":"LAUNCHED","pid":1234}
{"type":"SHUTDOWN"}
{"type":"CHILD_PID","pid":5678}
```

**But the Python pipeline expects these fields:**
```python
category  = event.get("category", "")    # Engine sends "type", NOT "category"
operation = event.get("operation", "")    # Engine sends "operation" for file, but "event"/"direction" for others
detail    = event.get("detail", "")      # Engine sends "path", "image", "cmdline" etc.
timestamp = event.get("timestamp", ...)  # Engine sends "time", NOT "timestamp"
```

**Result:** Every single event parsed by the pipeline will have `category=""`, hit the `else` branch ("Unknown category"), and be **silently discarded**. Zero events will ever reach the database or UI.

#### Specific Field Mismatches:

| What Engine Sends | What Pipeline Expects | Impact |
|---|---|---|
| `"type": "FILE"` | `event.get("category")` | Category always empty → event dropped |
| `"time": "2026-..."` | `event.get("timestamp")` | Falls back to `datetime.now()`, but event already dropped |
| `"path": "C:\\..."` | `event.get("detail")` | Never read |
| `"event": "Start"` (process) | `event.get("operation")` | Wrong field name |
| `"direction": "Send"` (network) | `event.get("operation")` | Wrong field name |
| `"src": "ip:port"` | `event.get("detail")` | Never read |
| `"new_pid": "5678"` | `event.get("child_pid")` | Wrong field name |
| `"image": "..."` | `event.get("detail")` | Wrong field name |

---

### 🔴 CRITICAL #2: Engine Requires Administrator — No UAC Elevation Logic

ETW (Event Tracing for Windows) **requires Administrator privileges**. The engine will silently fail or crash if launched without elevation:
- `StartTrace()` returns `ERROR_ACCESS_DENIED` (error 5)
- The Python launcher (`launcher.py`) calls `subprocess.Popen()` without requesting elevation
- No UAC prompt is triggered
- No user-facing error message explains the requirement

**Current behavior:** Engine starts → ETW session fails → events never generated → user sees empty tables with no error explanation.

---

### 🔴 CRITICAL #3: Naming Inconsistency — Project Identity Crisis

The project has **two names** used inconsistently:

| Location | Name Used |
|----------|-----------|
| Repository folder | `AnalytX` |
| `ui.py` header comment | `AnalytX` |
| Window title | `AnalytX` |
| `main.py` header comment | `BehaviorMonitor` |
| `pipeline.py` header comment | `BehaviorMonitor` |
| `database.py` header comment | `BehaviorMonitor` |
| `launcher.py` header comment | `BehaviorMonitor` |
| `reporter.py` header comment | `BehaviorMonitor` |
| `monitor_engine.cpp` | `BehaviorMonitor` |
| Error messages | `BehaviorMonitor` |
| Application name (`setApplicationName`) | `BehaviorMonitor` |
| HTML report title | `BehaviorMonitor Report` |
| ETW session name | `BehaviorMonitorSession` |
| Named pipe name | `BehaviorMonitorPipe` |

This suggests the project was **renamed from BehaviorMonitor to AnalytX** but the rename was only done on the folder and the UI window title — everything else still says BehaviorMonitor.

---

## 5. Major Issues (Bugs & Design Problems)

### 🟠 MAJOR #1: Per-Event SQLite Commits — Catastrophic Performance

Every single event triggers an individual `conn.commit()` call in `database.py`:

```python
def insert_file_event(...):
    conn.execute("INSERT INTO file_events ...")
    conn.commit()  # ← called on EVERY event
```

Under high-throughput monitoring (file I/O-heavy applications produce thousands of events per second), this creates a massive I/O bottleneck. SQLite performance with individual commits drops to ~50-100 inserts/second vs. 100,000+ with batched transactions.

**Fix needed:** Batch inserts into periodic transactions (e.g., commit every 100 events or every 500ms).

---

### 🟠 MAJOR #2: No `requirements.txt` or `pyproject.toml`

The project has **zero dependency management**. Required packages:
- `PyQt6` (the only external Python dependency)

No `requirements.txt`, `setup.py`, `pyproject.toml`, or `Pipfile` exists. Anyone cloning this repo has to discover dependencies by reading import statements.

---

### 🟠 MAJOR #3: Empty Log Files — Logging Setup Race Condition

All 16 log files in `logs/` are **0 bytes** (empty). The logging setup in `main.py` runs after dependency checks, but the log output format suggests events are logged to `stdout` via `print()` statements rather than the configured `logging` module. Most modules use `print(f"[MODULE]...")` instead of `logging.info(...)`.

---

### 🟠 MAJOR #4: 27 Orphaned Session Folders — No Cleanup

The `data/sessions/` directory contains **27 session folders** from a single day of development testing (Feb 22, 2026). Many were created within seconds of each other (e.g., `16-46-50` through `16-46-57`). There is:
- No session cleanup mechanism
- No session browser in the UI
- No disk usage warnings
- No automatic purging of old sessions

---

### 🟠 MAJOR #5: Thread Safety — `_event_callback` Called from Wrong Thread

The pipeline runs on a background thread and calls `self._event_callback()` directly. While the `UIUpdater` (a `QThread` subclass) uses `pyqtSignal` to marshal events to the main thread, the pipeline bypasses this by calling the callback directly from its thread. This creates a **race condition** with Qt's thread-safety model.

The `UIUpdater.emit_event()` method is designed as the bridge, but the pipeline calls whatever callback is set — if `Launcher.set_event_callback()` is given a direct function reference instead of the `UIUpdater.emit_event` wrapper, it will crash intermittently.

Currently the code wires this correctly (`self._launcher.set_event_callback(self._updater.emit_event)`), but it's fragile.

---

### 🟠 MAJOR #6: No `.gitignore`

The repository has committed:
- `__pycache__/` (compiled bytecodes)
- `monitor_engine.exe` (138 KB binary)
- `monitor_engine.obj` (74 KB object file)
- `logs/` directory with empty log files
- `data/sessions/` with 27 test session folders

---

## 6. Minor Issues & Improvements Needed

### 🟡 MINOR #1: No Error Dialogs in GUI for Failed Monitoring Start
When `_begin_monitoring()` fails, the error is shown in the status chip (truncated to 60 chars). A proper error dialog should be shown.

### 🟡 MINOR #2: `monitor_engine.cpp` Uses `CoCreateGuid()` Without Including `<objbase.h>`
It links `ole32.lib` in `build.bat` but relies on an implicit declaration. This may cause warnings or undefined behavior depending on the SDK version.

### 🟡 MINOR #3: Target PID Never Updated in Session Info
When monitoring starts, the session info label shows `PID: ...`. It's only updated when a `TargetLaunched` control event arrives — but due to the JSON mismatch, this event is never received.

### 🟡 MINOR #4: `UIUpdater` Subclasses `QThread` But Never Starts
`UIUpdater` extends `QThread` but is only used for its signal. `run()` is never implemented or called. It should be a plain `QObject` instead.

### 🟡 MINOR #5: Hardcoded Version Strings
Version "1.0.0" appears in `main.py` (`setApplicationVersion`) and "Version 1.0" in `ui.py`. These are inconsistent and hardcoded.

### 🟡 MINOR #6: No Window Icon
The application doesn't set a window icon (only a Unicode shield emoji in the header bar).

### 🟡 MINOR #7: `reporter.py` HTML Has Potential XSS
While `_esc()` handles basic HTML escaping, the reporter embeds user-controlled file paths and command lines into HTML. The escaping is sufficient for display but doesn't handle all edge cases (e.g., event attribute injection through `title="..."` attributes).

### 🟡 MINOR #8: `build.bat` Tells User to "Copy" the `.exe`
Line 27: `echo [Build] Copy monitor_engine.exe to BehaviorMonitor\core\` — but the build already outputs to the same directory. This message is misleading.

---

## 7. Architecture Quality Assessment

### Strengths ✅
| Aspect | Assessment |
|--------|------------|
| **Code Organization** | Excellent — clear separation of concerns across 6 modules |
| **Code Documentation** | Very good — comprehensive header comments, docstrings, inline explanations |
| **Self-Test Scripts** | Good — `database.py`, `pipeline.py`, `reporter.py`, `launcher.py` all have `if __name__ == "__main__"` self-tests |
| **UI Design** | Professional — dark theme, custom color palette, polished CSS-like stylesheet, metric cards, badge system, modal dialogs |
| **Error Handling** | Decent — fallback error display, graceful shutdown in `closeEvent`, `CtrlHandler` in C++ engine |
| **Database Design** | Solid — proper WAL mode, indexes, parameterized queries, `Row` factory |
| **Named Pipe IPC** | Well-implemented — proper message framing with newline-delimited JSON |
| **C++ ETW Integration** | Technically sound — correct use of `EnableTraceEx2`, `TdhGetProperty`, child PID tracking |

### Weaknesses ❌
| Aspect | Assessment |
|--------|------------|
| **Data Contract** | Fatally broken — C++ and Python disagree on JSON schema |
| **Dependency Management** | Non-existent — no requirements file |
| **Testing** | No automated tests — only manual self-tests |
| **Logging** | Broken — all log files empty, modules use print instead of logging |
| **Build System** | Minimal — batch file only, no CI, no build verification |
| **Documentation** | Non-existent README, no user guide |
| **Privilege Management** | Missing — no UAC handling for admin requirement |
| **Session Management** | No cleanup, no browsing, accumulates folders |

---

## 8. Technology Dependencies

### Runtime Requirements
| Dependency | Version | Required By | Installation |
|-----------|---------|-------------|-------------|
| Windows OS | 10+ | ETW APIs | N/A |
| Python | 3.10+ | `match` statements, type hints | python.org |
| PyQt6 | Latest | GUI | `pip install PyQt6` |
| SQLite3 | Built-in | Database | Included with Python |
| MSVC C++ Compiler | VS 2019+ | Engine build only | Visual Studio |
| Windows SDK | 10.0+ | ETW headers/libs | Visual Studio |
| Administrator Privileges | — | ETW session | Run as Admin |

### Build Requirements
- Visual Studio Developer Command Prompt (for `cl.exe`)
- Libraries: `tdh.lib`, `advapi32.lib`, `ws2_32.lib`, `shlwapi.lib`, `ole32.lib`

---

## 9. What Would It Take to Make This Work?

### Phase 1: Fix Show-Stoppers (Est. ~4-6 hours)

| # | Task | Difficulty |
|---|------|-----------|
| 1 | **Fix JSON contract**: Either update `pipeline.py` to read `type`/`time`/`path`/`event` OR update `monitor_engine.cpp` to emit `category`/`timestamp`/`detail`/`operation` | Medium |
| 2 | **Add admin elevation**: Request UAC elevation in `launcher.py` before starting the engine | Easy |
| 3 | **Create `requirements.txt`**: Single line — `PyQt6` | Trivial |
| 4 | **Rename all BehaviorMonitor references to AnalytX** (or vice versa) | Easy |

### Phase 2: Fix Major Issues (Est. ~3-4 hours)

| # | Task | Difficulty |
|---|------|-----------|
| 5 | Batch SQLite inserts for performance | Medium |
| 6 | Add `.gitignore` for pycache, exe, obj, logs, sessions | Trivial |
| 7 | Fix logging — use `logging` module consistently | Easy |
| 8 | Add session cleanup / disk management | Medium |
| 9 | Fix `UIUpdater` to be `QObject` instead of `QThread` | Trivial |

### Phase 3: Polish (Est. ~4-6 hours)

| # | Task | Difficulty |
|---|------|-----------|
| 10 | Write proper README with setup instructions | Easy |
| 11 | Add error dialogs in GUI for failure cases | Easy |
| 12 | Add session browser to load past sessions | Medium |
| 13 | Add window icon and branding | Easy |
| 14 | Harmonize version strings | Trivial |
| 15 | Add basic unit tests | Medium |

---

## 10. Security Considerations

| Concern | Status | Details |
|---------|--------|---------|
| **Runs as Admin** | ⚠️ Risk | ETW requires admin — the entire app runs elevated, including the UI |
| **Named Pipe Security** | ⚠️ Risk | Pipe created with `NULL` security descriptor — any local process can connect |
| **SQL Injection** | ✅ Safe | All queries use parameterized `?` placeholders |
| **HTML XSS in Reports** | ⚠️ Low Risk | Basic escaping exists but not comprehensive |
| **No Code Signing** | ⚠️ Note | `monitor_engine.exe` is unsigned — may trigger AV warnings |
| **Process Spawning** | ✅ Reasonable | Engine only launches the user-selected target, no arbitrary execution |

---

## 11. Verdict Summary

```
┌──────────────────────────────────────────────────────────────┐
│                     PROJECT STATUS CARD                       │
├──────────────────────────────────────────────────────────────┤
│  Architecture:    ████████░░  8/10  — Well-designed          │
│  Code Quality:    ███████░░░  7/10  — Clean, well-commented  │
│  Functionality:   ██░░░░░░░░  2/10  — Broken data contract   │
│  Build System:    ████░░░░░░  4/10  — Minimal, no CI         │
│  Documentation:   █░░░░░░░░░  1/10  — Essentially none       │
│  Testing:         █░░░░░░░░░  1/10  — No automated tests     │
│  UI/UX:           █████████░  9/10  — Professional & polished │
│  Deployment:      ██░░░░░░░░  2/10  — No installer, no deps  │
├──────────────────────────────────────────────────────────────┤
│  OVERALL:         ████░░░░░░  4/10                           │
│                                                              │
│  Buildable:       YES — compiles and launches                │
│  Functional:      NO  — events never flow end-to-end         │
│  Production-Ready: NO — multiple critical issues              │
│                                                              │
│  Estimated effort to reach MVP:  ~12-16 hours                │
│  Estimated effort to production: ~40-60 hours                │
└──────────────────────────────────────────────────────────────┘
```

---

## 12. Recommendation

The project represents **strong foundational work** — the architecture is well-thought-out, the code is clean and well-documented, and the UI is impressively polished. The author clearly understands ETW, named pipes, PyQt6, and SQLite well.

However, the **single most critical bug** (JSON field mismatch between C++ engine and Python pipeline) means the application **literally cannot function**. This appears to be a case where the C++ engine and Python pipeline were developed in parallel (or the engine was refactored) without updating the other side to match.

**Recommended next step:** Fix the JSON data contract mismatch. This one change would make the application functional for the first time.
