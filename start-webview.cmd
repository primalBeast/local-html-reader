@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Local HTML Reader
REM Splash is started by start-webview.vbs, or by Python if this cmd is run alone.
REM Starting it here as well closed the first splash and opened a second one.

REM Minimize THIS console (do not hide it). Logs stay in the window; restore from the taskbar.
powershell -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0scripts\minimize-console.ps1"

echo.
echo ============================================
echo  Local HTML Reader  (WebView2 window)
echo ============================================
echo.

call :refresh_uv_path
where uv >nul 2>&1
if errorlevel 1 (
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

echo Starting the local server in a WebView2 window (not a browser tab).
echo Close the app window to stop. You can still use start.cmd for the browser.
echo This console is minimized — restore "Local HTML Reader" from the taskbar for logs.
echo.
echo http://127.0.0.1:8766
echo.

uv run lhr serve --webview
exit /b %ERRORLEVEL%

:refresh_uv_path
if exist "%USERPROFILE%\.local\bin\uv.exe" set "PATH=%USERPROFILE%\.local\bin;%PATH%"
if exist "%USERPROFILE%\.cargo\bin\uv.exe" set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
exit /b 0
