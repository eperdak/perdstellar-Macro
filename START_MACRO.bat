@echo off
setlocal enabledelayedexpansion

TITLE perdstellar Macro - Auto Updater

echo ==============================================
echo       perdstellar Macro - Auto Updater
echo ==============================================
echo(

cd /d "%~dp0"

set "ENGINE_DIR=%~dp0macro_python_dependencies"
set "PYTHON_EXE=%ENGINE_DIR%\python.exe"

set "TCL_LIBRARY=%ENGINE_DIR%\tcl\tcl8.6"
set "TK_LIBRARY=%ENGINE_DIR%\tcl\tk8.6"

set "LOCAL_VERSION_FILE=VERSION.txt"
set "LOCAL_SCRIPT=BiomeMacro.py"
set "REQ_FILE=requirements.txt"

set "LATEST_RELEASE_API=https://api.github.com/repos/eperdak/perdstellar-Macro/releases/latest"
set "RAW_SCRIPT_URL=https://raw.githubusercontent.com/eperdak/perdstellar-Macro/main/BiomeMacro.py"
set "RAW_REQ_URL=https://raw.githubusercontent.com/eperdak/perdstellar-Macro/main/requirements.txt"

REM === CHECK AND CLEAN CORRUPTED OR MISSING VERSION.TXT ===
if exist "%LOCAL_VERSION_FILE%" (
    set /p LOCAL_VERSION=<"%LOCAL_VERSION_FILE%"
    if defined LOCAL_VERSION set "LOCAL_VERSION=!LOCAL_VERSION: =!"
    
    echo !LOCAL_VERSION! | findstr /i "Error WebCmdlet Exception" >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        echo [!] Corrupted VERSION.txt detected. Resetting to v0.0.0...
        del /f /q "%LOCAL_VERSION_FILE%" >nul 2>&1
        set "LOCAL_VERSION=v0.0.0"
        echo v0.0.0>"%LOCAL_VERSION_FILE%"
    ) else (
        echo Local version: [!LOCAL_VERSION!]
    )
) else (
    echo [!] VERSION.txt not found. Creating default VERSION.txt...
    set "LOCAL_VERSION=v0.0.0"
    echo v0.0.0>"%LOCAL_VERSION_FILE%"
)

echo Checking for updates on GitHub...

set "REMOTE_VERSION="

for /f "usebackq delims=" %%i in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; $ErrorActionPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; try { $res = Invoke-RestMethod -Uri '%LATEST_RELEASE_API%' -UseBasicParsing; if ($res.tag_name) { Write-Output $res.tag_name } } catch {}" 2^>nul`) do (
    set "REMOTE_VERSION=%%i"
)

if defined REMOTE_VERSION set "REMOTE_VERSION=!REMOTE_VERSION: =!"

if "!REMOTE_VERSION!"=="" (
    echo [!] Could not fetch release tag from GitHub.
    if exist "%LOCAL_SCRIPT%" (
        echo [!] Running existing local script...
        goto run_macro
    ) else (
        echo [X] Error: Local script %LOCAL_SCRIPT% is missing.
        pause
        exit /b 1
    )
)

echo GitHub release tag: [!REMOTE_VERSION!]
echo(

if "!LOCAL_VERSION!"=="!REMOTE_VERSION!" (
    if exist "%LOCAL_SCRIPT%" (
        echo [OK] You are running the latest version. Skipping update.
        goto run_macro
    )
)

echo [!] Downloading update !REMOTE_VERSION!...
echo(

echo Fetching latest BiomeMacro.py...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; $ErrorActionPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; try { Invoke-WebRequest '%RAW_SCRIPT_URL%' -OutFile '%LOCAL_SCRIPT%' -UseBasicParsing } catch {}" 2>nul

echo Fetching latest requirements.txt...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; $ErrorActionPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; try { Invoke-WebRequest '%RAW_REQ_URL%' -OutFile '%REQ_FILE%' -UseBasicParsing } catch {}" 2>nul

if exist "%REQ_FILE%" (
    echo Checking Python dependencies...
    "%PYTHON_EXE%" -m pip install -r "%REQ_FILE%" --quiet
)

echo !REMOTE_VERSION!>"%LOCAL_VERSION_FILE%"
echo [OK] Updated VERSION.txt to !REMOTE_VERSION!.

echo [OK] Update completed!
echo(

:run_macro
echo ==============================================
echo         Starting perdstellar Macro...
echo ==============================================
echo(

if not exist "%PYTHON_EXE%" (
    echo [X] Error: Python executable not found at: "%PYTHON_EXE%"
    echo [X] Make sure macro_python_dependencies folder exists!
    pause
    exit /b 1
)

"%PYTHON_EXE%" "%LOCAL_SCRIPT%"

if %ERRORLEVEL% NEQ 0 (
    echo(
    echo [!] Application exited with error code %ERRORLEVEL%.
    pause
)