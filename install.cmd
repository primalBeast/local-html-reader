@echo off
setlocal EnableExtensions
cd /d "%~dp0"
rem %~dp0 is unreliable inside call :label subroutines, so keep the folder here.
set "LHR_HERE=%~dp0"

rem Every message and every tool's output also goes to install.log next to this file.
set "LOG=%LHR_HERE%install.log"
set "STEP_OUT=%TEMP%\lhr-install-step.txt"
> "%LOG%" echo Local HTML Reader install log  %DATE% %TIME%
>> "%LOG%" echo Folder: %LHR_HERE%

call :say ""
call :say "============================================"
call :say " Local HTML Reader - Windows install"
call :say "============================================"
call :say ""
call :say "This installs uv (if needed) and the app."
call :say "Git is assumed already installed because you cloned the repo."
call :say "Node.js is not required to run the app."
call :say "A copy of everything shown here is saved to install.log."
call :say ""

set "FAILED=0"
rem Corporate laptops often need the Windows certificate store (not webpki).
set "UV_NATIVE_TLS=1"
if not defined SystemRoot set "SystemRoot=C:\Windows"
rem A damaged prompt can lose PATHEXT or System32. Put back what this script needs.
if not defined PATHEXT set "PATHEXT=.COM;.EXE;.BAT;.CMD"
rem Only System32 is added. PATH is never rebuilt from the registry (that hid curl and winget).
set "PATH=%SystemRoot%\System32;%SystemRoot%\System32\WindowsPowerShell\v1.0;%PATH%"
set "PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
set "TOOLS_UV=%LHR_HERE%.tools\uv"
>> "%LOG%" echo PATHEXT=%PATHEXT%

call "%LHR_HERE%scripts\find-uv.cmd"
if defined UV_EXE call :verify_uv
if not defined UV_EXE call :install_uv
if not defined UV_EXE (
  call :say "[FAIL] uv could not be found or installed."
  call :diagnose
  call :say "       Send install.log from this folder if you need help."
  set "FAILED=1"
  goto :summary
)

call :say "[OK]   uv found: %UV_EXE%"
call :say ""

if not exist "pyproject.toml" (
  call :say "[FAIL] pyproject.toml missing. Run this from the cloned repo folder."
  set "FAILED=1"
  goto :summary
)
if not exist "lhr\cli.py" (
  call :say "[FAIL] lhr\cli.py missing. The clone looks incomplete. Run: git pull"
  set "FAILED=1"
  goto :summary
)
call :say "[OK]   repo files present"
call :say ""

call :say "[..] Installing Python 3.12+ and app dependencies with uv sync --native-tls"
call :say "     This can take a few minutes the first time."
set "STEP=uv sync"
call :run "%UV_EXE%" sync --native-tls
if errorlevel 1 (
  call :say "[FAIL] uv sync failed."
  set "FAILED=1"
  goto :summary
)
call :say "[OK]   uv sync finished"
call :say ""

call :say "[..] Checking Python version"
set "STEP=python version"
call :run "%UV_EXE%" run python -c "import sys; assert sys.version_info >= (3, 12), sys.version; print(sys.version)"
if errorlevel 1 (
  call :say "[FAIL] Python 3.12+ is required."
  set "FAILED=1"
  goto :summary
)
call :say "[OK]   Python 3.12+"
call :say ""

call :say "[..] Checking lhr import"
set "STEP=lhr import"
call :run "%UV_EXE%" run python -c "from lhr.cli import main; print('import lhr.cli: OK')"
if errorlevel 1 (
  call :say "[FAIL] Could not import lhr.cli. Try: uv sync --reinstall"
  set "FAILED=1"
  goto :summary
)
call :say ""

if not exist "frontend\dist\index.html" (
  call :say "[FAIL] frontend\dist\index.html missing. The UI bundle is not in this clone."
  call :say "       Run: git pull"
  set "FAILED=1"
  goto :summary
)
dir /b "frontend\dist\assets\*.js" >nul 2>&1
if errorlevel 1 (
  call :say "[FAIL] No JS files in frontend\dist\assets. The UI bundle is incomplete."
  call :say "       Run: git pull"
  set "FAILED=1"
  goto :summary
)
call :say "[OK]   frontend production build present"
call :say ""

call :say "[..] lhr doctor"
set "STEP=lhr doctor"
call :run "%UV_EXE%" run lhr doctor
if errorlevel 1 (
  call :say "[FAIL] lhr doctor failed."
  set "FAILED=1"
  goto :summary
)
call :say "[OK]   lhr doctor finished"
call :say ""

:summary
call :say "============================================"
if "%FAILED%"=="0" (
  call :say " Install checks passed."
  call :say " Double-click start.cmd to launch the app."
  call :say " Or run:  start.cmd"
  call :say " Then open http://127.0.0.1:8766"
) else (
  call :say " Install checks FAILED. See messages above, or install.log."
)
call :say "============================================"
call :say ""
del "%STEP_OUT%" >nul 2>&1
if not defined LHR_NO_PAUSE pause
exit /b %FAILED%

rem ---------------------------------------------------------------------------

:say
rem Show one line and append it to install.log. Delayed expansion keeps ( ) & safe.
set "LHR_MSG=%~1"
setlocal EnableDelayedExpansion
echo(!LHR_MSG!
>> "!LOG!" echo(!LHR_MSG!
endlocal
exit /b 0

:run
rem Set STEP first, then: call :run "program" args...
rem Shows and logs the program's output, then its exit code.
>> "%LOG%" echo --- %STEP%: %*
%* > "%STEP_OUT%" 2>&1
set "STEP_RC=%ERRORLEVEL%"
type "%STEP_OUT%"
type "%STEP_OUT%" >> "%LOG%"
call :say "       %STEP%: exit code %STEP_RC%"
exit /b %STEP_RC%

:verify_uv
rem uv.exe can exist but be blocked from running (AppLocker, EDR). Check it really runs.
set "STEP=uv --version"
call :run "%UV_EXE%" --version
if not errorlevel 1 exit /b 0
call :say "[WARN] %UV_EXE% exists but would not run. Security software may be blocking it."
set "UV_BLOCKED=%UV_EXE%"
set "UV_EXE="
exit /b 0

:install_uv
call :say "[..] uv not found. Installing uv..."
if defined LHR_SKIP_WINGET goto :install_uv_download
rem winget.exe here is an app alias. "if exist" can miss it, so just try to run it.
set "WINGET=%LOCALAPPDATA%\Microsoft\WindowsApps\winget.exe"
set "STEP=winget --version"
call :run "%WINGET%" --version
if errorlevel 1 (
  call :say "     winget is not available. Skipping it."
  goto :install_uv_download
)
call :say "[..] Trying winget..."
rem winget's exit code is not used: "already installed" and real failures both look odd.
set "STEP=winget"
call :run "%WINGET%" install --id=astral-sh.uv -e --accept-package-agreements --accept-source-agreements
rem winget may say uv is already installed. Look for that copy before downloading.
call "%LHR_HERE%scripts\find-uv.cmd" deep
if defined UV_EXE call :verify_uv
if defined UV_EXE exit /b 0
call :say "     winget did not leave a uv.exe that this script can find."

:install_uv_download
set "UV_ZIP=%TEMP%\lhr-uv-windows.zip"
set "UV_TMP=%TEMP%\lhr-uv-unpack"
set "UV_URL=https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip"
if /I "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "UV_URL=https://github.com/astral-sh/uv/releases/latest/download/uv-aarch64-pc-windows-msvc.zip"
if /I "%PROCESSOR_ARCHITEW6432%"=="ARM64" set "UV_URL=https://github.com/astral-sh/uv/releases/latest/download/uv-aarch64-pc-windows-msvc.zip"
call :say "[..] Downloading uv to %TOOLS_UV%"
call :say "     from %UV_URL%"
del "%UV_ZIP%" >nul 2>&1
call :download_uv_zip
call :check_uv_zip
if errorlevel 1 exit /b 1
call :unpack_uv_zip
if errorlevel 1 exit /b 1
set "UV_EXE=%TOOLS_UV%\uv.exe"
call :verify_uv
del "%UV_ZIP%" >nul 2>&1
rd /s /q "%UV_TMP%" >nul 2>&1
exit /b 0

:download_uv_zip
if exist "%SystemRoot%\System32\curl.exe" (
  set "STEP=curl.exe download"
  call :run "%SystemRoot%\System32\curl.exe" -fsSL --retry 2 -o "%UV_ZIP%" "%UV_URL%"
  if not errorlevel 1 exit /b 0
) else (
  call :say "     %SystemRoot%\System32\curl.exe is missing."
)
call :say "[..] Downloading with PowerShell Invoke-WebRequest instead."
set "STEP=PowerShell download"
call :run "%PS%" -NoProfile -NonInteractive -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; $ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Uri $env:UV_URL -OutFile $env:UV_ZIP; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
exit /b %ERRORLEVEL%

:check_uv_zip
rem A proxy or security tool can return a small HTML page instead of the zip.
if not exist "%UV_ZIP%" (
  call :say "[FAIL] The uv download did not create %UV_ZIP%."
  call :say "       A proxy or security software probably blocked the download."
  exit /b 1
)
set "UV_ZIP_SIZE=0"
for %%F in ("%UV_ZIP%") do set "UV_ZIP_SIZE=%%~zF"
call :say "     Downloaded %UV_ZIP_SIZE% bytes."
rem Read the first bytes and compare with delayed expansion, so & | " in binary data are never parsed.
set "UV_ZIP_HEAD="
set /p UV_ZIP_HEAD=< "%UV_ZIP%"
setlocal EnableDelayedExpansion
set "UV_ZIP_PK=0"
if "!UV_ZIP_HEAD:~0,2!"=="PK" set "UV_ZIP_PK=1"
endlocal & set "UV_ZIP_PK=%UV_ZIP_PK%"
set "UV_ZIP_HEAD="
if %UV_ZIP_SIZE% LSS 1048576 goto :bad_uv_zip
if not "%UV_ZIP_PK%"=="1" goto :bad_uv_zip
call :say "[OK]   The download is a zip file."
exit /b 0

:bad_uv_zip
call :say "[FAIL] The uv download is not a zip file (size %UV_ZIP_SIZE% bytes, zip header %UV_ZIP_PK%)."
call :say "       A proxy or security software probably replaced or blocked it."
if %UV_ZIP_SIZE% LSS 65536 (
  call :say "       What came back instead is saved in install.log."
  >> "%LOG%" echo --- what the download returned:
  >> "%LOG%" type "%UV_ZIP%" 2>nul
  >> "%LOG%" echo.
)
exit /b 1

:unpack_uv_zip
rd /s /q "%UV_TMP%" >nul 2>&1
mkdir "%UV_TMP%" >nul 2>&1
if exist "%SystemRoot%\System32\tar.exe" (
  set "STEP=tar.exe unpack"
  call :run "%SystemRoot%\System32\tar.exe" -xf "%UV_ZIP%" -C "%UV_TMP%"
) else (
  call :say "     %SystemRoot%\System32\tar.exe is missing."
)
call :find_unpacked_uv
if defined UV_UNPACKED goto :copy_uv
rem .NET ZipFile works when Group Policy blocks script modules such as Expand-Archive.
call :say "[..] Unpacking with .NET ZipFile instead."
rd /s /q "%UV_TMP%" >nul 2>&1
set "STEP=.NET ZipFile unpack"
call :run "%PS%" -NoProfile -NonInteractive -Command "try { Add-Type -AssemblyName System.IO.Compression.FileSystem; [IO.Compression.ZipFile]::ExtractToDirectory($env:UV_ZIP, $env:UV_TMP); exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"
call :find_unpacked_uv
if defined UV_UNPACKED goto :copy_uv
call :say "[FAIL] Could not unpack uv.exe from the download."
call :say "       Unpacked files:"
dir /s /b "%UV_TMP%" 2>nul
>> "%LOG%" dir /s /b "%UV_TMP%" 2>nul
exit /b 1

:find_unpacked_uv
set "UV_UNPACKED="
if exist "%UV_TMP%\uv.exe" set "UV_UNPACKED=%UV_TMP%\uv.exe"
if defined UV_UNPACKED exit /b 0
for /f "delims=" %%F in ('dir /s /b "%UV_TMP%\uv.exe" 2^>nul') do set "UV_UNPACKED=%%~fF"
exit /b 0

:copy_uv
if not exist "%TOOLS_UV%" mkdir "%TOOLS_UV%"
for %%F in ("%UV_UNPACKED%") do set "UV_UNPACKED_DIR=%%~dpF"
copy /Y "%UV_UNPACKED_DIR%*.exe" "%TOOLS_UV%\" >nul
if not exist "%TOOLS_UV%\uv.exe" (
  call :say "[FAIL] Could not copy uv.exe into %TOOLS_UV%."
  call :say "       Security software may have removed it."
  exit /b 1
)
rem Drop the downloaded-from-the-internet mark. Unblock-File is not a script, so policy allows it.
"%PS%" -NoProfile -NonInteractive -Command "Get-ChildItem -LiteralPath $env:TOOLS_UV -Filter *.exe | Unblock-File" >nul 2>&1
set "UV_EXE_SIZE=0"
for %%F in ("%TOOLS_UV%\uv.exe") do set "UV_EXE_SIZE=%%~zF"
call :say "[OK]   uv.exe saved to %TOOLS_UV% (%UV_EXE_SIZE% bytes)"
exit /b 0

:diagnose
call :say ""
call :say "---- Details for troubleshooting ----"
call :say "PATHEXT: %PATHEXT%"
if defined UV_BLOCKED call :say "Found but would not run: %UV_BLOCKED%"
call :say "Places checked for uv.exe:"
call "%LHR_HERE%scripts\find-uv.cmd" deep
for %%L in ("%UV_LOOKED:|=" "%") do if not "%%~L"=="" call :say "  %%~L"
set "UV_EXE="
if exist "%PS%" (
  set "STEP=Get-ExecutionPolicy -List"
  call :run "%PS%" -NoProfile -NonInteractive -Command "Get-ExecutionPolicy -List | Out-String; 'Language mode: ' + $ExecutionContext.SessionState.LanguageMode"
) else (
  call :say "PowerShell not found at %PS%"
)
>> "%LOG%" echo PATH=%PATH%
call :say "-------------------------------------"
exit /b 0
