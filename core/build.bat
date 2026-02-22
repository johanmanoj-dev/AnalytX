@echo off
:: build.bat
:: Compiles monitor_engine.cpp using MSVC (cl.exe)
:: Run this from a "Developer Command Prompt for VS" or after running vcvarsall.bat
:: Must be run as Administrator to use ETW at runtime

echo [Build] Compiling monitor_engine.cpp...

cl.exe ^
    /W3 ^
    /O2 ^
    /EHsc ^
    /D "UNICODE" ^
    /D "_UNICODE" ^
    /D "WIN32_LEAN_AND_MEAN" ^
    monitor_engine.cpp ^
    /link ^
    tdh.lib ^
    advapi32.lib ^
    ws2_32.lib ^
    shlwapi.lib ^
    ole32.lib ^
    /OUT:monitor_engine.exe

if %ERRORLEVEL% == 0 (
    echo [Build] SUCCESS - monitor_engine.exe created.
    echo [Build] Copy monitor_engine.exe to BehaviorMonitor\core\
) else (
    echo [Build] FAILED - check errors above.
    echo [Build] Make sure you are in a Developer Command Prompt for Visual Studio.
)

pause