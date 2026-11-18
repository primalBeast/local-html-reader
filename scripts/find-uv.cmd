@echo off
rem Sets UV_EXE to the full path of a uv.exe that exists, or leaves it empty.
rem UV_LOOKED lists every place checked, separated by "|".
rem Every check is "if exist". It never uses where, so a broken PATH or PATHEXT cannot hide uv.
rem Pass "deep" to also search inside the WinGet uv package folders (used after winget runs).
rem No setlocal here: the caller keeps UV_EXE and UV_LOOKED.
set "UV_EXE="
set "UV_LOOKED="
for %%I in ("%~dp0..") do set "LHR_ROOT=%%~fI"

call :try "%LHR_ROOT%\.tools\uv\uv.exe"
for %%I in (uv.exe) do if not "%%~$PATH:I"=="" call :try "%%~$PATH:I"
call :try "%USERPROFILE%\.local\bin\uv.exe"
call :try "%USERPROFILE%\.cargo\bin\uv.exe"
call :try "%LOCALAPPDATA%\Microsoft\WinGet\Links\uv.exe"
call :try "%ProgramFiles%\WinGet\Links\uv.exe"
for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\astral-sh.uv*") do call :try_dir_and_children "%%~fD"
for /d %%D in ("%ProgramFiles%\WinGet\Packages\astral-sh.uv*") do call :try_dir_and_children "%%~fD"
if defined UV_EXE exit /b 0

rem The saved user PATH can list a uv folder this window has not picked up yet.
rem Read it once and check each folder. It is never copied onto PATH: rebuilding PATH
rem from the registry is what hid curl, winget and uv on Nov 18 2026.
if not defined LHR_USER_PATH call :read_user_path
if defined LHR_USER_PATH for %%D in ("%LHR_USER_PATH:;=" "%") do if not "%%~D"=="" call :try_dir "%%~D"
if defined UV_EXE exit /b 0

if /I not "%~1"=="deep" exit /b 0
for /d %%D in ("%LOCALAPPDATA%\Microsoft\WinGet\Packages\astral-sh.uv*") do for /f "delims=" %%F in ('dir /s /b "%%~fD\uv.exe" 2^>nul') do call :try "%%~fF"
for /d %%D in ("%ProgramFiles%\WinGet\Packages\astral-sh.uv*") do for /f "delims=" %%F in ('dir /s /b "%%~fD\uv.exe" 2^>nul') do call :try "%%~fF"
exit /b 0

:try
if defined UV_EXE exit /b 0
set "UV_LOOKED=%UV_LOOKED%|%~1"
if exist "%~1" if not exist "%~1\" set "UV_EXE=%~1"
exit /b 0

:try_dir
rem One folder from the saved user PATH. Expand names like %USERPROFILE% in this one entry only.
if defined UV_EXE exit /b 0
set "LHR_DIR=%~1"
call set "LHR_DIR=%LHR_DIR%"
if "%LHR_DIR:~-1%"=="\" set "LHR_DIR=%LHR_DIR:~0,-1%"
call :try "%LHR_DIR%\uv.exe"
exit /b 0

:try_dir_and_children
call :try "%~1\uv.exe"
for /d %%S in ("%~1\*") do call :try "%%~fS\uv.exe"
exit /b 0

:read_user_path
set "LHR_USER_PATH="
if not defined SystemRoot set "SystemRoot=C:\Windows"
if not exist "%SystemRoot%\System32\reg.exe" exit /b 0
for /f "tokens=2,*" %%A in ('%SystemRoot%\System32\reg.exe query HKCU\Environment /v Path 2^>nul') do set "LHR_USER_PATH=%%B"
exit /b 0
