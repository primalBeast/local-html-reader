@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo ============================================
echo  Local HTML Reader
echo ============================================
echo.

if not defined SystemRoot set "SystemRoot=C:\Windows"
if not defined PATHEXT set "PATHEXT=.COM;.EXE;.BAT;.CMD"
set "PATH=%SystemRoot%\System32;%SystemRoot%\System32\WindowsPowerShell\v1.0;%PATH%"
rem Find uv by full path. install.cmd puts its own copy in .tools\uv.
call "%~dp0scripts\find-uv.cmd"
if not defined UV_EXE (
  echo uv is not installed. Double-click install.cmd first.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\" (
  echo App is not installed yet. Double-click install.cmd first.
  echo.
  pause
  exit /b 1
)

if not exist "frontend\dist\index.html" (
  echo frontend\dist is missing. Double-click install.cmd, or run: git pull
  echo.
  pause
  exit /b 1
)

"%SystemRoot%\System32\netstat.exe" -ano | "%SystemRoot%\System32\findstr.exe" ":8766" | "%SystemRoot%\System32\findstr.exe" "LISTENING" >nul
if not errorlevel 1 (
  echo Already running on http://127.0.0.1:8766
  echo Opening the browser...
  start "" "http://127.0.0.1:8766"
  echo.
  pause
  exit /b 0
)

echo Starting local server and opening the browser.
echo Leave this window open while you use the app.
echo Press Ctrl+C to stop.
echo.
echo http://127.0.0.1:8766
echo.

"%UV_EXE%" run lhr serve --open
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo Server exited with an error ^(%RC%^).
  echo If you see "No module named lhr", run install.cmd again.
)
pause
exit /b %RC%
