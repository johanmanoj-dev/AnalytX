// monitor_engine.cpp
// Core monitoring engine for BehaviorMonitor
// Handles: CreateProcess (with correct working dir), ETW session, Named Pipe output
//
// Build: See build.bat
// Usage: monitor_engine.exe <target_exe_path> <working_directory> <pipe_name>
// Example: monitor_engine.exe "C:\App\app.exe" "C:\App" "\\\\.\\pipe\\BehaviorMonitorPipe"

#define UNICODE
#define _UNICODE
#define INITGUID

#include <windows.h>
#include <evntrace.h>
#include <evntcons.h>
#include <tdh.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <tlhelp32.h>
#include <shlwapi.h>
#include <strsafe.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#pragma comment(lib, "tdh.lib")
#pragma comment(lib, "advapi32.lib")
#pragma comment(lib, "ws2_32.lib")
#pragma comment(lib, "shlwapi.lib")

// ─────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────

#define MAX_EVENT_SIZE      4096
#define PIPE_BUFFER_SIZE    65536
#define SESSION_NAME        L"BehaviorMonitorSession"

// ETW Provider GUIDs we subscribe to
// Microsoft-Windows-Kernel-File
static const GUID FileProviderGuid = {
    0xEDD08927, 0x9CC4, 0x4E65,
    { 0xB9, 0x70, 0xC2, 0x56, 0x0F, 0xB5, 0xAD, 0xAF }
};

// Microsoft-Windows-Kernel-Network
static const GUID NetworkProviderGuid = {
    0x7DD42A49, 0x5329, 0x4832,
    { 0x8C, 0xA4, 0xD1, 0xB7, 0x38, 0x27, 0xC5, 0xFD }
};

// Microsoft-Windows-Kernel-Process
static const GUID ProcessProviderGuid = {
    0x22FB2CD6, 0x0E7B, 0x422B,
    { 0xA0, 0xC7, 0x2F, 0xAD, 0x1F, 0xD0, 0xE7, 0x16 }
};

// ─────────────────────────────────────────────
// Global State
// ─────────────────────────────────────────────

static HANDLE          g_hPipe         = INVALID_HANDLE_VALUE;
static TRACEHANDLE     g_hSession      = 0;
static TRACEHANDLE     g_hTrace        = 0;
static DWORD           g_TargetPID     = 0;
static BOOL            g_Running       = TRUE;

// Tracked PIDs (target + children) - simple array for first version
#define MAX_TRACKED_PIDS 256
static DWORD g_TrackedPIDs[MAX_TRACKED_PIDS];
static int   g_TrackedCount = 0;

// ─────────────────────────────────────────────
// Utility: Check if a PID is in our watch list
// ─────────────────────────────────────────────

static BOOL IsTrackedPID(DWORD pid) {
    for (int i = 0; i < g_TrackedCount; i++) {
        if (g_TrackedPIDs[i] == pid) return TRUE;
    }
    return FALSE;
}

static void AddTrackedPID(DWORD pid) {
    if (g_TrackedCount < MAX_TRACKED_PIDS && !IsTrackedPID(pid)) {
        g_TrackedPIDs[g_TrackedCount++] = pid;
        // Notify pipeline that a new child PID is being tracked
        char msg[128];
        sprintf_s(msg, sizeof(msg),
            "{\"type\":\"CHILD_PID\",\"pid\":%lu}\n", pid);
        DWORD written = 0;
        WriteFile(g_hPipe, msg, (DWORD)strlen(msg), &written, NULL);
    }
}

// ─────────────────────────────────────────────
// Utility: Get current timestamp string
// ─────────────────────────────────────────────

static void GetTimestamp(char* buf, size_t bufSize) {
    SYSTEMTIME st;
    GetLocalTime(&st);
    sprintf_s(buf, bufSize,
        "%04d-%02d-%02d %02d:%02d:%02d.%03d",
        st.wYear, st.wMonth, st.wDay,
        st.wHour, st.wMinute, st.wSecond, st.wMilliseconds);
}

// ─────────────────────────────────────────────
// Utility: Escape a string for JSON (basic)
// ─────────────────────────────────────────────

static void JsonEscape(const char* src, char* dst, size_t dstSize) {
    size_t j = 0;
    for (size_t i = 0; src[i] && j + 2 < dstSize; i++) {
        unsigned char c = (unsigned char)src[i];
        if (c == '"' || c == '\\') {
            if (j + 3 < dstSize) { dst[j++] = '\\'; dst[j++] = c; }
        } else if (c < 0x20) {
            // skip control chars
        } else {
            dst[j++] = c;
        }
    }
    dst[j] = '\0';
}

// ─────────────────────────────────────────────
// Send JSON event line to named pipe
// ─────────────────────────────────────────────

static void SendEvent(const char* jsonLine) {
    if (g_hPipe == INVALID_HANDLE_VALUE) return;
    DWORD written = 0;
    // Each event is one JSON line terminated by newline
    WriteFile(g_hPipe, jsonLine, (DWORD)strlen(jsonLine), &written, NULL);
    WriteFile(g_hPipe, "\n", 1, &written, NULL);
}

// ─────────────────────────────────────────────
// ETW Property Extraction Helper
// ─────────────────────────────────────────────

static BOOL GetPropertyString(
    PEVENT_RECORD pEvent,
    PTRACE_EVENT_INFO pInfo,
    ULONG propIndex,
    char* outBuf,
    size_t outBufSize)
{
    PROPERTY_DATA_DESCRIPTOR desc = {0};
    desc.PropertyName = (ULONGLONG)((PBYTE)pInfo +
        pInfo->EventPropertyInfoArray[propIndex].NameOffset);
    desc.ArrayIndex = ULONG_MAX;

    ULONG bufSize = 0;
    if (TdhGetPropertySize(pEvent, 0, NULL, 1, &desc, &bufSize) != ERROR_SUCCESS)
        return FALSE;
    if (bufSize == 0 || bufSize > 8192) return FALSE;

    PBYTE rawBuf = (PBYTE)malloc(bufSize);
    if (!rawBuf) return FALSE;

    ULONG status = TdhGetProperty(pEvent, 0, NULL, 1, &desc, bufSize, rawBuf);
    if (status != ERROR_SUCCESS) { free(rawBuf); return FALSE; }

    ULONG inType = pInfo->EventPropertyInfoArray[propIndex].nonStructType.InType;
    if (inType == TDH_INTYPE_UNICODESTRING) {
        WideCharToMultiByte(CP_UTF8, 0, (LPCWCH)rawBuf, -1,
            outBuf, (int)outBufSize, NULL, NULL);
    } else if (inType == TDH_INTYPE_ANSISTRING) {
        strncpy_s(outBuf, outBufSize, (char*)rawBuf, _TRUNCATE);
    } else {
        if (bufSize == 4) sprintf_s(outBuf, outBufSize, "%lu", *(ULONG*)rawBuf);
        else if (bufSize == 8) sprintf_s(outBuf, outBufSize, "%llu", *(ULONGLONG*)rawBuf);
        else sprintf_s(outBuf, outBufSize, "(binary)");
    }

    free(rawBuf);
    return TRUE;
}

// ─────────────────────────────────────────────
// ETW Event Callback
// ─────────────────────────────────────────────

static VOID WINAPI EventCallback(PEVENT_RECORD pEvent) {
    if (!g_Running) return;

    DWORD pid = pEvent->EventHeader.ProcessId;

    // Only process events from our tracked PIDs
    if (!IsTrackedPID(pid)) return;

    // Get event metadata via TDH
    ULONG bufferSize = 0;
    PTRACE_EVENT_INFO pInfo = NULL;

    if (TdhGetEventInformation(pEvent, 0, NULL, NULL, &bufferSize)
            == ERROR_INSUFFICIENT_BUFFER) {
        pInfo = (PTRACE_EVENT_INFO)malloc(bufferSize);
        if (!pInfo) return;
        if (TdhGetEventInformation(pEvent, 0, NULL, pInfo, &bufferSize)
                != ERROR_SUCCESS) {
            free(pInfo);
            return;
        }
    } else {
        return;
    }

    char timestamp[64];
    GetTimestamp(timestamp, sizeof(timestamp));

    // ── Provider: Kernel-File ──
    if (IsEqualGUID(pEvent->EventHeader.ProviderId, FileProviderGuid)) {
        USHORT opcode = pEvent->EventHeader.EventDescriptor.Id;

        const char* opName = "FileOp";
        switch (opcode) {
            case 12: opName = "Create";  break;
            case 13: opName = "Cleanup"; break;
            case 14: opName = "Close";   break;
            case 15: opName = "Read";    break;
            case 16: opName = "Write";   break;
            case 17: opName = "SetInfo"; break;
            case 18: opName = "Delete";  break;
            case 19: opName = "Rename";  break;
        }

        char filePath[2048]  = "(unknown)";
        char escapedPath[4096] = "";

        for (ULONG i = 0; i < pInfo->TopLevelPropertyCount; i++) {
            char propName[256];
            WideCharToMultiByte(CP_UTF8, 0,
                (LPCWCH)((PBYTE)pInfo + pInfo->EventPropertyInfoArray[i].NameOffset),
                -1, propName, sizeof(propName), NULL, NULL);
            if (_stricmp(propName, "FileName") == 0 ||
                _stricmp(propName, "OpenPath") == 0) {
                GetPropertyString(pEvent, pInfo, i, filePath, sizeof(filePath));
                break;
            }
        }

        JsonEscape(filePath, escapedPath, sizeof(escapedPath));

        char json[MAX_EVENT_SIZE];
        sprintf_s(json, sizeof(json),
            "{\"type\":\"FILE\",\"time\":\"%s\",\"pid\":%lu,"
            "\"operation\":\"%s\",\"path\":\"%s\"}",
            timestamp, pid, opName, escapedPath);
        SendEvent(json);
    }

    // ── Provider: Kernel-Network ──
    else if (IsEqualGUID(pEvent->EventHeader.ProviderId, NetworkProviderGuid)) {
        USHORT opcode = pEvent->EventHeader.EventDescriptor.Id;

        const char* proto     = "TCP";
        const char* direction = "Send";
        if (opcode == 11 || opcode == 13 || opcode == 27) direction = "Recv";
        if (opcode == 12 || opcode == 13) proto = "UDP";
        if (opcode == 26 || opcode == 27) proto = "TCPv6";

        char srcAddr[64] = "", dstAddr[64] = "";
        char srcPort[16] = "", dstPort[16] = "";
        char size[32]    = "0";

        for (ULONG i = 0; i < pInfo->TopLevelPropertyCount; i++) {
            char propName[256];
            WideCharToMultiByte(CP_UTF8, 0,
                (LPCWCH)((PBYTE)pInfo + pInfo->EventPropertyInfoArray[i].NameOffset),
                -1, propName, sizeof(propName), NULL, NULL);

            if      (_stricmp(propName, "saddr") == 0 || _stricmp(propName, "SourceAddress") == 0)
                GetPropertyString(pEvent, pInfo, i, srcAddr, sizeof(srcAddr));
            else if (_stricmp(propName, "daddr") == 0 || _stricmp(propName, "DestAddress") == 0)
                GetPropertyString(pEvent, pInfo, i, dstAddr, sizeof(dstAddr));
            else if (_stricmp(propName, "sport") == 0 || _stricmp(propName, "SourcePort") == 0)
                GetPropertyString(pEvent, pInfo, i, srcPort, sizeof(srcPort));
            else if (_stricmp(propName, "dport") == 0 || _stricmp(propName, "DestPort") == 0)
                GetPropertyString(pEvent, pInfo, i, dstPort, sizeof(dstPort));
            else if (_stricmp(propName, "size") == 0 || _stricmp(propName, "DataSize") == 0)
                GetPropertyString(pEvent, pInfo, i, size, sizeof(size));
        }

        char json[MAX_EVENT_SIZE];
        sprintf_s(json, sizeof(json),
            "{\"type\":\"NETWORK\",\"time\":\"%s\",\"pid\":%lu,"
            "\"protocol\":\"%s\",\"direction\":\"%s\","
            "\"src\":\"%s:%s\",\"dst\":\"%s:%s\",\"size\":\"%s\"}",
            timestamp, pid, proto, direction,
            srcAddr, srcPort, dstAddr, dstPort, size);
        SendEvent(json);
    }

    // ── Provider: Kernel-Process ──
    else if (IsEqualGUID(pEvent->EventHeader.ProviderId, ProcessProviderGuid)) {
        USHORT opcode = pEvent->EventHeader.EventDescriptor.Id;

        if (opcode == 1) {
            // New process started — check if parent is tracked
            char parentPidStr[32] = "";
            char newPidStr[32]    = "";
            char imageName[1024]  = "";
            char cmdLine[2048]    = "";
            char escapedImg[2048] = "";
            char escapedCmd[4096] = "";

            for (ULONG i = 0; i < pInfo->TopLevelPropertyCount; i++) {
                char propName[256];
                WideCharToMultiByte(CP_UTF8, 0,
                    (LPCWCH)((PBYTE)pInfo + pInfo->EventPropertyInfoArray[i].NameOffset),
                    -1, propName, sizeof(propName), NULL, NULL);

                if      (_stricmp(propName, "ParentProcessID") == 0)
                    GetPropertyString(pEvent, pInfo, i, parentPidStr, sizeof(parentPidStr));
                else if (_stricmp(propName, "ProcessID") == 0)
                    GetPropertyString(pEvent, pInfo, i, newPidStr, sizeof(newPidStr));
                else if (_stricmp(propName, "ImageName") == 0)
                    GetPropertyString(pEvent, pInfo, i, imageName, sizeof(imageName));
                else if (_stricmp(propName, "CommandLine") == 0)
                    GetPropertyString(pEvent, pInfo, i, cmdLine, sizeof(cmdLine));
            }

            DWORD parentPid = (DWORD)atol(parentPidStr);
            DWORD newPid    = (DWORD)atol(newPidStr);

            if (IsTrackedPID(parentPid) && newPid != 0) {
                AddTrackedPID(newPid); // auto-track children
            }

            if (IsTrackedPID(parentPid) || IsTrackedPID(newPid)) {
                JsonEscape(imageName, escapedImg, sizeof(escapedImg));
                JsonEscape(cmdLine,   escapedCmd, sizeof(escapedCmd));

                char json[MAX_EVENT_SIZE];
                sprintf_s(json, sizeof(json),
                    "{\"type\":\"PROCESS\",\"time\":\"%s\",\"pid\":%lu,"
                    "\"event\":\"Start\",\"new_pid\":\"%s\","
                    "\"image\":\"%s\",\"cmdline\":\"%s\"}",
                    timestamp, pid, newPidStr, escapedImg, escapedCmd);
                SendEvent(json);
            }
        }
        else if (opcode == 2 && IsTrackedPID(pid)) {
            char json[512];
            sprintf_s(json, sizeof(json),
                "{\"type\":\"PROCESS\",\"time\":\"%s\",\"pid\":%lu,"
                "\"event\":\"Stop\"}",
                timestamp, pid);
            SendEvent(json);
        }
        else if (opcode == 5 && IsTrackedPID(pid)) {
            // DLL / image load
            char imageName[1024]  = "";
            char escapedImg[2048] = "";

            for (ULONG i = 0; i < pInfo->TopLevelPropertyCount; i++) {
                char propName[256];
                WideCharToMultiByte(CP_UTF8, 0,
                    (LPCWCH)((PBYTE)pInfo + pInfo->EventPropertyInfoArray[i].NameOffset),
                    -1, propName, sizeof(propName), NULL, NULL);
                if (_stricmp(propName, "ImageName") == 0) {
                    GetPropertyString(pEvent, pInfo, i, imageName, sizeof(imageName));
                    break;
                }
            }

            JsonEscape(imageName, escapedImg, sizeof(escapedImg));

            char json[MAX_EVENT_SIZE];
            sprintf_s(json, sizeof(json),
                "{\"type\":\"PROCESS\",\"time\":\"%s\",\"pid\":%lu,"
                "\"event\":\"ImageLoad\",\"image\":\"%s\"}",
                timestamp, pid, escapedImg);
            SendEvent(json);
        }
    }

    free(pInfo);
}

// ─────────────────────────────────────────────
// ETW: Buffer Callback (required by API)
// ─────────────────────────────────────────────

static ULONG WINAPI BufferCallback(PEVENT_TRACE_LOGFILE pLog) {
    (void)pLog;
    return g_Running ? TRUE : FALSE;
}

// ─────────────────────────────────────────────
// ETW Session Setup
// ─────────────────────────────────────────────

static BOOL StartETWSession(void) {
    ULONG propSize = sizeof(EVENT_TRACE_PROPERTIES) +
                     sizeof(SESSION_NAME) + 256;
    PEVENT_TRACE_PROPERTIES props =
        (PEVENT_TRACE_PROPERTIES)calloc(1, propSize);
    if (!props) return FALSE;

    props->Wnode.BufferSize    = propSize;
    props->Wnode.Flags         = WNODE_FLAG_TRACED_GUID;
    props->Wnode.ClientContext = 1;
    CoCreateGuid(&props->Wnode.Guid);
    props->LogFileMode     = EVENT_TRACE_REAL_TIME_MODE;
    props->LoggerNameOffset = sizeof(EVENT_TRACE_PROPERTIES);

    // Stop any lingering session with same name first
    ControlTrace(0, SESSION_NAME, props, EVENT_TRACE_CONTROL_STOP);
    memset(props, 0, propSize);

    props->Wnode.BufferSize    = propSize;
    props->Wnode.Flags         = WNODE_FLAG_TRACED_GUID;
    props->Wnode.ClientContext = 1;
    CoCreateGuid(&props->Wnode.Guid);
    props->LogFileMode     = EVENT_TRACE_REAL_TIME_MODE;
    props->LoggerNameOffset = sizeof(EVENT_TRACE_PROPERTIES);

    ULONG status = StartTrace(&g_hSession, SESSION_NAME, props);
    if (status != ERROR_SUCCESS) {
        fprintf(stderr, "[Engine] StartTrace failed: %lu\n", status);
        free(props);
        return FALSE;
    }

    // Enable the three providers
    EnableTraceEx2(g_hSession, &FileProviderGuid,
        EVENT_CONTROL_CODE_ENABLE_PROVIDER,
        TRACE_LEVEL_VERBOSE, 0xFFFFFFFFFFFFFFFF, 0, 0, NULL);

    EnableTraceEx2(g_hSession, &NetworkProviderGuid,
        EVENT_CONTROL_CODE_ENABLE_PROVIDER,
        TRACE_LEVEL_VERBOSE, 0xFFFFFFFFFFFFFFFF, 0, 0, NULL);

    EnableTraceEx2(g_hSession, &ProcessProviderGuid,
        EVENT_CONTROL_CODE_ENABLE_PROVIDER,
        TRACE_LEVEL_VERBOSE, 0xFFFFFFFFFFFFFFFF, 0, 0, NULL);

    free(props);
    fprintf(stdout, "[Engine] ETW session started.\n");
    return TRUE;
}

// ─────────────────────────────────────────────
// ETW Consumer Thread (blocking)
// ─────────────────────────────────────────────

static DWORD WINAPI ETWConsumerThread(LPVOID lpParam) {
    (void)lpParam;

    EVENT_TRACE_LOGFILE logfile   = {0};
    logfile.LoggerName            = (LPWSTR)SESSION_NAME;
    logfile.ProcessTraceMode      = PROCESS_TRACE_MODE_REAL_TIME |
                                     PROCESS_TRACE_MODE_EVENT_RECORD;
    logfile.EventRecordCallback   = EventCallback;
    logfile.BufferCallback        = BufferCallback;

    g_hTrace = OpenTrace(&logfile);
    if (g_hTrace == INVALID_PROCESSTRACE_HANDLE) {
        fprintf(stderr, "[Engine] OpenTrace failed: %lu\n", GetLastError());
        return 1;
    }

    ProcessTrace(&g_hTrace, 1, NULL, NULL);
    CloseTrace(g_hTrace);
    return 0;
}

// ─────────────────────────────────────────────
// Launch Target Process with Correct Working Dir
// ─────────────────────────────────────────────

static BOOL LaunchTarget(
    const wchar_t* exePath,
    const wchar_t* workingDir,
    DWORD*         outPID)
{
    STARTUPINFOW        si = {0};
    PROCESS_INFORMATION pi = {0};
    si.cb = sizeof(si);

    wchar_t cmdLine[4096] = {0};
    const wchar_t* ext = PathFindExtensionW(exePath);

    if (_wcsicmp(ext, L".bat") == 0) {
        // .bat files must be run through cmd.exe
        StringCchPrintfW(cmdLine, 4096, L"cmd.exe /c \"%s\"", exePath);
    } else {
        StringCchPrintfW(cmdLine, 4096, L"\"%s\"", exePath);
    }

    BOOL ok = CreateProcessW(
        NULL,        // let cmdLine determine the exe
        cmdLine,     // command line
        NULL,        // process security
        NULL,        // thread security
        FALSE,       // don't inherit handles
        0,           // no special creation flags
        NULL,        // inherit our environment
        workingDir,  // ← target's own directory (key line)
        &si,
        &pi
    );

    if (!ok) {
        fprintf(stderr, "[Engine] CreateProcess failed: %lu\n", GetLastError());
        return FALSE;
    }

    *outPID = pi.dwProcessId;
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);

    fprintf(stdout, "[Engine] Target launched with PID: %lu\n", *outPID);
    return TRUE;
}

// ─────────────────────────────────────────────
// Named Pipe Setup (server side, engine writes)
// ─────────────────────────────────────────────

static BOOL SetupPipe(const wchar_t* pipeName) {
    g_hPipe = CreateNamedPipeW(
        pipeName,
        PIPE_ACCESS_OUTBOUND,
        PIPE_TYPE_MESSAGE | PIPE_WAIT,
        1,
        PIPE_BUFFER_SIZE,
        PIPE_BUFFER_SIZE,
        0,
        NULL
    );

    if (g_hPipe == INVALID_HANDLE_VALUE) {
        fprintf(stderr, "[Engine] CreateNamedPipe failed: %lu\n", GetLastError());
        return FALSE;
    }

    fprintf(stdout, "[Engine] Pipe created. Waiting for pipeline.py...\n");
    fflush(stdout);

    if (!ConnectNamedPipe(g_hPipe, NULL)) {
        DWORD err = GetLastError();
        if (err != ERROR_PIPE_CONNECTED) {
            fprintf(stderr, "[Engine] ConnectNamedPipe failed: %lu\n", err);
            return FALSE;
        }
    }

    fprintf(stdout, "[Engine] pipeline.py connected.\n");
    return TRUE;
}

// ─────────────────────────────────────────────
// Ctrl+C Handler — graceful shutdown
// ─────────────────────────────────────────────

static BOOL WINAPI CtrlHandler(DWORD type) {
    if (type == CTRL_C_EVENT || type == CTRL_BREAK_EVENT) {
        g_Running = FALSE;
        fprintf(stdout, "[Engine] Shutdown signal received.\n");

        if (g_hSession) {
            ULONG propSize = sizeof(EVENT_TRACE_PROPERTIES) + sizeof(SESSION_NAME) + 256;
            PEVENT_TRACE_PROPERTIES props =
                (PEVENT_TRACE_PROPERTIES)calloc(1, propSize);
            if (props) {
                props->Wnode.BufferSize = propSize;
                props->LoggerNameOffset = sizeof(EVENT_TRACE_PROPERTIES);
                ControlTrace(g_hSession, SESSION_NAME, props,
                    EVENT_TRACE_CONTROL_STOP);
                free(props);
            }
        }

        if (g_hPipe != INVALID_HANDLE_VALUE) {
            const char* shutdownMsg = "{\"type\":\"SHUTDOWN\"}\n";
            DWORD written = 0;
            WriteFile(g_hPipe, shutdownMsg, (DWORD)strlen(shutdownMsg),
                &written, NULL);
            FlushFileBuffers(g_hPipe);
            CloseHandle(g_hPipe);
            g_hPipe = INVALID_HANDLE_VALUE;
        }
        return TRUE;
    }
    return FALSE;
}

// ─────────────────────────────────────────────
// Entry Point
// ─────────────────────────────────────────────

int wmain(int argc, wchar_t* argv[]) {
    if (argc < 4) {
        fwprintf(stderr,
            L"Usage: monitor_engine.exe <exe_path> <working_dir> <pipe_name>\n"
            L"Note: Must be run as Administrator for ETW access.\n");
        return 1;
    }

    const wchar_t* exePath    = argv[1];
    const wchar_t* workingDir = argv[2];
    const wchar_t* pipeName   = argv[3];

    fprintf(stdout, "[Engine] BehaviorMonitor Engine v1.0 starting...\n");
    fflush(stdout);

    if (!PathFileExistsW(exePath)) {
        fwprintf(stderr, L"[Engine] Target not found: %s\n", exePath);
        return 1;
    }

    SetConsoleCtrlHandler(CtrlHandler, TRUE);

    // Step 1: Create named pipe, wait for Python to connect
    if (!SetupPipe(pipeName)) return 1;

    // Step 2: Start ETW session (requires Administrator)
    if (!StartETWSession()) {
        CloseHandle(g_hPipe);
        return 1;
    }

    // Step 3: Launch target in its own directory
    DWORD targetPID = 0;
    if (!LaunchTarget(exePath, workingDir, &targetPID)) {
        CloseHandle(g_hPipe);
        return 1;
    }

    g_TargetPID = targetPID;
    AddTrackedPID(targetPID);

    // Notify pipeline of the launched PID
    char launchMsg[256];
    sprintf_s(launchMsg, sizeof(launchMsg),
        "{\"type\":\"LAUNCHED\",\"pid\":%lu}\n", targetPID);
    DWORD written = 0;
    WriteFile(g_hPipe, launchMsg, (DWORD)strlen(launchMsg), &written, NULL);

    // Step 4: Start ETW consumer thread
    HANDLE hThread = CreateThread(NULL, 0, ETWConsumerThread, NULL, 0, NULL);
    if (!hThread) {
        fprintf(stderr, "[Engine] Failed to start ETW thread.\n");
        CloseHandle(g_hPipe);
        return 1;
    }

    // Step 5: Wait until ETW thread exits (stopped by Ctrl+C or SHUTDOWN signal)
    WaitForSingleObject(hThread, INFINITE);
    CloseHandle(hThread);

    fprintf(stdout, "[Engine] Engine stopped cleanly.\n");
    return 0;
}
