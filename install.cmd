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
if not defined SystemRoot set "SystemRoot=C:\Windows"
rem The prompt on a new laptop can omit System32 and WindowsApps, so curl and winget look missing.
set "PATH=%SystemRoot%\System32;%SystemRoot%\System32\WindowsPowerShell\v1.0;%LOCALAPPDATA%\Microsoft\WindowsApps;%PATH%"

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
set "USER_PATH="
for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "[Environment]::GetEnvironmentVariable('Path','User')"`) do set "USER_PATH=%%A"
if defined USER_PATH set "PATH=%USER_PATH%;%PATH%"
if exist "%USERPROFILE%\.local\bin\uv.exe" set "PATH=%USERPROFILE%\.local\bin;%PATH%"
if exist "%USERPROFILE%\.cargo\bin\uv.exe" set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
if exist "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe" set "PATH=%LOCALAPPDATA%\Microsoft\WinGet\Links;%PATH%"
if exist "%ProgramFiles%\WinGet\Links\uv.exe" set "PATH=%ProgramFiles%\WinGet\Links;%PATH%"
for /f "delims=" %%F in ('dir /s /b "%LOCALAPPDATA%\Microsoft\WinGet\Packages\uv.exe" 2^>nul') do set "PATH=%%~dpF;%PATH%"
for /f "delims=" %%F in ('dir /s /b "%ProgramFiles%\WinGet\Packages\uv.exe" 2^>nul') do set "PATH=%%~dpF;%PATH%"
exit /b 0

:install_uv
set "WINGET="
if exist "%LOCALAPPDATA%\Microsoft\WindowsApps\winget.exe" set "WINGET=%LOCALAPPDATA%\Microsoft\WindowsApps\winget.exe"
if not defined WINGET (
  where winget >nul 2>&1
  if not errorlevel 1 set "WINGET=winget"
)
if defined WINGET (
  echo [..] Trying winget...
  "%WINGET%" install --id=astral-sh.uv -e --accept-package-agreements --accept-source-agreements
  call :refresh_uv_path
  where uv >nul 2>&1
  if not errorlevel 1 exit /b 0
)

echo [..] Downloading uv.
set "UV_ZIP=%TEMP%\uv-windows.zip"
set "UV_DIR=%USERPROFILE%\.local\bin"
set "UV_URL=https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip"
if /I "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "UV_URL=https://github.com/astral-sh/uv/releases/latest/download/uv-aarch64-pc-windows-msvc.zip"
call :download_uv_zip
if errorlevel 1 (
  echo [FAIL] Could not download uv.
  exit /b 1
)
if not exist "%UV_DIR%" mkdir "%UV_DIR%"
powershell -NoProfile -Command "Expand-Archive -Force -LiteralPath $env:TEMP\uv-windows.zip -DestinationPath $env:USERPROFILE\.local\bin"
if not exist "%UV_DIR%\uv.exe" (
  for /f "delims=" %%F in ('dir /s /b "%UV_DIR%\uv.exe" 2^>nul') do copy /Y "%%F" "%UV_DIR%\uv.exe" >nul
)
if not exist "%UV_DIR%\uv.exe" (
  echo [FAIL] The download did not contain uv.exe.
  echo        Zip:
  dir "%UV_ZIP%"
  echo        Unpacked folder:
  dir /s /b "%UV_DIR%"
  exit /b 1
)
echo [OK]   uv.exe saved to %UV_DIR%
del "%UV_ZIP%" >nul 2>&1
call :refresh_uv_path
where uv >nul 2>&1
exit /b %ERRORLEVEL%

:download_uv_zip
if exist "%SystemRoot%\System32\curl.exe" (
  "%SystemRoot%\System32\curl.exe" -fsSL -L -o "%UV_ZIP%" "%UV_URL%"
  if not errorlevel 1 exit /b 0
)
echo [..] curl is not available. Downloading with PowerShell...
powershell -NoProfile -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -UseBasicParsing -Uri $env:UV_URL -OutFile $env:UV_ZIP; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
exit /b %ERRORLEVEL%
