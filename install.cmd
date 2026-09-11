@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo ============================================
echo  Local HTML Reader - Windows install
echo ============================================
echo.
echo This installs uv (if needed) and the app.
echo Git is assumed already installed because you cloned the repo.
echo Node.js is not required to run the app.
echo.

set "FAILED=0"
rem Corporate laptops often need the Windows certificate store (not webpki).
set "UV_NATIVE_TLS=1"

call :refresh_uv_path
where uv >nul 2>&1
if errorlevel 1 (
  echo [..] uv not found. Installing uv...
  call :install_uv
  call :refresh_uv_path
)

where uv >nul 2>&1
if errorlevel 1 (
  echo [FAIL] uv is not on PATH after install.
  echo        Close this window, open a new Command Prompt, and run install.cmd again.
  echo        Or install from: https://docs.astral.sh/uv/getting-started/installation/
  set "FAILED=1"
  goto :summary
)

echo [OK]   uv found
uv --version
echo.

if not exist "pyproject.toml" (
  echo [FAIL] pyproject.toml missing. Run this from the cloned repo folder.
  set "FAILED=1"
  goto :summary
)
if not exist "lhr\cli.py" (
  echo [FAIL] lhr\cli.py missing. The clone looks incomplete. Run: git pull
  set "FAILED=1"
  goto :summary
)
echo [OK]   repo files present
echo.

echo [..] Installing Python 3.12+ and app dependencies (uv sync --native-tls^)
uv sync --native-tls
if errorlevel 1 (
  echo [FAIL] uv sync failed.
  set "FAILED=1"
  goto :summary
)
echo [OK]   uv sync finished
echo.

echo [..] Checking Python version
uv run python -c "import sys; assert sys.version_info >= (3, 12), sys.version; print(sys.version)"
if errorlevel 1 (
  echo [FAIL] Python 3.12+ is required.
  set "FAILED=1"
  goto :summary
)
echo [OK]   Python 3.12+
echo.

echo [..] Checking lhr import
uv run python -c "from lhr.cli import main; print('import lhr.cli: OK')"
if errorlevel 1 (
  echo [FAIL] Could not import lhr.cli. Try: uv sync --reinstall
  set "FAILED=1"
  goto :summary
)
echo.

if not exist "frontend\dist\index.html" (
  echo [FAIL] frontend\dist\index.html missing. The UI bundle is not in this clone.
  echo        Run: git pull
  set "FAILED=1"
  goto :summary
)
dir /b "frontend\dist\assets\*.js" >nul 2>&1
if errorlevel 1 (
  echo [FAIL] No JS files in frontend\dist\assets. The UI bundle is incomplete.
  echo        Run: git pull
  set "FAILED=1"
  goto :summary
)
echo [OK]   frontend production build present
echo.

echo [..] lhr doctor
uv run lhr doctor
if errorlevel 1 (
  echo [FAIL] lhr doctor failed.
  set "FAILED=1"
  goto :summary
)
echo [OK]   lhr doctor finished
echo.

:summary
echo ============================================
if "%FAILED%"=="0" (
  echo  Install checks passed.
  echo  Double-click start.cmd to launch the app.
  echo  Or run:  uv run lhr serve --open
  echo  Then open http://127.0.0.1:8766
) else (
  echo  Install checks FAILED. See messages above.
)
echo ============================================
echo.
pause
exit /b %FAILED%

:refresh_uv_path
if exist "%USERPROFILE%\.local\bin\uv.exe" set "PATH=%USERPROFILE%\.local\bin;%PATH%"
if exist "%USERPROFILE%\.cargo\bin\uv.exe" set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
exit /b 0

:install_uv
where winget >nul 2>&1
if not errorlevel 1 (
  echo [..] Trying winget...
  winget install --id=astral-sh.uv -e --accept-package-agreements --accept-source-agreements
  call :refresh_uv_path
  where uv >nul 2>&1
  if not errorlevel 1 exit /b 0
)

echo [..] Trying the official uv installer...
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
exit /b %ERRORLEVEL%
