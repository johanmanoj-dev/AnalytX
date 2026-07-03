# AnalytX

A Windows real-time process behavior monitoring tool. Watch any `.exe` or `.bat` while it runs and capture every file access, network connection, and child process spawn as it happens.

## How It Works

```
C++ ETW Engine  ──►  Named Pipe  ──►  Python Pipeline  ──►  SQLite  ──►  PyQt6 GUI
 (kernel events)      (JSON stream)    (parser/router)       (storage)    (live tables)
```

The native C++ engine subscribes to Windows ETW kernel providers (File, Network, Process), filters events by the target's PID tree, and streams them as JSON over a named pipe. A Python pipeline reads, translates, and stores events in SQLite while the PyQt6 GUI displays them in real time.

## Requirements

- **Windows 10+**
- **Python 3.10+**
- **Administrator privileges** (ETW requires elevation)
- **PyQt6** — `pip install -r requirements.txt`
- **MSVC** (only if rebuilding the engine) — Visual Studio Developer Command Prompt

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run as Administrator
cd app
python main.py
```

Browse to a target `.exe`, click **Start Monitoring**, and watch events flow in.

## Building the Engine

Only needed if you modify `monitor_engine.cpp`:

```bash
# From a Developer Command Prompt for VS
cd core
build.bat
```

## Project Structure

| Directory | Contents |
|-----------|----------|
| `app/` | Python application — UI, pipeline, database, launcher, reporter |
| `core/` | C++ ETW engine and build script |
| `data/sessions/` | Session SQLite databases (created at runtime) |
| `logs/` | Runtime log files |

## Event Types

| Category | Source | Captures |
|----------|--------|----------|
| **File** | Kernel-File | Create, Read, Write, Delete, Rename, Close |
| **Network** | Kernel-Network | TCP/UDP Send/Recv with IPs, ports, sizes |
| **Process** | Kernel-Process | Process Start/Stop, DLL loads, child tracking |
