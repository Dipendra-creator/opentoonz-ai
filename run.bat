@echo off
setlocal
rem Starts the OpenToonz AI Studio (paste a story, get an animation)
rem on http://127.0.0.1:8765. First run creates ai\.venv and installs dependencies.

cd /d "%~dp0ai"

if not exist ".venv\Scripts\python.exe" (
    echo Creating Python environment in ai\.venv ...
    python -m venv .venv
    if errorlevel 1 (
        echo Python 3.11 or newer must be installed and on PATH.
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Installing dependencies failed.
        rmdir /s /q .venv
        pause
        exit /b 1
    )
)

where claude >nul 2>nul
if errorlevel 1 echo Warning: Claude CLI not found on PATH. Stories cannot be directed until it is installed.

echo.
echo OpenToonz AI Studio: http://127.0.0.1:8765
echo Videos and OpenToonz scenes: %~dp0ai\workspace\productions
echo Close this window or press Ctrl+C to stop.
echo.

rem open the browser once the server has had a moment to start
start "" /b cmd /c "timeout /t 3 /nobreak >nul & start "" http://127.0.0.1:8765"

".venv\Scripts\python.exe" -m otai.web
pause
